import os
import shutil
import time
import sys
from utils import is_reparse_point

def get_unique_path(target_path):
    """
    If a file exists, appends (1), (2), etc. to the filename to make it unique.
    Example: C:\\Users\\User\\Desktop\\file.txt -> C:\\Users\\User\\Desktop\\file (1).txt
    """
    if not os.path.exists(target_path):
        return target_path
        
    dir_name, file_name = os.path.split(target_path)
    base, ext = os.path.splitext(file_name)
    
    counter = 1
    while True:
        new_name = f"{base} ({counter}){ext}"
        new_path = os.path.join(dir_name, new_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1

# is_reparse_point is imported from utils - see top of file

def copy_file_chunked(src, dst, buffer_size=1024*1024, chunk_callback=None):
    """
    Copies a single file from src to dst in chunks, reporting bytes written.
    Preserves file metadata (timestamps, etc.) after copy completes.
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    
    # Open both files and copy in chunks
    with open(src, 'rb') as fsrc:
        with open(dst, 'wb') as fdst:
            while True:
                buf = fsrc.read(buffer_size)
                if not buf:
                    break
                fdst.write(buf)
                if chunk_callback:
                    chunk_callback(len(buf))
                    
    # Preserve metadata (mtime, ctime, attributes)
    try:
        shutil.copystat(src, dst)
    except Exception:
        pass  # Non-fatal if metadata copy fails on certain filesystems

class CopyEngine:
    def __init__(self, progress_callback=None, conflict_pref='replace'):
        """
        progress_callback: function(current_file_path, bytes_just_copied, total_bytes_copied_so_far, files_copied_so_far)
        conflict_pref: 'replace', 'skip', 'keep_both'
        """
        self.progress_callback = progress_callback
        self.conflict_pref = conflict_pref.lower()
        self.total_bytes_copied = 0
        self.total_files_copied = 0
        self.log_entries = []
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def log(self, status, src, dst, size, error_msg=""):
        self.log_entries.append({
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'status': status,  # 'SUCCESS', 'SKIPPED', 'ERROR'
            'src': src,
            'dst': dst,
            'size': size,
            'error': error_msg
        })

    def copy_file_with_conflict_resolution(self, src, dst):
        """
        Copies file src to dst, applying the chosen conflict resolution policy.
        Returns status: 'SUCCESS', 'SKIPPED', or 'ERROR'
        """
        if self.cancelled:
            return 'SKIPPED'
            
        file_size = 0
        try:
            file_size = os.path.getsize(src)
        except Exception:
            pass

        if os.path.exists(dst):
            if self.conflict_pref == 'skip':
                self.log('SKIPPED', src, dst, file_size, "File already exists (skipped by user preference)")
                return 'SKIPPED'
            elif self.conflict_pref == 'keep_both':
                dst = get_unique_path(dst)
            # For 'replace', we just write over the existing file

        def chunk_cb(bytes_written):
            self.total_bytes_copied += bytes_written
            if self.progress_callback:
                self.progress_callback(src, bytes_written, self.total_bytes_copied, self.total_files_copied)

        try:
            # Handle empty files or directories
            if os.path.isdir(src):
                os.makedirs(dst, exist_ok=True)
                return 'SUCCESS'
                
            # If the source file is a reparse point (symlink/placeholder), skip it
            if is_reparse_point(src):
                self.log('SKIPPED', src, dst, file_size, "Reparse point/cloud placeholder skipped.")
                return 'SKIPPED'
                
            copy_file_chunked(src, dst, chunk_callback=chunk_cb)
            self.total_files_copied += 1
            # Final notification to ensure file count increments in GUI
            if self.progress_callback:
                self.progress_callback(src, 0, self.total_bytes_copied, self.total_files_copied)
                
            self.log('SUCCESS', src, dst, file_size)
            return 'SUCCESS'
        except (PermissionError, FileNotFoundError, OSError) as e:
            self.log('ERROR', src, dst, file_size, str(e))
            return 'ERROR'
        except Exception as e:
            self.log('ERROR', src, dst, file_size, f"Unexpected error: {str(e)}")
            return 'ERROR'

    def copy_folder_recursive(self, src_dir, dst_dir):
        """
        Recursively copies all items from src_dir to dst_dir.
        Avoids infinite loop if dst_dir is inside src_dir.
        Skips reparse points (symlinks/junctions) and browser cache/logs.
        """
        from utils import should_exclude_file_or_dir
        if self.cancelled or is_reparse_point(src_dir) or should_exclude_file_or_dir(src_dir):
            return
            
        # Get absolute paths to check nesting
        abs_src = os.path.abspath(src_dir)
        abs_dst = os.path.abspath(dst_dir)
        
        if abs_dst.startswith(abs_src + os.sep):
            # Destination is a subdirectory of source, skip it to prevent recursion loop
            self.log('SKIPPED', src_dir, dst_dir, 0, "Destination is nested inside Source; skipped to prevent loop.")
            return

        try:
            for root, dirs, files in os.walk(src_dir, topdown=True):
                if self.cancelled:
                    break
                    
                # Filter out reparse points and browser cache/logs from directories list in-place
                dirs_to_keep = []
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    if not is_reparse_point(dir_path) and not should_exclude_file_or_dir(dir_path):
                        dirs_to_keep.append(d)
                dirs[:] = dirs_to_keep  # Recurse only into safe folders
                
                # Create corresponding destination directories
                rel_path = os.path.relpath(root, src_dir)
                if rel_path == '.':
                    current_dst_dir = dst_dir
                else:
                    current_dst_dir = os.path.join(dst_dir, rel_path)
                    
                os.makedirs(current_dst_dir, exist_ok=True)
                
                for file in files:
                    if self.cancelled:
                        break
                    src_file = os.path.join(root, file)
                    if is_reparse_point(src_file) or should_exclude_file_or_dir(src_file):
                        continue  # Skip virtual/cloud placeholders, symlinks, and cache/logs
                    dst_file = os.path.join(current_dst_dir, file)
                    self.copy_file_with_conflict_resolution(src_file, dst_file)
        except Exception as e:
            self.log('ERROR', src_dir, dst_dir, 0, f"Error traversing directory: {e}")

    def write_log_files(self, desktop_user_path=None, drive_root_path=None):
        """
        Writes a clean, formatted text log of the migration operations.
        One to Desktop, one to the transport drive root.
        """
        # Create log content
        success_count = sum(1 for e in self.log_entries if e['status'] == 'SUCCESS')
        skipped_count = sum(1 for e in self.log_entries if e['status'] == 'SKIPPED')
        error_count = sum(1 for e in self.log_entries if e['status'] == 'ERROR')
        
        log_header = [
            "==================================================",
            "          PCM (PC Mover) Migration Log            ",
            "==================================================",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Machine: {os.environ.get('COMPUTERNAME', 'Unknown')}",
            f"User Profile: {os.environ.get('USERNAME', 'Unknown')}",
            "--------------------------------------------------",
            f"Total Files Successfully Copied: {success_count}",
            f"Total Files Skipped:             {skipped_count}",
            f"Errors / Failed Files:           {error_count}",
            f"Total Bytes Transferred:         {self.total_bytes_copied} ({self.total_bytes_copied / (1024*1024):.2f} MB)",
            "==================================================\n",
            "Details of operations:"
        ]
        
        details = []
        for e in self.log_entries:
            if e['status'] == 'ERROR':
                details.append(f"[{e['status']}] {e['src']} -> {e['dst']} | Error: {e['error']}")
            elif e['status'] == 'SKIPPED':
                details.append(f"[{e['status']}] {e['src']} -> {e['dst']} | Note: {e['error']}")
            else:
                details.append(f"[{e['status']}] {e['src']} -> {e['dst']} ({e['size']} bytes)")
                
        full_log_text = "\n".join(log_header + details)
        
        # Save to Desktop
        if desktop_user_path:
            desktop_path = os.path.join(desktop_user_path, 'Desktop')
            if os.path.exists(desktop_path):
                log_file = os.path.join(desktop_path, "PCM_Migration_Log.txt")
                try:
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(full_log_text)
                    print(f"Log written to Desktop: {log_file}")
                except Exception as e:
                    print(f"Could not write log to Desktop: {e}")

        # Save to Drive
        if drive_root_path:
            log_file = os.path.join(drive_root_path, "PCM_Migration_Log.txt")
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(full_log_text)
                print(f"Log written to Drive: {log_file}")
            except Exception as e:
                print(f"Could not write log to Drive: {e}")
                
        return full_log_text
