import os
import sys
import subprocess
import shutil

creationflags = 0
if sys.platform == 'win32':
    creationflags = subprocess.CREATE_NO_WINDOW


def _get_system_disk_index():
    """Returns the physical disk index that contains the system drive (usually C:\\)."""
    try:
        system_drive = os.environ.get('SystemDrive', 'C:').upper()
        if not system_drive.endswith('\\'):
            system_drive += '\\'
        # Use PowerShell to query which disk holds the system partition
        ps_cmd = (
            f"Get-Partition -DriveLetter '{system_drive[0]}' "
            "| Select-Object -ExpandProperty DiskNumber"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=creationflags
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
    except Exception as e:
        print(f"[drive_ops] Could not determine system disk index: {e}")
    return 0  # Fallback: assume disk 0 is the system disk


def _query_partition_info(disk_index):
    """
    Returns a list of partition dicts for the given physical disk index.
    Each dict: {'letter': 'E:', 'label': str, 'free_bytes': int, 'total_bytes': int, 'fstype': str}
    Uses Win32 API calls (non-blocking) to read volume info for each partition letter.
    """
    partitions = []
    try:
        import ctypes
        # Ask PowerShell for drive letters on this disk
        ps_cmd = (
            f"Get-Partition -DiskNumber {disk_index} "
            "| Where-Object { $_.DriveLetter } "
            "| Select-Object -ExpandProperty DriveLetter"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=creationflags
        )
        if result.returncode != 0:
            return partitions

        letters = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        for letter_char in letters:
            drive_letter = f"{letter_char.upper()}:"
            drive_path = drive_letter + "\\"

            # Query free space via kernel32 (non-blocking)
            freeBytes = ctypes.c_ulonglong(0)
            totalBytes = ctypes.c_ulonglong(0)
            totalFreeBytes = ctypes.c_ulonglong(0)
            success_space = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(drive_path),
                ctypes.byref(freeBytes),
                ctypes.byref(totalBytes),
                ctypes.byref(totalFreeBytes)
            )
            if not success_space:
                continue

            # Get volume label and filesystem type
            volumeNameBuffer = ctypes.create_unicode_buffer(1024)
            fileSystemNameBuffer = ctypes.create_unicode_buffer(1024)
            success_vol = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive_path),
                volumeNameBuffer, 1024,
                None, None, None,
                fileSystemNameBuffer, 1024
            )
            label = volumeNameBuffer.value if success_vol else ""
            fs_type = fileSystemNameBuffer.value if success_vol else ""

            partitions.append({
                'letter': drive_letter,
                'label': label,
                'free_bytes': freeBytes.value,
                'total_bytes': totalBytes.value,
                'fstype': fs_type
            })
    except Exception as e:
        print(f"[drive_ops] Error querying partitions for disk {disk_index}: {e}")
    return partitions


