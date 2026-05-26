import os
import json
import time

MANIFEST_FILENAME = "manifest.json"
CURRENT_VERSION = "1.4"

def create_manifest(drive_path, source_machine, source_users, total_size_bytes, steam_games=None, custom_items=None):
    """
    Writes manifest.json to the root of drive_path.
    
    source_users is a list of dicts:
    [
        {
            "username": "John",
            "folders": ["Desktop", "Documents", ...],
            "folder_sizes": {"Desktop": 1048576, ...},
            "browsers": ["Chrome", "Firefox"]
        }
    ]
    """
    manifest_path = os.path.join(drive_path, MANIFEST_FILENAME)
    
    data = {
        "pcm_version": CURRENT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_machine": source_machine,
        "source_users": source_users,
        "total_size_bytes": total_size_bytes
    }
    
    if steam_games:
        data["steam_games"] = steam_games
        
    if custom_items:
        data["custom_items"] = custom_items
    
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"Manifest written to {manifest_path}")
        return True
    except Exception as e:
        print(f"Error writing manifest: {e}")
        return False

def read_manifest(drive_path):
    """
    Reads manifest.json from drive_path and validates its structure.
    Returns parsed dictionary if valid, or None if invalid.
    """
    manifest_path = os.path.join(drive_path, MANIFEST_FILENAME)
    if not os.path.exists(manifest_path):
        return None
        
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Basic validation
        if "pcm_version" in data and "source_machine" in data and "source_users" in data:
            return data
    except Exception as e:
        print(f"Error reading manifest: {e}")
        
    return None

def is_pcm_drive(drive_path):
    """
    Checks if the drive_path has a valid PCM manifest file.
    """
    manifest = read_manifest(drive_path)
    return manifest is not None
