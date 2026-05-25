import os
import sys
import socket
import ssl
import time
import json
import tempfile
import threading
import subprocess
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import datetime

# Protocol Ports
PORT_TCP = 58291
PORT_UDP = 58292

# Protocol Commands
CMD_PAIRING_CODE = 1
CMD_VERIFY_SUCCESS = 2
CMD_VERIFY_FAIL = 3
CMD_MANIFEST = 4
CMD_TARGET_PREFS = 5
CMD_FILE_START = 6
CMD_FILE_CHUNK = 7
CMD_FILE_END = 8
CMD_TRANSFER_COMPLETE = 9
CMD_ERROR = 10
CMD_HEARTBEAT = 11

def generate_self_signed_cert():
    """
    Generates an ephemeral RSA private key and self-signed certificate, 
    writing them to temporary files to be loaded by the ssl module.
    """
    print("[Network] Generating ephemeral SSL certificate...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"PCM Network Transfer"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    temp_dir = tempfile.gettempdir()
    cert_path = os.path.join(temp_dir, "pcm_temp_cert.crt")
    key_path = os.path.join(temp_dir, "pcm_temp_key.key")
    
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
        
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        
    print(f"[Network] Certificate written to: {cert_path}")
    return cert_path, key_path

def add_firewall_rule():
    """
    Adds a Windows Defender Firewall rule for the PCM executable.
    Requires Administrator privileges.
    """
    exe_path = sys.executable
    rule_name = "PCM PC Mover"
    print(f"[Network] Adding Windows Firewall rule for: {exe_path}")
    try:
        # Delete existing rule first to clean up
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
            capture_output=True, text=True, check=False
        )
        
        # Add new rule
        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            "dir=in",
            "action=allow",
            f"program={exe_path}",
            "enable=yes",
            "profile=any"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        success = res.returncode == 0
        print(f"[Network] Firewall rule addition result: {'SUCCESS' if success else 'FAILED'} (code {res.returncode})")
        return success
    except Exception as e:
        print(f"[Network] Exception while managing firewall: {e}")
        return False

def remove_firewall_rule():
    """
    Removes the Windows Defender Firewall rule for the PCM executable.
    """
    rule_name = "PCM PC Mover"
    print("[Network] Cleaning up Windows Firewall rule...")
    try:
        res = subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
            capture_output=True, text=True, check=False
        )
        return res.returncode == 0
    except Exception as e:
        print(f"[Network] Exception while removing firewall: {e}")
        return False

def send_frame(sock, cmd_type, payload=b""):
    """
    Sends a frame over the socket.
    Format: [4 bytes length][1 byte command_type][payload]
    """
    length = len(payload)
    header = length.to_bytes(4, byteorder='big') + cmd_type.to_bytes(1, byteorder='big')
    sock.sendall(header + payload)

def receive_frame(sock):
    """
    Receives a single frame from the socket.
    Returns: (cmd_type, payload)
    """
    header = b""
    while len(header) < 5:
        chunk = sock.recv(5 - len(header))
        if not chunk:
            raise ConnectionError("Socket closed prematurely while reading header.")
        header += chunk
        
    length = int.from_bytes(header[:4], byteorder='big')
    cmd_type = header[4]
    
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise ConnectionError("Socket closed prematurely while reading payload.")
        payload += chunk
        
    return cmd_type, payload

def get_local_ips():
    """
    Returns list of local IP addresses on the machine.
    Useful for manual network configuration / debugging.
    """
    ips = []
    try:
        # Get hostname
        hostname = socket.gethostname()
        # Enumerate addresses
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and ip != "127.0.0.1": # Filter IPv4 only
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    
    # Fallback/alternative
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip not in ips:
            ip = s.getsockname()[0]
        if ip not in ips:
            ips.append(ip)
    except Exception:
        pass
        
    return ips

