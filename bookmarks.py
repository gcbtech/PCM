import os
import json
import sqlite3
import shutil
import glob

def get_appdata_paths(user_path):
    """Returns local and roaming appdata paths for a given user profile path."""
    local_appdata = os.path.join(user_path, 'AppData', 'Local')
    roaming_appdata = os.path.join(user_path, 'AppData', 'Roaming')
    return local_appdata, roaming_appdata

def find_chrome_bookmarks_files(user_path):
    """
    Finds all Chrome profile Bookmark files.
    Returns a list of dicts: {'profile_name': str, 'path': str}
    """
    local_appdata, _ = get_appdata_paths(user_path)
    chrome_data_dir = os.path.join(local_appdata, 'Google', 'Chrome', 'User Data')
    bookmark_files = []
    
    if os.path.exists(chrome_data_dir):
        # Scan profiles (Default, Profile 1, Profile 2, etc.)
        for root, dirs, files in os.walk(chrome_data_dir):
            # We only look at top-level profile folders, e.g., User Data\Default or User Data\Profile X
            rel_path = os.path.relpath(root, chrome_data_dir)
            parts = rel_path.split(os.sep)
            if len(parts) == 1:
                profile_name = parts[0]
                if profile_name in ['Default'] or profile_name.startswith('Profile '):
                    bm_path = os.path.join(root, 'Bookmarks')
                    if os.path.exists(bm_path):
                        bookmark_files.append({
                            'profile_name': profile_name,
                            'path': bm_path
                        })
            # Prevent deeply nested recursion
            if len(parts) > 1:
                dirs.clear()
    return bookmark_files

def find_edge_bookmarks_files(user_path):
    """
    Finds all Edge profile Bookmark files.
    Returns a list of dicts: {'profile_name': str, 'path': str}
    """
    local_appdata, _ = get_appdata_paths(user_path)
    edge_data_dir = os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data')
    bookmark_files = []
    
    if os.path.exists(edge_data_dir):
        for root, dirs, files in os.walk(edge_data_dir):
            rel_path = os.path.relpath(root, edge_data_dir)
            parts = rel_path.split(os.sep)
            if len(parts) == 1:
                profile_name = parts[0]
                if profile_name in ['Default'] or profile_name.startswith('Profile '):
                    bm_path = os.path.join(root, 'Bookmarks')
                    if os.path.exists(bm_path):
                        bookmark_files.append({
                            'profile_name': profile_name,
                            'path': bm_path
                        })
            if len(parts) > 1:
                dirs.clear()
    return bookmark_files

def find_firefox_profiles(user_path):
    """
    Finds all Firefox profile directories containing places.sqlite.
    Returns a list of dicts: {'profile_name': str, 'path': str}
    """
    _, roaming_appdata = get_appdata_paths(user_path)
    ff_profiles_dir = os.path.join(roaming_appdata, 'Mozilla', 'Firefox', 'Profiles')
    profiles = []
    
    if os.path.exists(ff_profiles_dir):
        try:
            for entry in os.scandir(ff_profiles_dir):
                if entry.is_dir():
                    sqlite_path = os.path.join(entry.path, 'places.sqlite')
                    if os.path.exists(sqlite_path):
                        profiles.append({
                            'profile_name': entry.name,
                            'path': entry.path
                        })
        except Exception:
            pass
    return profiles

