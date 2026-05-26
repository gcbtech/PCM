import os
import sys
import subprocess
import glob

creationflags = 0
if sys.platform == 'win32':
    creationflags = subprocess.CREATE_NO_WINDOW

def export_wifi_profiles(dest_dir):
    """
    Scans Windows Wi-Fi profiles under C:\ProgramData\Microsoft\Wlansvc\Profiles\Interfaces\
    and copies XML configuration files into dest_dir/wifi/.
    """
    print("[Settings] Exporting Wi-Fi profiles...")
    wifi_dest = os.path.join(dest_dir, "wifi")
    os.makedirs(wifi_dest, exist_ok=True)
    
    interfaces_path = r"C:\ProgramData\Microsoft\Wlansvc\Profiles\Interfaces"
    if not os.path.exists(interfaces_path):
        print("[Settings] WlanInterfaces directory not found (perhaps Wi-Fi is disabled/not present).")
        return False
        
    xml_files = glob.glob(os.path.join(interfaces_path, "**", "*.xml"), recursive=True)
    copied_count = 0
    
    for xml_path in xml_files:
        try:
            filename = os.path.basename(xml_path)
            dest_path = os.path.join(wifi_dest, filename)
            
            # Read and copy the XML file safely
            with open(xml_path, 'r', encoding='utf-8', errors='ignore') as src_f:
                content = src_f.read()
                
            with open(dest_path, 'w', encoding='utf-8') as dest_f:
                dest_f.write(content)
                
            copied_count += 1
        except Exception as e:
            print(f"[Settings] Error copying Wi-Fi profile {xml_path}: {e}")
            
    print(f"[Settings] Successfully exported {copied_count} Wi-Fi profiles.")
    return copied_count > 0

def export_personalization_settings(dest_dir):
    """
    Exports Control Panel, cursor, color, and system theme registry keys into .reg files.
    Also exports the active desktop wallpaper image.
    """
    print("[Settings] Exporting registry personalization settings...")
    reg_dest = os.path.join(dest_dir, "registry")
    os.makedirs(reg_dest, exist_ok=True)
    
    keys_to_export = {
        "desktop": r"HKCU\Control Panel\Desktop",
        "colors": r"HKCU\Control Panel\Colors",
        "cursors": r"HKCU\Control Panel\Cursors",
        "themes": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes"
    }
    
    exported_count = 0
    for name, key in keys_to_export.items():
        reg_file = os.path.join(reg_dest, f"{name}.reg")
        try:
            cmd = ["reg", "export", key, reg_file, "/y"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=creationflags)
            if res.returncode == 0:
                exported_count += 1
            else:
                print(f"[Settings] Failed to export {key}: {res.stderr}")
        except Exception as e:
            print(f"[Settings] Exception exporting key {key}: {e}")
            
    # Export wallpaper file
    try:
        import shutil
        appdata_roaming = os.environ.get('APPDATA')
        if appdata_roaming:
            wallpaper_src = os.path.join(appdata_roaming, "Microsoft", "Windows", "Themes", "TranscodedWallpaper")
            if os.path.exists(wallpaper_src):
                wallpaper_dst = os.path.join(dest_dir, "wallpaper.jpg")
                shutil.copy2(wallpaper_src, wallpaper_dst)
                print("[Settings] Successfully exported TranscodedWallpaper file.")
    except Exception as e:
        print(f"[Settings] Exception exporting wallpaper file: {e}")
            
    print(f"[Settings] Exported {exported_count} personalization registry keys.")
    return exported_count > 0

def restore_wifi_profiles(src_dir):
    """
    Imports Wi-Fi XML profiles using standard Windows netsh wlan utility.
    """
    wifi_src = os.path.join(src_dir, "wifi")
    if not os.path.exists(wifi_src):
        print("[Settings] No Wi-Fi profiles backup folder found to restore.")
        return False
        
    xml_files = glob.glob(os.path.join(wifi_src, "*.xml"))
    restored_count = 0
    
    for xml_path in xml_files:
        try:
            # Command: netsh wlan add profile filename="<path>" user=all
            cmd = ["netsh", "wlan", "add", "profile", f"filename={xml_path}", "user=all"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=creationflags)
            if res.returncode == 0:
                restored_count += 1
            else:
                print(f"[Settings] Failed to restore Wi-Fi profile {xml_path}: {res.stderr}")
        except Exception as e:
            print(f"[Settings] Exception restoring Wi-Fi profile {xml_path}: {e}")
            
    print(f"[Settings] Successfully restored {restored_count} Wi-Fi profiles.")
    return restored_count > 0

def restore_personalization_settings(src_dir):
    """
    Imports exported registry theme/control panel configuration files silently.
    Also restores and instantly updates the active desktop wallpaper.
    """
    reg_src = os.path.join(src_dir, "registry")
    if not os.path.exists(reg_src):
        print("[Settings] No personalization registry backup found to restore.")
        return False
        
    reg_files = glob.glob(os.path.join(reg_src, "*.reg"))
    restored_count = 0
    
    for reg_path in reg_files:
        try:
            # Command: reg import "<path>" or regedit /s "<path>"
            cmd = ["reg", "import", reg_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, creationflags=creationflags)
            if res.returncode == 0:
                restored_count += 1
            else:
                print(f"[Settings] Failed to import registry file {reg_path}: {res.stderr}")
        except Exception as e:
            print(f"[Settings] Exception importing registry file {reg_path}: {e}")
            
    # Restore wallpaper
    wallpaper_src = os.path.join(src_dir, "wallpaper.jpg")
    if os.path.exists(wallpaper_src):
        try:
            import shutil
            import ctypes
            user_profile = os.environ.get('USERPROFILE') or os.path.expanduser('~')
            pictures_dir = os.path.join(user_profile, "Pictures")
            os.makedirs(pictures_dir, exist_ok=True)
            wallpaper_dst = os.path.join(pictures_dir, "PCM_wallpaper.jpg")
            
            # Copy to user pictures
            shutil.copy2(wallpaper_src, wallpaper_dst)
            print(f"[Settings] Copied wallpaper to user pictures: {wallpaper_dst}")
            
            # Call SystemParametersInfoW: SPI_SETDESKWALLPAPER=20, SPIF_UPDATEINIFILE=0x01, SPIF_SENDCHANGE=0x02
            # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE = 3
            res = ctypes.windll.user32.SystemParametersInfoW(20, 0, wallpaper_dst, 3)
            print(f"[Settings] SystemParametersInfoW returned {res} for wallpaper change.")
        except Exception as e:
            print(f"[Settings] Exception restoring desktop wallpaper: {e}")
            
    print(f"[Settings] Successfully restored {restored_count} personalization keys.")
    return restored_count > 0
