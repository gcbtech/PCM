import os
import re
import winreg
from utils import format_bytes

def get_steam_install_path():
    """
    Finds the Steam installation path from the Windows registry.
    """
    paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")
    ]
    for hkey, subkey, val_name in paths:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                val, _ = winreg.QueryValueEx(key, val_name)
                if val:
                    normalized = os.path.abspath(os.path.normpath(val))
                    if os.path.exists(normalized):
                        return normalized
        except Exception:
            continue
            
    # Fallback to default install locations
    default_paths = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam"
    ]
    for p in default_paths:
        if os.path.exists(p):
            return p
    return None

def parse_library_folders(steam_path):
    """
    Parses libraryfolders.vdf to find all Steam library paths.
    """
    libraries = [steam_path]
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return list(set(libraries))
        
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # Find all "path" "..." entries
        matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
        for m in matches:
            # Unescape path
            normalized = os.path.abspath(m.replace("\\\\", "\\"))
            if os.path.exists(normalized):
                libraries.append(normalized)
    except Exception as e:
        print(f"[Steam] Error parsing libraryfolders.vdf: {e}")
        
    return list(set(libraries))

def parse_acf(filepath):
    """
    Parses a Valve appmanifest .acf file to a flat key-value dictionary.
    """
    data = {}
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # Find double quoted key and value pairs on the same line or adjacent
        pairs = re.findall(r'"([^"]+)"\s+"([^"]*)"', content)
        for k, v in pairs:
            data[k.lower()] = v
    except Exception as e:
        print(f"[Steam] Error parsing {filepath}: {e}")
    return data

def detect_steam_games():
    """
    Detects installed Steam games.
    Returns:
        dict: { appid (str): { 'appid': str, 'name': str, 'size_bytes': int, 'manifest_path': str, 'common_path': str, 'installdir': str } }
    """
    games = {}
    steam_path = get_steam_install_path()
    if not steam_path:
        print("[Steam] Steam installation not found.")
        return games
        
    library_paths = parse_library_folders(steam_path)
    for lib in library_paths:
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.exists(steamapps):
            continue
            
        try:
            for entry in os.scandir(steamapps):
                if entry.is_file() and entry.name.lower().startswith("appmanifest_") and entry.name.lower().endswith(".acf"):
                    acf_path = entry.path
                    acf_data = parse_acf(acf_path)
                    
                    appid = acf_data.get("appid")
                    name = acf_data.get("name")
                    installdir = acf_data.get("installdir")
                    
                    if not appid or not name or not installdir:
                        continue
                        
                    # Filter out Steamworks Common Redistributables (AppID 228980) or similar tool-only/runtime packages
                    if appid == "228980" or "steamworks common" in name.lower() or "steamworks shared" in name.lower():
                        continue
                        
                    # Verify game directory exists in steamapps/common
                    common_dir = os.path.join(steamapps, "common", installdir)
                    if os.path.exists(common_dir) and os.path.isdir(common_dir):
                        # Extract size on disk, default to walking if missing or 0
                        size_str = acf_data.get("sizeondisk", "0")
                        try:
                            size_bytes = int(size_str)
                        except ValueError:
                            size_bytes = 0
                            
                        # If size_bytes is 0, let's walk the directory to get exact size
                        if size_bytes == 0:
                            for root, dirs, files in os.walk(common_dir):
                                for f in files:
                                    try:
                                        size_bytes += os.path.getsize(os.path.join(root, f))
                                    except Exception:
                                        pass
                                        
                        games[appid] = {
                            'appid': appid,
                            'name': name,
                            'installdir': installdir,
                            'size_bytes': size_bytes,
                            'manifest_path': acf_path,
                            'common_path': common_dir
                        }
        except Exception as e:
            print(f"[Steam] Error scanning library {lib}: {e}")
            
    return games