def chrome_bookmarks_to_html(json_path, output_html_path):
    """Converts a Chrome/Edge Bookmarks JSON file to standard Netscape Bookmark HTML."""
    try:
        with open(json_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        
        html_lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            '<!-- This is an automatically generated file.',
            '     It will be read and classified by your browser. -->',
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>Bookmarks</TITLE>",
            "<H1>Bookmarks</H1>",
            "<DL><p>"
        ]
        
        def process_node(node, indent=4):
            space = " " * indent
            node_type = node.get("type")
            name = node.get("name", "")
            
            if node_type == "url":
                url = node.get("url", "")
                html_lines.append(f'{space}<DT><A HREF="{url}">{name}</A>')
            elif node_type == "folder":
                html_lines.append(f'{space}<DT><H3>{name}</H3>')
                html_lines.append(f'{space}<DL><p>')
                children = node.get("children", [])
                for child in children:
                    process_node(child, indent + 4)
                html_lines.append(f'{space}</DL><p>')

        roots = data.get("roots", {})
        for root_name in ["bookmark_bar", "other", "synced"]:
            if root_name in roots:
                root_node = roots[root_name]
                children = root_node.get("children", [])
                if children:
                    html_lines.append(f'    <DT><H3>{root_name.replace("_", " ").title()}</H3>')
                    html_lines.append('    <DL><p>')
                    for child in children:
                        process_node(child, 8)
                    html_lines.append('    </DL><p>')
                    
        html_lines.append("</DL><p>")
        
        os.makedirs(os.path.dirname(output_html_path), exist_ok=True)
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(html_lines))
        return True
    except Exception as e:
        print(f"Error converting Chrome bookmarks: {e}")
        return False

def firefox_bookmarks_to_html(ff_profile_path, output_html_path):
    """Converts a Firefox places.sqlite database to Netscape Bookmark HTML."""
    sqlite_path = os.path.join(ff_profile_path, 'places.sqlite')
    if not os.path.exists(sqlite_path):
        return False
        
    try:
        # Connect to SQLite DB. Since it might be locked, copy it to temp location first
        temp_db = output_html_path + ".tmp.db"
        shutil.copy2(sqlite_path, temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moz_bookmarks'")
        if not cursor.fetchone():
            conn.close()
            os.remove(temp_db)
            return False
            
        # Get bookmarks and folders
        # type 1 = url, type 2 = folder, type 3 = separator
        cursor.execute("""
            SELECT b.id, b.parent, b.title, b.type, p.url 
            FROM moz_bookmarks b 
            LEFT JOIN moz_places p ON b.fk = p.id
            ORDER BY b.parent, b.position
        """)
        rows = cursor.fetchall()
        conn.close()
        os.remove(temp_db)
        
        # Build index
        nodes = {}
        children = {} # parent_id -> list of node_ids
        
        for r in rows:
            node_id, parent, title, b_type, url = r
            if not title:
                title = url if url else "Folder"
            nodes[node_id] = {
                'id': node_id,
                'parent': parent,
                'title': title,
                'type': b_type,
                'url': url
            }
            if parent not in children:
                children[parent] = []
            children[parent].append(node_id)
            
        html_lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>Bookmarks</TITLE>",
            "<H1>Bookmarks</H1>",
            "<DL><p>"
        ]
        
        def render_tree(parent_id, indent=4):
            if parent_id not in children:
                return
            space = " " * indent
            for node_id in children[parent_id]:
                node = nodes[node_id]
                if node['type'] == 1: # URL
                    url = node['url'] or ""
                    title = node['title']
                    html_lines.append(f'{space}<DT><A HREF="{url}">{title}</A>')
                elif node['type'] == 2: # Folder
                    title = node['title']
                    # Skip root folder placeholders unless they have contents
                    if node_id in [1, 2, 3, 5]: # Firefox system roots (menu, toolbar, tags, unfiled)
                        render_tree(node_id, indent)
                    else:
                        html_lines.append(f'{space}<DT><H3>{title}</H3>')
                        html_lines.append(f'{space}<DL><p>')
                        render_tree(node_id, indent + 4)
                        html_lines.append(f'{space}</DL><p>')

        # Root parent in Firefox is typically 0, system folders are children of 1 (root) or 0
        # Let's render everything starting from 1 (menu/toolbar folders usually live here)
        render_tree(1, 4)
        # Also render children of parent=0 or 2, just in case
        for r_id in [0, 2, 3]:
            render_tree(r_id, 4)
            
        html_lines.append("</DL><p>")
        
        os.makedirs(os.path.dirname(output_html_path), exist_ok=True)
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(html_lines))
        return True
    except Exception as e:
        print(f"Error converting Firefox bookmarks: {e}")
        return False