class PCMNetworkReceiver:
    def __init__(self, pairing_code, manifest_received_cb, target_selected_event, progress_cb, completion_cb, error_cb):
        self.pairing_code = str(pairing_code).strip()
        self.manifest_received_cb = manifest_received_cb
        self.target_selected_event = target_selected_event
        self.progress_cb = progress_cb
        self.completion_cb = completion_cb
        self.error_cb = error_cb
        
        self.server_sock = None
        self.ssl_conn = None
        self.beacon_active = True
        self.cancelled = False
        self.target_prefs = None  # To be set by GUI: {'user_path': '...', 'conflict_pref': 'replace'}
        self.cert_path = None
        self.key_path = None

    def start_beacon(self):
        """Starts UDP beacon broadcast in a separate thread."""
        def beacon_loop():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            print("[Network] UDP Beacon thread started.")
            while self.beacon_active and not self.cancelled:
                try:
                    # Broadcast availability
                    s.sendto(b"PCM_BEACON:58291", ('255.255.255.255', PORT_UDP))
                except Exception as e:
                    print(f"[Network] UDP Broadcast error: {e}")
                time.sleep(1.0)
            s.close()
            print("[Network] UDP Beacon thread stopped.")
            
        t = threading.Thread(target=beacon_loop, daemon=True)
        t.start()

    def stop(self):
        self.cancelled = True
        self.beacon_active = False
        if self.ssl_conn:
            try:
                self.ssl_conn.close()
            except Exception:
                pass
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        # Clean up certs
        if self.cert_path and os.path.exists(self.cert_path):
            try:
                os.remove(self.cert_path)
                os.remove(self.key_path)
            except Exception:
                pass

    def run(self):
        """Executes the Receiver server loop. Should be run in a background thread."""
        try:
            # 1. Start Firewall configuration (already checked via Admin elevation)
            add_firewall_rule()

            # 2. Generate Cert
            self.cert_path, self.key_path = generate_self_signed_cert()

            # 3. Start UDP beacon
            self.start_beacon()

            # 4. Create TCP socket
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("", PORT_TCP))
            self.server_sock.listen(1)
            print(f"[Network] TCP Server listening on port {PORT_TCP}...")

            # Accept connection
            conn, addr = self.server_sock.accept()
            print(f"[Network] Connection from: {addr}")
            self.beacon_active = False # Stop beacon once connection is received

            # Wrap with SSL
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)
            self.ssl_conn = context.wrap_socket(conn, server_side=True)
            print("[Network] SSL/TLS handshake complete.")

            # 5. Verify pairing code
            cmd, payload = receive_frame(self.ssl_conn)
            if cmd != CMD_PAIRING_CODE or payload.decode('utf-8').strip() != self.pairing_code:
                send_frame(self.ssl_conn, CMD_VERIFY_FAIL, b"Invalid Pairing Code")
                raise ValueError("Authentication failed: invalid pairing code.")
            
            send_frame(self.ssl_conn, CMD_VERIFY_SUCCESS, b"OK")
            print("[Network] Client successfully authenticated.")

            # 6. Receive manifest metadata
            cmd, payload = receive_frame(self.ssl_conn)
            if cmd != CMD_MANIFEST:
                raise ValueError("Expected CMD_MANIFEST from client.")
            
            manifest_data = json.loads(payload.decode('utf-8'))
            print("[Network] Manifest received from client.")

            # Notify GUI of manifest and wait for user selections
            self.manifest_received_cb(manifest_data)
            
            # Block until GUI releases event
            print("[Network] Waiting for GUI target user and conflict selection...")
            while not self.target_selected_event.is_set():
                if self.cancelled:
                    return
                time.sleep(0.1)

            # Send preferences back to client
            prefs_bytes = json.dumps(self.target_prefs).encode('utf-8')
            send_frame(self.ssl_conn, CMD_TARGET_PREFS, prefs_bytes)
            print("[Network] Target user preferences sent to client.")

            # Get target user paths and options
            target_user_path = self.target_prefs['user_path']
            conflict_pref = self.target_prefs.get('conflict_pref', 'replace').lower()
            
            # Map of categories to profile subdirectories
            # Desktop, Documents, Downloads, Pictures, Videos, Music
            category_dirs = {
                'Desktop': os.path.join(target_user_path, 'Desktop'),
                'Documents': os.path.join(target_user_path, 'Documents'),
                'Downloads': os.path.join(target_user_path, 'Downloads'),
                'Pictures': os.path.join(target_user_path, 'Pictures'),
                'Videos': os.path.join(target_user_path, 'Videos'),
                'Music': os.path.join(target_user_path, 'Music'),
                'Bookmarks': os.path.join(target_user_path, 'AppData', 'Local', 'PCM_Bookmarks_Temp') # Temporary path for incoming bookmarks
            }

            from copy_engine import get_unique_path
            
            # 7. File transfer loop
            files_processed = 0
            total_bytes_written = 0
            log_entries = []

            while not self.cancelled:
                cmd, payload = receive_frame(self.ssl_conn)
                
                if cmd == CMD_TRANSFER_COMPLETE:
                    print("[Network] Transfer complete frame received.")
                    break
                elif cmd == CMD_ERROR:
                    raise ValueError(f"Sender reported error: {payload.decode('utf-8')}")
                elif cmd != CMD_FILE_START:
                    raise ValueError(f"Unexpected frame command: {cmd}")
                
                # CMD_FILE_START
                file_meta = json.loads(payload.decode('utf-8'))
                rel_path = file_meta['rel_path']
                file_size = file_meta['size']
                category = file_meta.get('category', 'Documents')
                
                # Resolve destination folder
                dst_root = category_dirs.get(category, category_dirs['Documents'])
                dst_file_path = os.path.join(dst_root, rel_path)
                os.makedirs(os.path.dirname(dst_file_path), exist_ok=True)
                
                # Handle conflict resolution
                skip_current = False
                if os.path.exists(dst_file_path):
                    if conflict_pref == 'skip':
                        skip_current = True
                        log_entries.append({
                            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'SKIPPED',
                            'src': rel_path,
                            'dst': dst_file_path,
                            'size': file_size,
                            'error': 'File already exists (skipped)'
                        })
                    elif conflict_pref == 'keep_both':
                        dst_file_path = get_unique_path(dst_file_path)

                # Open destination file if not skipping
                fdst = None
                if not skip_current:
                    try:
                        fdst = open(dst_file_path, 'wb')
                    except Exception as e:
                        print(f"[Network] Error opening file for write {dst_file_path}: {e}")
                        skip_current = True
                        log_entries.append({
                            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'ERROR',
                            'src': rel_path,
                            'dst': dst_file_path,
                            'size': 0,
                            'error': str(e)
                        })

                # Stream chunks until CMD_FILE_END
                file_bytes_read = 0
                while not self.cancelled:
                    chunk_cmd, chunk_payload = receive_frame(self.ssl_conn)
                    if chunk_cmd == CMD_FILE_END:
                        break
                    elif chunk_cmd != CMD_FILE_CHUNK:
                        raise ValueError(f"Expected CMD_FILE_CHUNK or CMD_FILE_END, got: {chunk_cmd}")
                    
                    if not skip_current and fdst:
                        fdst.write(chunk_payload)
                    
                    file_bytes_read += len(chunk_payload)
                    total_bytes_written += len(chunk_payload)
                    self.progress_cb(rel_path, len(chunk_payload), files_processed, manifest_data['total_files'])

                if fdst:
                    fdst.close()

                if not skip_current:
                    files_processed += 1
                    log_entries.append({
                        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'SUCCESS',
                        'src': rel_path,
                        'dst': dst_file_path,
                        'size': file_size,
                        'error': ''
                    })
                    # Report file iteration update to UI
                    self.progress_cb(rel_path, 0, files_processed, manifest_data['total_files'])

            # 8. Post-process browser bookmarks if they were sent
            # Check if temporary bookmarks folder exists, and trigger import
            bookmarks_temp_path = category_dirs['Bookmarks']
            if os.path.exists(bookmarks_temp_path):
                print("[Network] Importing browser bookmarks locally...")
                import bookmarks
                try:
                    # Organised by browser. Bookmarks module expects files in a _pcm_bookmarks directory
                    # We pass the temporary directory path as target bookmarks folder
                    bookmarks.import_bookmarks(bookmarks_temp_path, target_user_path)
                except Exception as e:
                    print(f"[Network] Bookmarks restore error: {e}")
                # Clean up temporary bookmarks folder
                try:
                    import shutil
                    shutil.rmtree(bookmarks_temp_path)
                except Exception:
                    pass

            # 9. Create final log files
            # Write a detailed report to the Receiver Desktop
            success_count = sum(1 for e in log_entries if e['status'] == 'SUCCESS')
            skipped_count = sum(1 for e in log_entries if e['status'] == 'SKIPPED')
            error_count = sum(1 for e in log_entries if e['status'] == 'ERROR')

            log_header = [
                "==================================================",
                "          PCM (PC Mover) Network Migration Log    ",
                "==================================================",
                f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Source Machine: {manifest_data.get('source_machine', 'Unknown')}",
                f"Destination Machine: {os.environ.get('COMPUTERNAME', 'Unknown')}",
                f"Target User Profile: {os.path.basename(target_user_path)}",
                "--------------------------------------------------",
                f"Total Files Successfully Copied: {success_count}",
                f"Total Files Skipped:             {skipped_count}",
                f"Errors / Failed Files:           {error_count}",
                f"Total Bytes Transferred:         {total_bytes_written} ({total_bytes_written / (1024*1024):.2f} MB)",
                "==================================================\n",
                "Details of operations:"
            ]
            
            details = []
            for e in log_entries:
                if e['status'] == 'ERROR':
                    details.append(f"[{e['status']}] {e['src']} -> {e['dst']} | Error: {e['error']}")
                elif e['status'] == 'SKIPPED':
                    details.append(f"[{e['status']}] {e['src']} -> {e['dst']} | Note: {e['error']}")
                else:
                    details.append(f"[{e['status']}] {e['src']} -> {e['dst']} ({e['size']} bytes)")
                    
            full_log_text = "\n".join(log_header + details)

            desktop_path = os.path.join(target_user_path, 'Desktop')
            if os.path.exists(desktop_path):
                log_file = os.path.join(desktop_path, "PCM_Network_Migration_Log.txt")
                try:
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(full_log_text)
                    print(f"[Network] Log written to Desktop: {log_file}")
                except Exception as e:
                    print(f"[Network] Could not write log to Desktop: {e}")

            summary = f"Import complete! {success_count} files imported, {error_count} errors. Check PCM_Network_Migration_Log.txt on your Desktop."
            self.completion_cb(summary)

        except Exception as e:
            print(f"[Network] Receiver Error: {e}")
            if not self.cancelled:
                self.error_cb(str(e))
        finally:
            self.stop()

