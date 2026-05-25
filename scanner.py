import os
import sys
import time

# System accounts to filter out
SYSTEM_ACCOUNTS = {
    'default', 'default user', 'public', 'all users', 'administrator', 
    'guest', 'defaultuser0', 'desktop.ini', 'systemprofile', 
    'networkservice', 'localservice'
}

class UserProfile:
    def __init__(self, username, path):
        self.username = username
        self.path = path
        self.folders = {}  # folder_name -> FolderInfo

class FolderInfo:
    def __init__(self, name, path, exists=False, size_bytes=0, file_count=0):
        self.name = name
        self.path = path
        self.exists = exists
        self.size_bytes = size_bytes
        self.file_count = file_count

    def get_friendly_size(self):
        size = self.size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

def get_users_root():
    """Returns the base Users directory, typically C:\\Users"""
    if sys.platform == 'win32':
        return os.environ.get('SystemDrive', 'C:') + '\\Users'
    return '/Users'  # Fallback for development/testing on macOS/Linux

# Unbuffered logging helper
_debug_file = None

def init_debug_log():
    global _debug_file
    try:
        # Write to same directory as the executable to avoid OneDrive redirects
        running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        log_path = os.path.join(running_dir, "PCM_Scan_Step_Debug.log")
        # buffering=1 means line-buffered (flushes on newlines)
        _debug_file = open(log_path, "w", encoding="utf-8", buffering=1)
        log_debug("=== PCM SCAN DEBUG INITIALIZED ===")
    except Exception as e:
        print(f"Could not open debug log: {e}")

def log_debug(message):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    try:
        print(formatted)
    except Exception:
        pass
    if _debug_file:
        try:
            _debug_file.write(formatted + "\n")
            _debug_file.flush()
            # Force OS level flush to disk
            os.fsync(_debug_file.fileno())
        except Exception:
            pass

def close_debug_log():
    global _debug_file
    if _debug_file:
        try:
            log_debug("=== PCM SCAN DEBUG FINISHED SUCCESSFULLY ===")
            _debug_file.close()
            _debug_file = None
        except Exception:
            pass

def scan_user_profiles():
    """
    Scans the system for local user profiles.
    Returns a list of UserProfile objects.
    """
    users_dir = get_users_root()
    profiles = []
    
    if not os.path.exists(users_dir):
        return profiles
        
    try:
        for entry in os.scandir(users_dir):
            if entry.is_dir():
                name_lower = entry.name.lower()
                if name_lower not in SYSTEM_ACCOUNTS and not entry.name.startswith('.'):
                    profiles.append(UserProfile(entry.name, entry.path))
    except Exception as e:
        print(f"Error scanning user profiles: {e}")
        
    return profiles

def is_reparse_point(path):
    """
    Checks if a file or directory is a Windows reparse point (junction, symlink, or cloud-only placeholder).
    Reparse points can cause infinite loops or force slow cloud downloads on Windows.
    """
    if sys.platform != 'win32':
        return os.path.islink(path)
    try:
        # 1024 corresponds to stat.FILE_ATTRIBUTE_REPARSE_POINT
        return bool(os.lstat(path).st_file_attributes & 1024)
    except Exception:
        return False