def export_browser_bookmarks(user_path, dest_bookmarks_dir):
    """
    Finds and backs up bookmarks for Chrome, Edge, and Firefox.
    Stores raw files and generates universal HTML fallback files.
    """
    os.makedirs(dest_bookmarks_dir, exist_ok=True)
    summary = []
    
    # 1. Chrome Bookmarks
    chrome_bm = find_chrome_bookmarks_files(user_path)
    for bm in chrome_bm:
        profile = bm['profile_name']
        src = bm['path']
        
        # Raw Backup
        raw_dest_dir = os.path.join(dest_bookmarks_dir, 'Chrome', profile)
        os.makedirs(raw_dest_dir, exist_ok=True)
        raw_dest = os.path.join(raw_dest_dir, 'Bookmarks')
        try:
            shutil.copy2(src, raw_dest)
            # HTML export
            html_dest = os.path.join(dest_bookmarks_dir, 'Chrome', f'Chrome_Bookmarks_{profile}.html')
            chrome_bookmarks_to_html(src, html_dest)
            summary.append(f"Chrome ({profile})")
        except Exception:
            pass

    # 2. Edge Bookmarks
    edge_bm = find_edge_bookmarks_files(user_path)
    for bm in edge_bm:
        profile = bm['profile_name']
        src = bm['path']
        
        # Raw Backup
        raw_dest_dir = os.path.join(dest_bookmarks_dir, 'Edge', profile)
        os.makedirs(raw_dest_dir, exist_ok=True)
        raw_dest = os.path.join(raw_dest_dir, 'Bookmarks')
        try:
            shutil.copy2(src, raw_dest)
            # HTML export
            html_dest = os.path.join(dest_bookmarks_dir, 'Edge', f'Edge_Bookmarks_{profile}.html')
            chrome_bookmarks_to_html(src, html_dest)
            summary.append(f"Edge ({profile})")
        except Exception:
            pass

    # 3. Firefox Bookmarks
    ff_profiles = find_firefox_profiles(user_path)
    for prof in ff_profiles:
        profile = prof['profile_name']
        src_profile_dir = prof['path']
        src_sqlite = os.path.join(src_profile_dir, 'places.sqlite')
        
        # Raw Backup
        raw_dest_dir = os.path.join(dest_bookmarks_dir, 'Firefox', profile)
        os.makedirs(raw_dest_dir, exist_ok=True)
        raw_dest = os.path.join(raw_dest_dir, 'places.sqlite')
        try:
            shutil.copy2(src_sqlite, raw_dest)
            # HTML export
            html_dest = os.path.join(dest_bookmarks_dir, 'Firefox', f'Firefox_Bookmarks_{profile}.html')
            firefox_bookmarks_to_html(src_profile_dir, html_dest)
            summary.append(f"Firefox ({profile})")
        except Exception:
            pass
            
    return summary