def list_removable_drives():
    """
    Lists all external / removable physical drives suitable for transport.
    Enumerates whole physical disks via WMI (Win32_DiskDrive) so that:
      - Multi-partition drives appear as a single entry (the whole device)
      - Unpartitioned / raw drives are also visible
    Returns a list of dicts, one per physical disk.
    """
    drives = []
    if sys.platform != 'win32':
        return drives

    try:
        system_disk_idx = _get_system_disk_index()

        # Use PowerShell + Get-Disk for reliable USB/external detection.
        # Get-Disk exposes BusType (USB, SATA, NVMe, etc.) directly.
        ps_cmd = (
            "Get-Disk | Where-Object { $_.BusType -eq 'USB' } "
            "| Select-Object Number, FriendlyName, Size, MediaType "
            "| ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
            creationflags=creationflags
        )

        if result.returncode != 0 or not result.stdout.strip():
            print(f"[drive_ops] Get-Disk query returned no results or failed.")
            return drives

        import json
        raw = json.loads(result.stdout.strip())
        # PowerShell returns a single object (not array) when there's only one result
        if isinstance(raw, dict):
            raw = [raw]

        for disk in raw:
            disk_index = disk.get("Number")
            if disk_index is None:
                continue

            # Skip the system disk
            if disk_index == system_disk_idx:
                continue

            friendly_name = disk.get("FriendlyName", "External Disk").strip()
            total_bytes = int(disk.get("Size", 0))
            media_type = str(disk.get("MediaType", "")).strip()

            # Determine human-friendly type description
            # MediaType from Get-Disk: 0 = Unspecified, 3 = HDD, 4 = SSD, 5 = SCM
            # For USB bus, "Removable" typically means flash drive; fixed means external HDD/SSD
            if media_type in ("4", "SSD"):
                type_desc = "External SSD"
            elif media_type in ("3", "HDD"):
                type_desc = "External Hard Drive"
            else:
                # Heuristic: small USB disks (<256GB) are likely flash drives
                if total_bytes < 256 * (1024 ** 3):
                    type_desc = "USB Flash Drive"
                else:
                    type_desc = "External Hard Drive"

            # Query existing partitions on this disk
            parts = _query_partition_info(disk_index)
            letters = [p['letter'] for p in parts]

            # Aggregate: label from first partition, or "Unallocated"
            if parts:
                label = parts[0]['label'] or friendly_name
                free_bytes = sum(p['free_bytes'] for p in parts)
            else:
                label = friendly_name
                free_bytes = 0

            drives.append({
                'disk_index': disk_index,
                'letter': letters[0] if letters else "",
                'letters': letters,
                'label': label or "External Disk",
                'total_bytes': total_bytes,
                'free_bytes': free_bytes,
                'type_desc': type_desc,
                'partitions': parts,
            })

    except Exception as e:
        print(f"Error listing removable drives: {e}")

    return drives

def format_drive(disk_index, label="PCM", drive_letter=None):
    r"""
    Formats an entire physical disk using diskpart.
    Cleans the disk, creates a single primary NTFS partition, and assigns a drive letter.

    Args:
        disk_index: Physical disk number (e.g. 1 for \\.\PhysicalDrive1)
        label: Volume label for the new partition (default "PCM")
        drive_letter: Optional safety check - if provided, refuses to proceed if it
                      resolves to the system drive. Not used for the actual format.

    Returns:
        The newly assigned drive letter string (e.g. "E:") on success, or False on failure.

    Requires administrator privileges because diskpart needs elevation.
    """
    if sys.platform != 'win32':
        print(f"[Mock Format] Formatted disk {disk_index} to NTFS with label {label}")
        return "Z:"  # Mock letter

    # Safety: refuse to format the system disk
    system_disk_idx = _get_system_disk_index()
    if disk_index == system_disk_idx:
        raise ValueError(f"Cannot format the system disk (Disk {disk_index})!")

    if drive_letter:
        dl = drive_letter.strip().upper()
        system_drive = os.environ.get('SystemDrive', 'C:').upper()
        if dl.rstrip(':') == system_drive.rstrip(':'):
            raise ValueError("Cannot format the system drive!")

    try:
        import re

        # Sanitize label
        label = re.sub(r'[^\w\-]', '_', label)[:32]

        # Build diskpart script
        #   select disk N  - target the physical disk
        #   clean           - wipe partition table
        #   create partition primary - single partition using all space
        #   format fs=ntfs quick label=XXX - quick NTFS format
        #   assign          - auto-assign the next available drive letter
        script_lines = [
            f"select disk {disk_index}",
            "clean",
            "create partition primary",
            f"format fs=ntfs quick label={label}",
            "assign",
        ]
        script_content = "\n".join(script_lines) + "\n"

        # Write script to a temp file (diskpart requires a file input)
        # Use the project working directory area to stay within workspace
        script_dir = os.path.join(os.environ.get('TEMP', os.getcwd()), 'pcm_diskpart')
        os.makedirs(script_dir, exist_ok=True)
        script_path = os.path.join(script_dir, 'format_script.txt')

        with open(script_path, 'w') as f:
            f.write(script_content)

        print(f"[drive_ops] Running diskpart with script:\n{script_content}")

        # Execute diskpart
        proc = subprocess.run(
            ["diskpart", "/s", script_path],
            capture_output=True, text=True, timeout=120,
            creationflags=creationflags
        )

        # Clean up script file
        try:
            os.remove(script_path)
        except Exception:
            pass

        print(f"[drive_ops] diskpart stdout:\n{proc.stdout}")
        if proc.stderr:
            print(f"[drive_ops] diskpart stderr:\n{proc.stderr}")

        if proc.returncode != 0:
            print(f"[drive_ops] diskpart failed with return code {proc.returncode}")
            return False

        # Check for errors in output (diskpart returns 0 even on some failures)
        output_lower = proc.stdout.lower()
        if "error" in output_lower or "cannot" in output_lower or "is not valid" in output_lower:
            # Check if these are real failures vs benign mentions
            if "diskpart succeeded" not in output_lower:
                print("[drive_ops] diskpart output contains error indicators.")
                return False

        # Determine the newly assigned drive letter by re-querying partitions
        parts = _query_partition_info(disk_index)
        if parts:
            new_letter = parts[0]['letter']
            print(f"[drive_ops] Format complete. New drive letter: {new_letter}")
            return new_letter
        else:
            # Fallback: try to find it via PowerShell
            try:
                ps_cmd = (
                    f"Get-Partition -DiskNumber {disk_index} "
                    "| Where-Object {{ $_.DriveLetter }} "
                    "| Select-Object -First 1 -ExpandProperty DriveLetter"
                )
                ps_result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=10,
                    creationflags=creationflags
                )
                if ps_result.returncode == 0 and ps_result.stdout.strip():
                    new_letter = ps_result.stdout.strip().upper() + ":"
                    print(f"[drive_ops] Format complete (PS fallback). New drive letter: {new_letter}")
                    return new_letter
            except Exception:
                pass
            print("[drive_ops] Format appeared to succeed but could not determine new drive letter.")
            return False

    except subprocess.TimeoutExpired:
        print(f"[drive_ops] diskpart timed out formatting disk {disk_index}")
        return False
    except Exception as e:
        print(f"[drive_ops] Exception formatting disk {disk_index}: {e}")
        return False

