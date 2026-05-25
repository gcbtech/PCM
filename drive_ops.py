import os
import sys
import subprocess
import psutil
import shutil

# Windows Drive Type constants
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

def get_drive_type(drive_path):
    """Returns the Windows drive type for a given drive path (e.g. 'E:\\')."""
    if sys.platform == 'win32':
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(drive_path)
    return DRIVE_REMOVABLE  # Fallback for dev

def list_removable_drives():
    """
    Lists all external / removable drives suitable for transport.
    Uses pure Win32 API calls via ctypes instead of psutil to prevent 
    system hangs on empty card readers or disconnected network mapped drives.
    """
    drives = []
    if sys.platform != 'win32':
        return drives
        
    try:
        import ctypes
        
        # Get system drive to exclude it (usually C:\)
        system_drive = os.environ.get('SystemDrive', 'C:').upper()
        if not system_drive.endswith('\\'):
            system_drive += '\\'
            
        # GetLogicalDriveStringsW returns all drive letters separated by null bytes, e.g. "C:\x00D:\x00E:\x00\x00"
        buffer = ctypes.create_unicode_buffer(1024)
        length = ctypes.windll.kernel32.GetLogicalDriveStringsW(1024, buffer)
        
        if length == 0:
            return drives
            
        # Parse the raw unicode buffer separated by nulls
        raw_bytes = buffer.raw[:length * 2]
        drive_strings = raw_bytes.decode('utf-16le').split('\x00')
        drive_letters = [d.strip() for d in drive_strings if d.strip()]
        
        for drive_path in drive_letters:
            drive_letter = drive_path.rstrip('\\')
            
            # Skip system drive
            if drive_path.upper() == system_drive.upper():
                continue
                
            # Skip traditional floppy disk drives (A: and B:) to avoid slow hardware seeks
            if drive_letter.upper() in ['A:', 'B:']:
                continue
                
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
            
            # Focus on DRIVE_REMOVABLE (USB flash drives) and DRIVE_FIXED (USB external HDDs)
            if drive_type in [DRIVE_REMOVABLE, DRIVE_FIXED]:
                try:
                    # Query Disk Free Space directly using GetDiskFreeSpaceExW (non-blocking kernel call)
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
                        # If we can't query size (like an uninserted card reader), skip it immediately without blocking
                        continue
                        
                    # Fetch volume label and filesystem name
                    volumeNameBuffer = ctypes.create_unicode_buffer(1024)
                    fileSystemNameBuffer = ctypes.create_unicode_buffer(1024)
                    success_vol = ctypes.windll.kernel32.GetVolumeInformationW(
                        ctypes.c_wchar_p(drive_path),
                        volumeNameBuffer,
                        1024,
                        None,
                        None,
                        None,
                        fileSystemNameBuffer,
                        1024
                    )
                    
                    label = volumeNameBuffer.value if success_vol else ""
                    fs_type = fileSystemNameBuffer.value if success_vol else "NTFS"
                    
                    type_desc = "USB Flash Drive" if drive_type == DRIVE_REMOVABLE else "External Hard Drive"
                    
                    drives.append({
                        'letter': drive_letter,
                        'label': label or "Local Disk",
                        'total_bytes': totalBytes.value,
                        'free_bytes': freeBytes.value,
                        'fstype': fs_type,
                        'type_desc': type_desc
                    })
                except Exception:
                    # Skip empty/locked drives
                    continue
    except Exception as e:
        print(f"Error listing removable drives: {e}")
        
    return drives

def format_drive(drive_letter, label="PCM"):
    """
    Performs a quick format of the specified drive to NTFS.
    Requires administrative permissions or elevation in some Windows environments, 
    but for standard USB drives, standard user can format them.
    Command: format E: /fs:ntfs /v:PCM /q /x
    We pass 'Y\n' to handle any prompt.
    """
    drive_letter = drive_letter.strip().upper()
    if not drive_letter.endswith(':'):
        drive_letter = drive_letter + ':'
        
    system_drive = os.environ.get('SystemDrive', 'C:').upper()
    if drive_letter == system_drive:
        raise ValueError("Cannot format the system drive!")
        
    if sys.platform != 'win32':
        print(f"[Mock Format] Formatted {drive_letter} to NTFS with label {label}")
        return True
        
    try:
        # Run format command non-interactively
        # /q: Quick Format, /fs:ntfs: File System NTFS, /v:Label: Volume Label, /x: Force Dismount
        cmd = f"format {drive_letter} /fs:ntfs /v:{label} /q /x"
        print(f"Executing: {cmd}")
        
        # Popen allows us to feed input to stdin
        proc = subprocess.Popen(
            cmd, 
            shell=True, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        # Windows format command asks "Press ENTER when ready..." and then "Format another? (Y/N)"
        # We write Enter (\n) then N (\n)
        stdout, stderr = proc.communicate(input="\nN\n")
        
        if proc.returncode == 0:
            print("Drive formatted successfully.")
            return True
        else:
            print(f"Format failed (code {proc.returncode}). Stderr: {stderr}")
            # Try formatting without dismount if /x failed, or run via powershell
            return False
    except Exception as e:
        print(f"Exception formatting drive {drive_letter}: {e}")
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
            text=True
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