def import_browser_bookmarks(source_bookmarks_dir, dest_user_path):
    """
    Restores browser bookmarks to the destination user profile.
    If the target browser profiles exist, attempts to overwrite/install raw bookmarks.
    Always places the HTML bookmark exports on the Desktop in a 'PCM Migrated Bookmarks' folder
    as a safe and convenient fallback.
    """
    desktop_fallback_dir = os.path.join(dest_user_path, 'Desktop', 'PCM Migrated Bookmarks')
    restored = []
    
    local_appdata, roaming_appdata = get_appdata_paths(dest_user_path)
    
    # 1. Chrome Restore
    chrome_backup_dir = os.path.join(source_bookmarks_dir, 'Chrome')
    if os.path.exists(chrome_backup_dir):
        # Look for HTML exports to copy to desktop
        html_files = glob.glob(os.path.join(chrome_backup_dir, '*.html'))
        if html_files:
            os.makedirs(desktop_fallback_dir, exist_ok=True)
            for h in html_files:
                shutil.copy2(h, desktop_fallback_dir)
                
        # Attempt raw overwrite if directory exists
        dest_chrome_dir = os.path.join(local_appdata, 'Google', 'Chrome', 'User Data')
        if os.path.exists(dest_chrome_dir):
            for entry in os.scandir(chrome_backup_dir):
                if entry.is_dir():
                    profile = entry.name
                    src_bm = os.path.join(entry.path, 'Bookmarks')
                    dest_profile_dir = os.path.join(dest_chrome_dir, profile)
                    if os.path.exists(dest_profile_dir) and os.path.exists(src_bm):
                        try:
                            shutil.copy2(src_bm, os.path.join(dest_profile_dir, 'Bookmarks'))
                            restored.append(f"Chrome ({profile})")
                        except Exception:
                            pass
                            
    # 2. Edge Restore
    edge_backup_dir = os.path.join(source_bookmarks_dir, 'Edge')
    if os.path.exists(edge_backup_dir):
        html_files = glob.glob(os.path.join(edge_backup_dir, '*.html'))
        if html_files:
            os.makedirs(desktop_fallback_dir, exist_ok=True)
            for h in html_files:
                shutil.copy2(h, desktop_fallback_dir)
                
        dest_edge_dir = os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data')
        if os.path.exists(dest_edge_dir):
            for entry in os.scandir(edge_backup_dir):
                if entry.is_dir():
                    profile = entry.name
                    src_bm = os.path.join(entry.path, 'Bookmarks')
                    dest_profile_dir = os.path.join(dest_edge_dir, profile)
                    if os.path.exists(dest_profile_dir) and os.path.exists(src_bm):
                        try:
                            shutil.copy2(src_bm, os.path.join(dest_profile_dir, 'Bookmarks'))
                            restored.append(f"Edge ({profile})")
                        except Exception:
                            pass

    # 3. Firefox Restore
    firefox_backup_dir = os.path.join(source_bookmarks_dir, 'Firefox')
    if os.path.exists(firefox_backup_dir):
        html_files = glob.glob(os.path.join(firefox_backup_dir, '*.html'))
        if html_files:
            os.makedirs(desktop_fallback_dir, exist_ok=True)
            for h in html_files:
                shutil.copy2(h, desktop_fallback_dir)
                
        dest_ff_dir = os.path.join(roaming_appdata, 'Mozilla', 'Firefox', 'Profiles')
        if os.path.exists(dest_ff_dir):
            # Match profiles or copy to default profiles
            for entry in os.scandir(firefox_backup_dir):
                if entry.is_dir():
                    src_sqlite = os.path.join(entry.path, 'places.sqlite')
                    if os.path.exists(src_sqlite):
                        # Copy to all active Firefox profiles since profiles have dynamic hashes (e.g. xxxxxxxx.default-release)
                        try:
                            for dest_prof in os.scandir(dest_ff_dir):
                                if dest_prof.is_dir():
                                    shutil.copy2(src_sqlite, os.path.join(dest_prof.path, 'places.sqlite'))
                            restored.append("Firefox")
                        except Exception:
                            pass
                            
    # Create a simple readme on Desktop inside the folder
    if os.path.exists(desktop_fallback_dir):
        readme_path = os.path.join(desktop_fallback_dir, 'README.txt')
        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write("PCM (PC Mover) Bookmarks Migrated\n")
                f.write("=================================\n\n")
                f.write("We have migrated your browser bookmarks to this folder as a universal fallback.\n\n")
                f.write("If the automated import failed to appear in your browser, you can manually import them:\n")
                f.write("1. Open your browser (Chrome, Edge, Firefox, etc.)\n")
                f.write("2. Open the Bookmarks / Favorites settings menu.\n")
                f.write("3. Select 'Import Bookmarks and Settings' or 'Import Bookmarks'.\n")
                f.write("4. Choose 'Bookmarks HTML File' or 'From HTML file' as the source.\n")
                f.write("5. Select one of the HTML files in this folder (e.g., Chrome_Bookmarks_Default.html).\n")
                f.write("\nThank you for using PCM (PC Mover)!\n")
        except Exception:
            pass

    return restored, desktop_fallback_dir if os.path.exists(desktop_fallback_dir) else None