def get_folder_stats(folder_path):
    """
    Recursively counts files and sums bytes for a folder.
    Skips junctions, symlinks, and cloud placeholders to prevent hangs/loops.
    """
    total_size = 0
    file_count = 0
    
    log_debug(f"get_folder_stats: Entering folder_path = {folder_path}")
    
    # Safe check path existence without following potentially broken symlinks
    log_debug("get_folder_stats: Checking path existence via lstat...")
    try:
        os.lstat(folder_path)
    except Exception:
        log_debug("get_folder_stats: Path does not exist or inaccessible (lstat failed). Skipping.")
        return 0, 0
        
    log_debug("get_folder_stats: Checking if reparse point...")
    if is_reparse_point(folder_path):
        log_debug("get_folder_stats: Folder is a reparse point (junction/symlink). Skipping.")
        return 0, 0
        
    try:
        log_debug("get_folder_stats: Starting directory traversal (os.walk)...")
        # topdown=True allows in-place directory filtering
        for root, dirs, files in os.walk(folder_path, topdown=True):
            log_debug(f"get_folder_stats: Walking in root = {root}")
            
            # Filter out reparse points from directories list in-place
            dirs_to_keep = []
            for d in dirs:
                dir_path = os.path.join(root, d)
                log_debug(f"get_folder_stats:   Inspecting directory entry: {d}")
                if not is_reparse_point(dir_path):
                    dirs_to_keep.append(d)
                else:
                    log_debug(f"get_folder_stats:   Skipping reparse point folder: {d}")
            dirs[:] = dirs_to_keep  # Walk will only recurse into safe folders
            
            for file in files:
                file_path = os.path.join(root, file)
                log_debug(f"get_folder_stats:   Inspecting file entry: {file}")
                
                if is_reparse_point(file_path):
                    log_debug(f"get_folder_stats:   Skipping reparse point/cloud file: {file}")
                    continue
                    
                try:
                    log_debug(f"get_folder_stats:     Performing os.stat on {file}")
                    stat = os.stat(file_path)
                    total_size += stat.st_size
                    file_count += 1
                except (PermissionError, FileNotFoundError) as e:
                    log_debug(f"get_folder_stats:     Access skipped due to: {type(e).__name__}")
                    continue
                except Exception as e:
                    log_debug(f"get_folder_stats:     Access skipped due to generic exception: {e}")
                    continue
        log_debug(f"get_folder_stats: Completed walk for {folder_path}.")
    except Exception as e:
        log_debug(f"get_folder_stats: Walk failed with exception: {e}")
        
    return total_size, file_count

def scan_profile_folders(user_profile_path, status_callback=None):
    """
    Scans standard folders for a specific user profile path.
    Also handles OneDrive redirected folders, picking whichever exists or combining.
    """
    # Initialize the diagnostic log file
    init_debug_log()
    
    standard_names = ['Desktop', 'Documents', 'Downloads', 'Pictures', 'Videos', 'Music']
    folders_info = {}
    
    log_debug(f"scan_profile_folders: Starting scan for profile = {user_profile_path}")
    
    for name in standard_names:
        log_debug(f"scan_profile_folders: Current loop target folder = {name}")
        if status_callback:
            try:
                status_callback(f"Scanning folder: {name}")
            except Exception:
                pass
                
        # Check standard location
        std_path = os.path.join(user_profile_path, name)
        # Check OneDrive location (common in Windows 10/11)
        od_path = os.path.join(user_profile_path, 'OneDrive', name)
        
        target_path = std_path
        exists = False
        
        log_debug(f"scan_profile_folders: Checking OneDrive path: {od_path}")
        try:
            # Check lstat first to see if it exists at all
            os.lstat(od_path)
            log_debug("scan_profile_folders: OneDrive path exists!")
            target_path = od_path
            exists = True
        except Exception:
            log_debug("scan_profile_folders: OneDrive path does not exist.")
            
        if not exists:
            log_debug(f"scan_profile_folders: Checking standard path: {std_path}")
            try:
                os.lstat(std_path)
                log_debug("scan_profile_folders: Standard path exists!")
                target_path = std_path
                exists = True
            except Exception:
                log_debug("scan_profile_folders: Standard path does not exist.")
            
        if exists:
            log_debug(f"scan_profile_folders: Proceeding to scan target_path: {target_path}")
            size_bytes, file_count = get_folder_stats(target_path)
            folders_info[name] = FolderInfo(name, target_path, exists=True, size_bytes=size_bytes, file_count=file_count)
            log_debug(f"scan_profile_folders: Scan finished for {name}. Size: {size_bytes} bytes, Files: {file_count}")
        else:
            log_debug(f"scan_profile_folders: Skipping {name} since no paths exist.")
            folders_info[name] = FolderInfo(name, target_path, exists=False)
            
    # Close diagnostic log file
    close_debug_log()
    return folders_info