def eject_drive(drive_letter):
    """
    Attempts to safely eject/dismount the drive.
    Uses PowerShell com-object interface for clean ejection.
    """
    drive_letter = drive_letter.strip().upper()
    if not drive_letter.endswith(':'):
        drive_letter = drive_letter + ':'
        
    if sys.platform != 'win32':
        print(f"[Mock Eject] Ejected {drive_letter}")
        return True
        
    try:
        # PowerShell script to eject
        # (New-Object -ComObject Shell.Application).Namespace(17).ParseName('E:').InvokeVerb('Eject')
        # Namespace(17) corresponds to ssfDRIVES (My Computer)
        ps_cmd = f"(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{drive_letter}').InvokeVerb('Eject')"
        proc = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            creationflags=creationflags
        )
        
        if proc.returncode == 0:
            print(f"Drive {drive_letter} ejected successfully.")
            return True
        else:
            print(f"Eject failed: {proc.stderr}")
            return False
    except Exception as e:
        print(f"Exception ejecting drive {drive_letter}: {e}")
        return False

def self_copy_to_drive(drive_letter):
    """
    Copies the currently running executable to the root of the target drive.
    If running under Python directly (development), copies a mock/placeholder script
    or copy the source code directory.
    """
    drive_letter = drive_letter.strip().upper()
    if not drive_letter.endswith('\\'):
        drive_letter = drive_letter + '\\'
        
    target_path = os.path.join(drive_letter, "PCM.exe")
    
    try:
        if getattr(sys, 'frozen', False):
            # Running as compiled .exe
            exe_path = sys.executable
            shutil.copy2(exe_path, target_path)
            print(f"Copied compiled exe {exe_path} to {target_path}")
            return True
        else:
            # Running in dev/source mode. Write a launcher batch script or Python files.
            # In dev mode, we can create a text file "PCM.exe (dev placeholder)" or copy main.py as a script.
            # Let's write a simple batch script or copy the files so they can be run.
            dev_stub_path = os.path.join(drive_letter, "PCM_DEV_RUN.bat")
            with open(dev_stub_path, 'w') as f:
                f.write("@echo off\n")
                f.write("echo PCM (PC Mover) - Dev Mode Transport Launcher\n")
                f.write("echo Running python main.py from transport drive\n")
                f.write("pause\n")
            print("Dev mode: created PCM_DEV_RUN.bat stub on drive.")
            return True
    except Exception as e:
        print(f"Error copying self to drive: {e}")
        return False
