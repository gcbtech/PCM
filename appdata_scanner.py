import os

class AppDataInfo:
    def __init__(self, name, exists=False, size_bytes=0, items=None):
        self.name = name
        self.exists = exists
        self.size_bytes = size_bytes
        self.items = items if items else []

    def get_friendly_size(self):
        from utils import format_bytes
        return format_bytes(self.size_bytes)

def get_appdata_definitions(profile_path):
    """
    Defines paths for curated settings and profiles relative to a user's profile path.
    """
    return {
        "Notepad++ Settings & Drafts": [
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Notepad++", "backup"),
                "type": "folder",
                "rel_path": "Notepad++/backup"
            },
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Notepad++", "config.xml"),
                "type": "file",
                "rel_path": "Notepad++/config.xml"
            }
        ],
        "Google Chrome Browser Profile": [
            {
                "path": os.path.join(profile_path, "AppData", "Local", "Google", "Chrome", "User Data", "Default"),
                "type": "folder",
                "rel_path": "Google/Chrome/User Data/Default"
            }
        ],
        "Microsoft Edge Browser Profile": [
            {
                "path": os.path.join(profile_path, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default"),
                "type": "folder",
                "rel_path": "Microsoft/Edge/User Data/Default"
            }
        ],
        "Mozilla Firefox Browser Profile": [
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles"),
                "type": "folder",
                "rel_path": "Mozilla/Firefox/Profiles"
            }
        ],
        "Microsoft Office Signatures & Templates": [
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Microsoft", "Signatures"),
                "type": "folder",
                "rel_path": "Microsoft/Signatures"
            },
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Microsoft", "Templates"),
                "type": "folder",
                "rel_path": "Microsoft/Templates"
            },
            {
                "path": os.path.join(profile_path, "Documents", "Outlook Files"),
                "type": "folder",
                "rel_path": "Documents/Outlook Files"
            }
        ],
        "VS Code Workspace & Extensions": [
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "Code", "User"),
                "type": "folder",
                "rel_path": "Code/User"
            },
            {
                "path": os.path.join(profile_path, ".vscode", "extensions"),
                "type": "folder",
                "rel_path": ".vscode/extensions"
            }
        ],
        "Discord Session Storage": [
            {
                "path": os.path.join(profile_path, "AppData", "Roaming", "discord", "Local Storage"),
                "type": "folder",
                "rel_path": "discord/Local Storage"
            }
        ]
    }

def calculate_item_size(item_path, item_type):
    """
    Calculates the size of a file or folder safely in bytes.
    """
    if not os.path.exists(item_path):
        return 0
        
    if item_type == 'file':
        try:
            return os.path.getsize(item_path)
        except OSError:
            return 0
            
    total_size = 0
    try:
        from utils import should_exclude_file_or_dir
        for root, dirs, files in os.walk(item_path):
            # Exclude folders early so walk doesn't recurse into them
            dirs[:] = [d for d in dirs if not should_exclude_file_or_dir(os.path.join(root, d))]
            for f in files:
                fp = os.path.join(root, f)
                if should_exclude_file_or_dir(fp):
                    continue
                try:
                    # Skip reparse points / symlinks to avoid infinite loops
                    from copy_engine import is_reparse_point
                    if not is_reparse_point(fp):
                        total_size += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        pass
    return total_size

def scan_profile_appdata(profile_path, status_callback=None):
    """
    Scans the given user profile path for active curated application data directories.
    Returns a dictionary: {app_name: AppDataInfo}
    """
    definitions = get_appdata_definitions(profile_path)
    discovered = {}
    
    for app_name, items in definitions.items():
        if status_callback:
            status_callback(f"Checking settings for {app_name}...")
            
        app_exists = False
        app_size = 0
        valid_items = []
        
        for item in items:
            path = item["path"]
            if os.path.exists(path):
                app_exists = True
                size = calculate_item_size(path, item["type"])
                app_size += size
                valid_items.append(item)
                
        if app_exists:
            discovered[app_name] = AppDataInfo(
                name=app_name,
                exists=True,
                size_bytes=app_size,
                items=valid_items
            )
            
    return discovered