class PCMNetworkSender:
    def __init__(self, pairing_code, files_to_send, progress_cb, completion_cb, error_cb):
        self.pairing_code = str(pairing_code).strip()
        self.files_to_send = files_to_send # list of dicts: {'src_path': '...', 'rel_path': '...', 'size': 123, 'category': '...'}
        self.progress_cb = progress_cb
        self.completion_cb = completion_cb
        self.error_cb = error_cb
        
        self.ssl_sock = None
        self.cancelled = False

    def stop(self):
        self.cancelled = True
        if self.ssl_sock:
            try:
                self.ssl_sock.close()
            except Exception:
                pass

    def run(self):
        """Executes the Sender client loop. Should be run in a background thread."""
        try:
            # 1. Listen for UDP beacon to auto-discover Destination IP
            print("[Network] Starting UDP auto-discovery...")
            receiver_ip = None
            
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                udp_sock.bind(("", PORT_UDP))
            except Exception:
                # Fallback if binding fails
                pass
            udp_sock.settimeout(6.0)

            start_time = time.time()
            while time.time() - start_time < 6.0:
                if self.cancelled:
                    udp_sock.close()
                    return
                try:
                    data, addr = udp_sock.recvfrom(1024)
                    if data.startswith(b"PCM_BEACON:58291"):
                        receiver_ip = addr[0]
                        print(f"[Network] Auto-discovered Receiver at: {receiver_ip}")
                        break
                except socket.timeout:
                    break
                except Exception as e:
                    print(f"[Network] Discovery socket exception: {e}")
                    time.sleep(0.5)

            udp_sock.close()

            # Fallback if discovery fails (check localhost)
            if not receiver_ip:
                print("[Network] Auto-discovery timed out. Attempting fallback to localhost...")
                receiver_ip = "127.0.0.1"

            # 2. Connect to Receiver
            print(f"[Network] Connecting to {receiver_ip}:{PORT_TCP}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((receiver_ip, PORT_TCP))
            sock.settimeout(None) # Reset timeout for streaming

            # SSL Wrap
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.ssl_sock = context.wrap_socket(sock, server_hostname="localhost")
            print("[Network] SSL/TLS tunnel established.")

            # 3. Send pairing code
            send_frame(self.ssl_sock, CMD_PAIRING_CODE, self.pairing_code.encode('utf-8'))
            print("[Network] Pairing code sent. Waiting for verification...")

            # Receive verification response
            cmd, payload = receive_frame(self.ssl_sock)
            if cmd == CMD_VERIFY_FAIL:
                raise ValueError("Incorrect pairing code entered. Access Denied.")
            elif cmd != CMD_VERIFY_SUCCESS:
                raise ValueError(f"Unexpected response from Receiver: {cmd}")

            print("[Network] Successfully authenticated and paired!")

            # 4. Compile and send Manifest
            total_size = sum(f['size'] for f in self.files_to_send)
            total_files = len(self.files_to_send)
            
            manifest_dict = {
                'source_machine': os.environ.get('COMPUTERNAME', 'Unknown'),
                'total_files': total_files,
                'total_size': total_size
            }
            send_frame(self.ssl_sock, CMD_MANIFEST, json.dumps(manifest_dict).encode('utf-8'))
            print("[Network] Manifest metadata sent.")

            # 5. Wait for target preference confirmation from Receiver
            cmd, payload = receive_frame(self.ssl_sock)
            if cmd != CMD_TARGET_PREFS:
                raise ValueError("Expected target preferences from Receiver.")
            
            target_prefs = json.loads(payload.decode('utf-8'))
            print(f"[Network] Target preferences acknowledged: {target_prefs}")

            # 6. Stream files chunk-by-chunk
            files_processed = 0
            total_bytes_sent = 0
            
            for file_info in self.files_to_send:
                if self.cancelled:
                    break
                
                src_path = file_info['src_path']
                rel_path = file_info['rel_path']
                file_size = file_info['size']
                category = file_info.get('category', 'Documents')

                # Send file metadata
                meta = {
                    'rel_path': rel_path,
                    'size': file_size,
                    'category': category
                }
                send_frame(self.ssl_sock, CMD_FILE_START, json.dumps(meta).encode('utf-8'))

                # Stream chunks
                bytes_sent_for_file = 0
                if os.path.exists(src_path) and os.path.isfile(src_path):
                    try:
                        with open(src_path, 'rb') as f:
                            while not self.cancelled:
                                chunk = f.read(65536) # 64KB buffer
                                if not chunk:
                                    break
                                send_frame(self.ssl_sock, CMD_FILE_CHUNK, chunk)
                                bytes_sent_for_file += len(chunk)
                                total_bytes_sent += len(chunk)
                                self.progress_cb(rel_path, len(chunk), files_processed, total_files)
                    except Exception as e:
                        print(f"[Network] Error reading file {src_path}: {e}")
                        # In case of read failure, we still send FILE_END so receiver closes file safely
                        
                send_frame(self.ssl_sock, CMD_FILE_END, b"")
                files_processed += 1
                # Report absolute file update to GUI
                self.progress_cb(rel_path, 0, files_processed, total_files)

            # 7. Complete transfer
            if not self.cancelled:
                send_frame(self.ssl_sock, CMD_TRANSFER_COMPLETE, b"")
                print("[Network] Send migration complete!")
                self.completion_cb(f"Export complete! {files_processed} files successfully sent to destination computer.")

        except Exception as e:
            print(f"[Network] Sender Error: {e}")
            if not self.cancelled:
                self.error_cb(str(e))
        finally:
            self.stop()
