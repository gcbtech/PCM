import os
import sys
import threading
import time
import customtkinter as ctk
from gui.components import (
    PremiumCard, HeaderPanel, ScrollableFolderList, ScrollableSteamGamesList, ScrollableCustomItemList, AppFonts,
    ACCENT_BLUE, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS_GREEN, WARNING_YELLOW, DANGER_RED,
    BG_COLOR, BORDER_COLOR, CARD_COLOR, ScrollableSettingsList, ScrollableAppDataList
)
import scanner
import drive_ops
import bookmarks
import copy_engine
import manifest
from utils import format_bytes

def show_export_welcome_screen(app):
    app.set_title_subtitle("Export", "Welcome")
    app.clear_container()
    
    # Header
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Export Files", subtitle="Let's prepare your files for migration")
    header.pack(fill="x")
    
    # Body Card
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    welcome_lbl = ctk.CTkLabel(
        card, 
        text="Choose User Account(s) to Migrate", 
        font=AppFonts.HEADING_MEDIUM,
        text_color=TEXT_PRIMARY
    )
    welcome_lbl.pack(pady=(25, 10))
    
    desc_lbl = ctk.CTkLabel(
        card, 
        text="PCM will scan your selected profile folders (Desktop, Documents, Downloads, Photos, etc.)\n"
             "and browser bookmarks to transfer them to your new PC.\n"
             "Check all accounts you want to migrate.",
        font=AppFonts.BODY,
        text_color=TEXT_SECONDARY,
        justify="center"
    )
    desc_lbl.pack(pady=(0, 15))
    
    # Scanning profiles
    app.user_profiles = scanner.scan_user_profiles()
    
    if len(app.user_profiles) <= 3:
        # Use standard Frame to avoid showing an unnecessary, inactive scrollbar
        checkbox_frame = ctk.CTkFrame(card, fg_color="transparent")
    else:
        # Use ScrollableFrame for systems with many user profiles
        checkbox_frame = ctk.CTkScrollableFrame(card, fg_color="transparent", height=140)
    checkbox_frame.pack(pady=5, padx=20, fill="x")
    
    check_vars = {}  # username -> BooleanVar
    
    if len(app.user_profiles) == 0:
        error_lbl = ctk.CTkLabel(card, text="No active user profiles detected on this machine.",
                                 text_color=DANGER_RED, font=AppFonts.BODY_BOLD)
        error_lbl.pack(pady=10)
        start_btn_state = "disabled"
    else:
        for profile in app.user_profiles:
            var = ctk.BooleanVar(value=True if len(app.user_profiles) == 1 else False)
            check_vars[profile.username] = var
            chk = ctk.CTkCheckBox(
                checkbox_frame,
                text=f"  {profile.username}  —  {profile.path}",
                variable=var,
                font=AppFonts.BODY_BOLD,
                text_color=TEXT_PRIMARY,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE,
                checkmark_color=TEXT_PRIMARY
            )
            chk.pack(anchor="w", pady=4)
        start_btn_state = "normal"

    def proceed_to_scan():
        # Collect checked profiles
        app.selected_profiles = [p for p in app.user_profiles if check_vars.get(p.username, ctk.BooleanVar()).get()]
        if not app.selected_profiles:
            return  # Nothing selected — ignore
        app.selected_profile = app.selected_profiles[0]  # backward compat
        show_scanning_loading_screen(app)
        
    start_btn = ctk.CTkButton(
        card, 
        text="Scan My Files", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        state=start_btn_state,
        command=proceed_to_scan,
        height=40,
        width=200
    )
    start_btn.pack(pady=(20, 20))
    
    # Manual Mode Switch Override Link
    switch_btn = ctk.CTkButton(
        app.container,
        text="Already have a PCM drive? Switch to Import Mode →",
        font=AppFonts.SMALL,
        fg_color="transparent",
        hover=False,
        text_color=ACCENT_BLUE,
        cursor="hand2",
        command=app.switch_to_import_mode
    )
    switch_btn.pack(pady=5)

    from gui.network_view import show_method_selection
    back_btn = ctk.CTkButton(
        app.container,
        text="← Back to Transfer Method Selection",
        font=AppFonts.SMALL,
        fg_color="transparent",
        hover=False,
        text_color=TEXT_SECONDARY,
        cursor="hand2",
        command=lambda: show_method_selection(app)
    )
    back_btn.pack(pady=5)

def show_scanning_loading_screen(app):
    app.set_title_subtitle("Export", "Scanning")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Export Files", subtitle="Scanning files and folders")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    user_count = len(app.selected_profiles)
    scan_target = f"{user_count} account(s)" if user_count > 1 else (app.selected_profiles[0].username if app.selected_profiles else "profile")
    lbl = ctk.CTkLabel(card, text=f"Analyzing Profile Folders for {scan_target}...",
                       font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    lbl.pack(pady=(80, 20))
    
    progress = ctk.CTkProgressBar(card, width=300, fg_color=BG_COLOR, progress_color=ACCENT_BLUE)
    progress.pack(pady=10)
    progress.set(0)
    progress.start()
    
    sub_lbl = ctk.CTkLabel(card, text="Preparing to scan folders...", font=AppFonts.BODY, text_color=TEXT_SECONDARY)
    sub_lbl.pack(pady=10)
    
    def update_status(text):
        app.after_idle(lambda: sub_lbl.configure(text=text))
        
    def run_scan():
        import traceback
        running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        try:
            app.all_users_folders_info = {}
            for profile in app.selected_profiles:
                app.after_idle(lambda u=profile.username: update_status(f"Scanning {u}..."))
                fi = scanner.scan_profile_folders(profile.path, status_callback=update_status)
                app.all_users_folders_info[profile.username] = fi

            # Aggregate folder info for the checklist view
            # Combine sizes across all selected users
            merged = {}
            for username, fi in app.all_users_folders_info.items():
                for fname, finfo in fi.items():
                    if fname not in merged:
                        merged[fname] = scanner.FolderInfo(fname, finfo.path, finfo.exists,
                                                           finfo.size_bytes, finfo.file_count)
                    else:
                        merged[fname].size_bytes += finfo.size_bytes
                        merged[fname].file_count += finfo.file_count
                        if not merged[fname].exists and finfo.exists:
                            merged[fname].exists = True
            app.folders_info = merged
            
            # Scan and aggregate AppData
            from appdata_scanner import scan_profile_appdata, AppDataInfo
            app.all_users_appdata_info = {}
            for profile in app.selected_profiles:
                app.after_idle(lambda u=profile.username: update_status(f"Scanning AppData for {u}..."))
                ad = scan_profile_appdata(profile.path, status_callback=update_status)
                app.all_users_appdata_info[profile.username] = ad
                
            merged_appdata = {}
            for username, ad_dict in app.all_users_appdata_info.items():
                for app_name, info in ad_dict.items():
                    if app_name not in merged_appdata:
                        merged_appdata[app_name] = AppDataInfo(app_name, info.exists, info.size_bytes, info.items.copy())
                    else:
                        merged_appdata[app_name].size_bytes += info.size_bytes
                        if info.exists and not merged_appdata[app_name].exists:
                            merged_appdata[app_name].exists = True
                        merged_appdata[app_name].items.extend(info.items)
            app.appdata_info = merged_appdata

            # Detect Steam games
            import steam_ops
            app.after_idle(lambda: update_status("Detecting Steam games..."))
            app.steam_games = steam_ops.detect_steam_games()
            
            # Proceed to folder result view
            app.after(500, lambda: show_scan_results_screen(app))
        except Exception as e:
            tb_str = traceback.format_exc()
            print(f"Exception during scan:\n{tb_str}")
            try:
                desktop = os.path.join(app.selected_profiles[0].path, 'Desktop')
                log_file = os.path.join(desktop, "PCM_Scan_Debug_Error.txt")
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write("PCM (PC Mover) Scan Error Diagnosis Log\n")
                    f.write("========================================\n\n")
                    f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Error: {e}\n\nTraceback details:\n{tb_str}")
            except Exception:
                pass
            app.after_idle(lambda: show_error_screen(
                app, 
                "Scanning Encountered an Error", 
                f"An unhandled error occurred during file scanning:\n\n{str(e)}\n\n"
                "A diagnostic debug log has been saved to your Desktop."
            ))
        
    threading.Thread(target=run_scan, daemon=True).start()

def show_scan_results_screen(app):
    print(f"[Debug] show_scan_results_screen: app.folders_info keys: {list(app.folders_info.keys()) if app.folders_info else 'None'}")
    print(f"[Debug] show_scan_results_screen: app.steam_games keys: {list(app.steam_games.keys()) if hasattr(app, 'steam_games') and app.steam_games else 'None'}")
    app.set_title_subtitle("Export", "Configure")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Export Files", subtitle="Configure files and target drive")
    header.pack(fill="x")
    
    # Outer frame to arrange folder list and drive selection
    body = ctk.CTkFrame(app.container, fg_color="transparent")
    body.pack(fill="both", expand=True, pady=(0, 10))
    
    body.columnconfigure(0, weight=3) # Tabbed Checklist
    body.columnconfigure(1, weight=2) # Drive Selection Panel
    body.rowconfigure(0, weight=1)    # Ensure both panels expand vertically to fill the window height
    
    # Left side: CTkTabview for Folder and Steam checklists
    tabview = ctk.CTkTabview(
        body, 
        fg_color=CARD_COLOR,
        segmented_button_selected_color=ACCENT_BLUE,
        segmented_button_selected_hover_color=ACCENT_BLUE,
        segmented_button_unselected_hover_color=BG_COLOR,
        border_color=BORDER_COLOR,
        border_width=1,
        corner_radius=12
    )
    tabview.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    
    tabview.add("Personal Folders")
    tabview.add("Steam Games")
    tabview.add("Windows Settings")
    tabview.add("AppData Preferences")
    tabview.add("Custom Items")
    
    # Grid checklists inside tabs to match the tab frame's default grid geometry manager
    folder_checklist = ScrollableFolderList(tabview.tab("Personal Folders"), app.folders_info, border_width=0, corner_radius=0)
    folder_checklist.grid(row=0, column=0, sticky="nsew")
    tabview.tab("Personal Folders").grid_rowconfigure(0, weight=1)
    tabview.tab("Personal Folders").grid_columnconfigure(0, weight=1)
    
    steam_checklist = ScrollableSteamGamesList(tabview.tab("Steam Games"), getattr(app, 'steam_games', {}), border_width=0, corner_radius=0)
    steam_checklist.grid(row=0, column=0, sticky="nsew")
    tabview.tab("Steam Games").grid_rowconfigure(0, weight=1)
    tabview.tab("Steam Games").grid_columnconfigure(0, weight=1)

    settings_checklist = ScrollableSettingsList(tabview.tab("Windows Settings"), border_width=0, corner_radius=0)
    settings_checklist.grid(row=0, column=0, sticky="nsew")
    tabview.tab("Windows Settings").grid_rowconfigure(0, weight=1)
    tabview.tab("Windows Settings").grid_columnconfigure(0, weight=1)

    appdata_checklist = ScrollableAppDataList(tabview.tab("AppData Preferences"), getattr(app, 'appdata_info', {}), border_width=0, corner_radius=0)
    appdata_checklist.grid(row=0, column=0, sticky="nsew")
    tabview.tab("AppData Preferences").grid_rowconfigure(0, weight=1)
    tabview.tab("AppData Preferences").grid_columnconfigure(0, weight=1)

    # Setup Custom Items checklist and controls
    custom_checklist = None
    
    def remove_custom_item(path):
        app.custom_items = [item for item in app.custom_items if item['path'] != path]
        refresh_custom_items_list()
        
    def add_custom_folder():
        from tkinter import filedialog, messagebox
        app.update()
        path = filedialog.askdirectory(title="Select Custom Folder to Migrate")
        if not path:
            return
            
        path = os.path.normpath(path)
        if any(item['path'] == path for item in app.custom_items):
            messagebox.showinfo("Already Added", "This folder has already been added to the custom migration list.")
            return
            
        confirm = messagebox.askyesno(
            "⚠️ PCM Custom Migration Warning",
            "You are selecting a folder that is not normally moved by PCM.\n\n"
            "PCM cannot guarantee that manually selected programs will function correctly on the new PC "
            "because they often depend on registry entries, user keys, and drivers that are not selected.\n\n"
            "Do you understand this risk and wish to proceed?",
            icon="warning"
        )
        if not confirm:
            return
            
        item_entry = {
            'path': path,
            'type': 'folder',
            'size_bytes': 0,
            'calculating': True
        }
        app.custom_items.append(item_entry)
        refresh_custom_items_list()
        
        def calc_worker():
            total_size = 0
            try:
                for root, dirs, files in os.walk(path):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except OSError:
                            pass
            except Exception:
                pass
            item_entry['size_bytes'] = total_size
            item_entry['calculating'] = False
            app.after_idle(refresh_custom_items_list)
            
        threading.Thread(target=calc_worker, daemon=True).start()

    def add_custom_files():
        from tkinter import filedialog, messagebox
        app.update()
        files = filedialog.askopenfilenames(title="Select Custom Files to Migrate")
        if not files:
            return
            
        new_files = []
        for fp in files:
            normalized = os.path.normpath(fp)
            if not any(item['path'] == normalized for item in app.custom_items):
                new_files.append(normalized)
                
        if not new_files:
            messagebox.showinfo("Already Added", "Selected files have already been added to the custom migration list.")
            return
            
        confirm = messagebox.askyesno(
            "⚠️ PCM Custom Migration Warning",
            "You are selecting files that are not normally moved by PCM.\n\n"
            "PCM cannot guarantee that manually selected files/programs will function correctly on the new PC "
            "because they often depend on registry entries, user keys, and drivers that are not selected.\n\n"
            "Do you understand this risk and wish to proceed?",
            icon="warning"
        )
        if not confirm:
            return
            
        for fp in new_files:
            item_entry = {
                'path': fp,
                'type': 'file',
                'size_bytes': 0,
                'calculating': True
            }
            app.custom_items.append(item_entry)
            
            def calc_file_worker(entry=item_entry, path=fp):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                entry['size_bytes'] = size
                entry['calculating'] = False
                app.after_idle(refresh_custom_items_list)
                
            threading.Thread(target=calc_file_worker, daemon=True).start()
            
        refresh_custom_items_list()

    def refresh_custom_items_list():
        nonlocal custom_checklist
        if custom_checklist:
            custom_checklist.destroy()
            
        custom_checklist = ScrollableCustomItemList(
            tabview.tab("Custom Items"),
            app.custom_items,
            remove_item_callback=remove_custom_item,
            border_width=0,
            corner_radius=0
        )
        custom_checklist.grid(row=0, column=0, sticky="nsew")
        update_size_estimate()

    # Layout for Custom Items Tab: Checklist in row 0, buttons in row 1
    tabview.tab("Custom Items").grid_rowconfigure(0, weight=1)
    tabview.tab("Custom Items").grid_rowconfigure(1, weight=0)
    tabview.tab("Custom Items").grid_columnconfigure(0, weight=1)
    
    # Custom items action buttons
    btn_frame = ctk.CTkFrame(tabview.tab("Custom Items"), fg_color="transparent")
    btn_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 10))
    btn_frame.columnconfigure(0, weight=1)
    btn_frame.columnconfigure(1, weight=1)
    
    add_folder_btn = ctk.CTkButton(
        btn_frame,
        text="📁 Add Custom Folder",
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=add_custom_folder
    )
    add_folder_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
    
    add_file_btn = ctk.CTkButton(
        btn_frame,
        text="📄 Add Custom Files",
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=add_custom_files
    )
    add_file_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")
    
    # Right side: Target drive options Card
    drive_card = PremiumCard(body)
    drive_card.grid(row=0, column=1, sticky="nsew")
    drive_card.columnconfigure(0, weight=1)
    
    title_lbl = ctk.CTkLabel(drive_card, text="Target USB/Flash Drive", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    title_lbl.pack(pady=(20, 15), padx=10)
    
    drive_letter_var = ctk.StringVar()
    detected_drives = []
    
    drive_dropdown = None
    warning_lbl = None
    
    size_summary_lbl = ctk.CTkLabel(drive_card, text="Selected: 0.00 B", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    size_summary_lbl.pack(pady=5)

    def update_size_estimate():
        checked = folder_checklist.get_selected_folders()
        total_bytes = 0
        for name in checked:
            info = app.folders_info.get(name)
            if info:
                total_bytes += info.size_bytes
                
        # Steam games size
        selected_games = steam_checklist.get_selected_games()
        for appid in selected_games:
            game = app.steam_games.get(appid)
            if game:
                total_bytes += game['size_bytes']
                
        # Custom items size
        for item in app.custom_items:
            total_bytes += item['size_bytes']

        # Settings size
        selected_settings = settings_checklist.get_selected_settings()
        for name in selected_settings:
            data = settings_checklist.checkboxes.get(name)
            if data:
                total_bytes += data['size_bytes']

        # AppData size
        selected_apps = appdata_checklist.get_selected_apps()
        for name in selected_apps:
            info = app.appdata_info.get(name)
            if info:
                total_bytes += info.size_bytes
                
        # Buffer of 50MB or 5% overhead for bookmarks + PCM executable
        total_bytes += int(total_bytes * 0.05) + (50 * 1024 * 1024)
        app.migration_size_bytes = total_bytes
        
        size_str = format_bytes(total_bytes)
        size_summary_lbl.configure(text=f"Estimate Required:  {size_str}")
        check_drive_suitability()
        
    # Hook checkbox toggles to recalculate sizes
    for item in folder_checklist.checkboxes.values():
        item['checkbox'].configure(command=update_size_estimate)
        
    for item in steam_checklist.checkboxes.values():
        item['checkbox'].configure(command=update_size_estimate)

    for item in settings_checklist.checkboxes.values():
        item['checkbox'].configure(command=update_size_estimate)

    for item in appdata_checklist.checkboxes.values():
        item['checkbox'].configure(command=update_size_estimate)
        
    folder_checklist.on_toggle_callback = update_size_estimate
    steam_checklist.on_toggle_callback = update_size_estimate
    settings_checklist.on_toggle_callback = update_size_estimate
    appdata_checklist.on_toggle_callback = update_size_estimate
        
    def _drive_display_name(d):
        """Build a human-readable dropdown label for a physical disk."""
        total_space = format_bytes(d['total_bytes'])
        letters = d.get('letters', [])
        letters_str = ", ".join(letters) if letters else "No Partitions"
        return f"Disk {d['disk_index']} ({d['label']}) — {total_space} {d['type_desc']} [{letters_str}]"

    def scan_drives():
        nonlocal detected_drives
        detected_drives = drive_ops.list_removable_drives()
        
        values = [_drive_display_name(d) for d in detected_drives]
            
        if not values:
            drive_letter_var.set("No drive detected (Preview Mode)")
            if drive_dropdown:
                drive_dropdown.configure(
                    values=["No drive detected (Preview Mode)"], 
                    state="disabled",
                    fg_color=BORDER_COLOR,
                    button_color=BORDER_COLOR
                )
            app.selected_drive = None
        else:
            drive_letter_var.set(values[0])
            if drive_dropdown:
                drive_dropdown.configure(
                    values=values, 
                    state="normal",
                    fg_color=ACCENT_BLUE,
                    button_color=ACCENT_BLUE
                )
            app.selected_drive = detected_drives[0]
            
        update_size_estimate()

    def on_drive_select(choice):
        for d in detected_drives:
            if choice == _drive_display_name(d):
                app.selected_drive = d
                break
        check_drive_suitability()
        
    # Drive drop down
    drive_sel_frame = ctk.CTkFrame(drive_card, fg_color="transparent")
    drive_sel_frame.pack(pady=10, padx=10, fill="x")
    
    drive_dropdown = ctk.CTkOptionMenu(
        drive_sel_frame, 
        values=["Scanning drives..."], 
        variable=drive_letter_var, 
        command=on_drive_select,
        fg_color=ACCENT_BLUE,
        button_color=ACCENT_BLUE,
        dropdown_fg_color=CARD_COLOR,
        dropdown_hover_color=ACCENT_BLUE
    )
    drive_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5))
    
    refresh_btn = ctk.CTkButton(
        drive_sel_frame, 
        text="↻", 
        width=35, 
        fg_color=BORDER_COLOR, 
        hover_color=ACCENT_BLUE,
        command=scan_drives
    )
    refresh_btn.pack(side="right")
    
    warning_lbl = ctk.CTkLabel(
        drive_card, 
        text="Please insert a USB drive", 
        font=AppFonts.SMALL, 
        text_color=WARNING_YELLOW, 
        justify="center"
    )
    warning_lbl.pack(pady=10, padx=10)
    
    def check_drive_suitability():
        checked = folder_checklist.get_selected_folders()
        checked_games = steam_checklist.get_selected_games()
        checked_settings = settings_checklist.get_selected_settings()
        checked_apps = appdata_checklist.get_selected_apps()
        if not checked and not checked_games and not app.custom_items and not checked_settings and not checked_apps:
            warning_lbl.configure(text="⚠️ Select at least one item to move.", text_color=WARNING_YELLOW)
            start_btn.configure(state="disabled", fg_color=BORDER_COLOR)
            return
            
        if not app.selected_drive:
            warning_lbl.configure(text="ℹ️ PREVIEW MODE:\nPlug in a USB drive to export files.\nShowing estimates only.", text_color=ACCENT_BLUE)
            start_btn.configure(state="disabled", text="Drive Required", fg_color=BORDER_COLOR)
            return
            
        # Check capacity
        req_space = app.migration_size_bytes
        total_space = app.selected_drive['total_bytes']
        
        if req_space > total_space:
            size_diff = format_bytes(req_space - total_space)
            warning_lbl.configure(text=f"❌ NOT ENOUGH SPACE:\nDrive is too small by {size_diff}.", text_color=DANGER_RED)
            start_btn.configure(state="disabled", text="Drive Too Small", fg_color=BORDER_COLOR)
        else:
            warning_lbl.configure(text="✓ Drive is ready.\nFormatting is required.", text_color=SUCCESS_GREEN)
            start_btn.configure(state="normal", text="Start Migration", fg_color=ACCENT_BLUE)
 
    def proceed_to_confirm():
        app.selected_folders = folder_checklist.get_selected_folders()
        app.selected_games = steam_checklist.get_selected_games()
        app.selected_settings = settings_checklist.get_selected_settings()
        app.selected_apps = appdata_checklist.get_selected_apps()
        show_format_warning_screen(app)

    back_btn = ctk.CTkButton(
        drive_card,
        text="← Back to Welcome",
        font=AppFonts.BODY_BOLD,
        fg_color=BORDER_COLOR,
        hover_color=ACCENT_BLUE,
        command=lambda: show_export_welcome_screen(app),
        height=35
    )
    back_btn.pack(side="bottom", fill="x", pady=(0, 20), padx=20)
    
    start_btn = ctk.CTkButton(
        drive_card, 
        text="Start Migration", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=proceed_to_confirm,
        height=40
    )
    start_btn.pack(side="bottom", fill="x", pady=(20, 10), padx=20)
    
    # Render the initial custom items list
    refresh_custom_items_list()
    
    # Trigger initial scan
    scan_drives()

def show_format_warning_screen(app):
    app.set_title_subtitle("Export", "Warning")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Format Warning", subtitle="Destructive operation confirmation")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    warn_icon = ctk.CTkLabel(card, text="⚠️", font=("Segoe UI", 48, "normal"), text_color=WARNING_YELLOW)
    warn_icon.pack(pady=(20, 10))
    
    title_lbl = ctk.CTkLabel(card, text="WARNING: Drive Formatting Required!", font=AppFonts.HEADING_MEDIUM, text_color=DANGER_RED)
    title_lbl.pack(pady=5)
    
    drive = app.selected_drive
    letters = drive.get('letters', [])
    letters_str = ", ".join(letters) if letters else "No Partitions"
    desc_str = f"Disk {drive['disk_index']}  |  Label: '{drive['label']}'  |  Type: {drive['type_desc']}  |  Partitions: [{letters_str}]"
    
    info_lbl = ctk.CTkLabel(
        card, 
        text=f"PCM (PC Mover) must format the target drive before copying files to guarantee NTFS reliability.\n\n"
             f"{desc_str}\n\n"
             "ALL existing files on this drive will be PERMANENTLY DELETED.",
        font=AppFonts.BODY,
        text_color=TEXT_PRIMARY,
        justify="center"
    )
    info_lbl.pack(pady=20, padx=20)
    
    chk_var = ctk.StringVar(value="off")
    
    def on_check():
        if chk_var.get() == "on":
            format_btn.configure(state="normal", fg_color=DANGER_RED, hover_color=DANGER_RED)
        else:
            format_btn.configure(state="disabled", fg_color=BORDER_COLOR)

    chk = ctk.CTkCheckBox(
        card, 
        text="I understand that formatting will erase all data currently on this drive", 
        font=AppFonts.BODY_BOLD,
        text_color=TEXT_PRIMARY,
        variable=chk_var,
        onvalue="on",
        offvalue="off",
        command=on_check,
        checkmark_color=TEXT_PRIMARY,
        fg_color=DANGER_RED,
        hover_color=DANGER_RED
    )
    chk.pack(pady=10)
    
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(side="bottom", pady=25)
    
    back_btn = ctk.CTkButton(
        btn_frame, 
        text="Go Back", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR, 
        hover_color=ACCENT_BLUE,
        command=lambda: show_scan_results_screen(app),
        width=120
    )
    back_btn.pack(side="left", padx=10)
    
    def start_export_thread():
        show_progress_screen(app)
        
    format_btn = ctk.CTkButton(
        btn_frame, 
        text="Format & Export", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR,
        state="disabled",
        command=start_export_thread,
        width=180
    )
    format_btn.pack(side="right", padx=10)

def show_progress_screen(app):
    app.set_title_subtitle("Export", "Progress")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Exporting", subtitle="Moving your files to the transport drive...")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    op_title = ctk.CTkLabel(card, text="Preparing migration...", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    op_title.pack(pady=(30, 10))
    
    progress = ctk.CTkProgressBar(card, width=450, fg_color=BG_COLOR, progress_color=ACCENT_BLUE)
    progress.pack(pady=10)
    progress.set(0.0)
    
    percent_lbl = ctk.CTkLabel(card, text="0% completed (0.00 B / 0.00 B)", font=AppFonts.BODY, text_color=TEXT_SECONDARY)
    percent_lbl.pack(pady=5)

    speed_lbl = ctk.CTkLabel(card, text="Speed: —", font=AppFonts.SMALL, text_color=TEXT_SECONDARY)
    speed_lbl.pack(pady=2)

    eta_lbl = ctk.CTkLabel(card, text="ETA: —", font=AppFonts.SMALL, text_color=TEXT_SECONDARY)
    eta_lbl.pack(pady=2)
    
    detail_lbl = ctk.CTkLabel(card, text="", font=AppFonts.SMALL, text_color=TEXT_SECONDARY, justify="center")
    detail_lbl.pack(pady=15, padx=20)
    
    cancel_btn = ctk.CTkButton(card, text="Cancel", font=AppFonts.BODY_BOLD, fg_color=BORDER_COLOR, hover_color=DANGER_RED)
    cancel_btn.pack(side="bottom", pady=25)
    
    # State tracker for cancel
    engine = copy_engine.CopyEngine(conflict_pref="replace")
    
    def on_cancel():
        engine.cancel()
        cancel_btn.configure(state="disabled", text="Cancelling...")
        
    cancel_btn.configure(command=on_cancel)

    # Speed / ETA tracking shared state
    _speed_state = {'last_bytes': 0, 'last_time': time.monotonic()}
    
    def progress_callback(file_path, bytes_just_copied, total_bytes_copied, total_files_copied):
        total_req = app.migration_size_bytes
        if total_req > 0:
            fraction = min(1.0, total_bytes_copied / total_req)
        else:
            fraction = 1.0
            
        percent = int(fraction * 100)
        curr_str = format_bytes(total_bytes_copied)
        req_str = format_bytes(total_req)
        filename = os.path.basename(file_path)

        # Compute rolling speed every callback
        now = time.monotonic()
        elapsed = now - _speed_state['last_time']
        delta_bytes = total_bytes_copied - _speed_state['last_bytes']
        if elapsed >= 0.5 and delta_bytes > 0:
            speed_bps = delta_bytes / elapsed
            _speed_state['last_bytes'] = total_bytes_copied
            _speed_state['last_time'] = now
            speed_str = f"Speed: {format_bytes(speed_bps)}/s"
            remaining = total_req - total_bytes_copied
            eta_secs = remaining / speed_bps if speed_bps > 0 else 0
            if eta_secs < 60:
                eta_str = f"ETA: {int(eta_secs)}s"
            elif eta_secs < 3600:
                eta_str = f"ETA: {int(eta_secs // 60)}m {int(eta_secs % 60)}s"
            else:
                eta_str = f"ETA: {int(eta_secs // 3600)}h {int((eta_secs % 3600) // 60)}m"
            app.after_idle(lambda ss=speed_str: speed_lbl.configure(text=ss))
            app.after_idle(lambda es=eta_str: eta_lbl.configure(text=es))
        
        app.after_idle(lambda: progress.set(fraction))
        app.after_idle(lambda: percent_lbl.configure(text=f"{percent}% completed ({curr_str} / {req_str})"))
        app.after_idle(lambda: detail_lbl.configure(text=f"Copying file: ...\\{filename}"))

    # Connect progress callback
    engine.progress_callback = progress_callback
    
    def worker():
        drive = app.selected_drive
        disk_index = drive['disk_index']
        
        # Step 1: Format entire physical disk via diskpart
        app.after_idle(lambda: op_title.configure(text="Formatting Drive..."))
        app.after_idle(lambda: detail_lbl.configure(text=f"Cleaning and formatting Disk {disk_index} to NTFS..."))
        
        new_letter = drive_ops.format_drive(disk_index, label="PCM_MOVE", drive_letter=drive.get('letter'))
        if not new_letter:
            app.after_idle(lambda: show_error_screen(app, "Formatting Failed",
                "We were unable to format the external USB drive.\n"
                "Please ensure it is plugged in, writable, and not locked by another process.\n\n"
                "Note: PCM must be run as Administrator for USB disk formatting."))
            return
        
        # Update the drive letter to the newly assigned one
        drive_letter = new_letter
        drive['letter'] = new_letter
        drive['letters'] = [new_letter]
            
        if engine.cancelled:
            app.after_idle(lambda: show_export_welcome_screen(app))
            return
            
        # Step 2: Copy Files
        app.after_idle(lambda: op_title.configure(text="Exporting Files..."))
        
        # Target PCM folders on USB
        pcm_root = os.path.join(drive_letter + "\\", "_pcm_data")
        os.makedirs(pcm_root, exist_ok=True)
        
        folder_sizes_manifest = {}
        user_manifests = []

        for profile in app.selected_profiles:
            if engine.cancelled:
                break

            user_folders_info = app.all_users_folders_info.get(profile.username, {})
            user_selected_folders = app.selected_folders  # same checklist for all users

            for folder_name in user_selected_folders:
                if engine.cancelled:
                    break
                info = user_folders_info.get(folder_name)
                if info and info.exists:
                    app.after_idle(lambda f=folder_name, u=profile.username:
                                   detail_lbl.configure(text=f"Copying {u}\\{f}..."))
                    # Each user gets their own subdirectory on the drive
                    dest_dir = os.path.join(pcm_root, profile.username, folder_name)
                    engine.copy_folder_recursive(info.path, dest_dir)
                    folder_sizes_manifest[folder_name] = folder_sizes_manifest.get(folder_name, 0) + info.size_bytes

            # Bookmarks for each user
            bookmarks_dest = os.path.join(pcm_root, profile.username, "_pcm_bookmarks")
            exported_browsers = bookmarks.export_browser_bookmarks(profile.path, bookmarks_dest)

            user_manifests.append({
                "username": profile.username,
                "folders": user_selected_folders,
                "folder_sizes": folder_sizes_manifest.copy(),
                "browsers": exported_browsers
            })
                
        if engine.cancelled:
            app.after_idle(lambda: show_export_welcome_screen(app))
            return

        # Copy selected Settings (global to drive/system)
        selected_settings = getattr(app, 'selected_settings', [])
        if selected_settings and not engine.cancelled:
            app.after_idle(lambda: op_title.configure(text="Exporting Settings..."))
            import settings_ops
            
            # Personalization Settings
            if "Windows Personalization Settings" in selected_settings:
                app.after_idle(lambda: detail_lbl.configure(text="Exporting Personalization Settings..."))
                settings_dest = os.path.join(pcm_root, "settings")
                os.makedirs(settings_dest, exist_ok=True)
                settings_ops.export_personalization_settings(settings_dest)
                
            # Wi-Fi Networks
            if "Wi-Fi Network Profiles" in selected_settings:
                app.after_idle(lambda: detail_lbl.configure(text="Exporting Wi-Fi Network Profiles..."))
                settings_dest = os.path.join(pcm_root, "settings")
                os.makedirs(settings_dest, exist_ok=True)
                settings_ops.export_wifi_profiles(settings_dest)

        # Copy selected AppData Preferences (for each selected user profile)
        selected_apps = getattr(app, 'selected_apps', [])
        if selected_apps and not engine.cancelled:
            app.after_idle(lambda: op_title.configure(text="Exporting AppData..."))
            
            for profile in app.selected_profiles:
                if engine.cancelled:
                    break
                    
                user_appdata_info = app.all_users_appdata_info.get(profile.username, {})
                for app_name in selected_apps:
                    if engine.cancelled:
                        break
                        
                    info = user_appdata_info.get(app_name)
                    if info and info.exists:
                        app.after_idle(lambda a=app_name, u=profile.username:
                                       detail_lbl.configure(text=f"Copying {a} for {u}..."))
                        for item in info.items:
                            if engine.cancelled:
                                break
                            original_path = item["path"]
                            rel_path = item["rel_path"]
                            
                            dest_path = os.path.join(pcm_root, profile.username, "appdata", rel_path)
                            
                            if item["type"] == "folder":
                                engine.copy_folder_recursive(original_path, dest_path)
                            else:
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                engine.copy_file_with_conflict_resolution(original_path, dest_path)

        if engine.cancelled:
            app.after_idle(lambda: show_export_welcome_screen(app))
            return

        # Copy selected Steam games (global to system)
        selected_games = getattr(app, 'selected_games', [])
        steam_manifest_data = []
        if selected_games and not engine.cancelled:
            app.after_idle(lambda: op_title.configure(text="Exporting Steam Games..."))
            steam_data_root = os.path.join(pcm_root, "steam_games")
            os.makedirs(steam_data_root, exist_ok=True)
            os.makedirs(os.path.join(steam_data_root, "common"), exist_ok=True)
            
            for appid in selected_games:
                if engine.cancelled:
                    break
                game = app.steam_games.get(appid)
                if game:
                    app.after_idle(lambda g=game['name']: detail_lbl.configure(text=f"Copying game: {g}..."))
                    
                    # Copy manifest .acf file
                    dest_manifest = os.path.join(steam_data_root, os.path.basename(game['manifest_path']))
                    engine.copy_file_with_conflict_resolution(game['manifest_path'], dest_manifest)
                    
                    # Copy game files recursively
                    dest_common = os.path.join(steam_data_root, "common", game['installdir'])
                    engine.copy_folder_recursive(game['common_path'], dest_common)
                    
                    # Track in manifest list
                    steam_manifest_data.append({
                        "appid": appid,
                        "name": game['name'],
                        "installdir": game['installdir'],
                        "size_bytes": game['size_bytes']
                    })

        # Copy custom files and folders
        custom_manifest_data = []
        if getattr(app, 'custom_items', []) and not engine.cancelled:
            app.after_idle(lambda: op_title.configure(text="Exporting Custom Items..."))
            custom_data_root = os.path.join(pcm_root, "custom_items")
            os.makedirs(custom_data_root, exist_ok=True)
            
            for idx, item in enumerate(app.custom_items):
                if engine.cancelled:
                    break
                    
                original_path = item['path']
                item_type = item['type']
                
                # short unique name to prevent MAX_PATH issues
                short_name = f"folder_{idx}" if item_type == 'folder' else f"file_{idx}"
                dest_path = os.path.join(custom_data_root, short_name)
                
                app.after_idle(lambda p=original_path: detail_lbl.configure(text=f"Copying custom item: {p}..."))
                
                if item_type == 'folder':
                    engine.copy_folder_recursive(original_path, dest_path)
                else:
                    engine.copy_file_with_conflict_resolution(original_path, dest_path)
                    
                custom_manifest_data.append({
                    "original_path": original_path,
                    "type": item_type,
                    "short_name": short_name,
                    "size_bytes": item['size_bytes']
                })

        if engine.cancelled:
            app.after_idle(lambda: show_export_welcome_screen(app))
            return

        # Step 3: Write Manifest
        app.after_idle(lambda: op_title.configure(text="Writing Manifest..."))
        app.after_idle(lambda: detail_lbl.configure(text="Generating configuration file..."))
        
        manifest.create_manifest(
            drive_path=drive_letter + "\\",
            source_machine=os.environ.get('COMPUTERNAME', 'SOURCE-PC'),
            source_users=user_manifests,
            total_size_bytes=engine.total_bytes_copied,
            steam_games=steam_manifest_data,
            custom_items=custom_manifest_data,
            settings=selected_settings,
            appdata=selected_apps
        )
        
        # Step 4: Copy self to drive root
        app.after_idle(lambda: op_title.configure(text="Copying Launcher..."))
        app.after_idle(lambda: detail_lbl.configure(text="Copying PCM application to drive root for easy new PC launch..."))
        drive_ops.self_copy_to_drive(drive_letter)
        
        # Step 5: Generate Log
        primary_profile = app.selected_profiles[0] if app.selected_profiles else app.selected_profile
        engine.write_log_files(desktop_user_path=primary_profile.path, drive_root_path=drive_letter + "\\")
        
        # Step 6: Eject Drive
        app.after_idle(lambda: op_title.configure(text="Ejecting Drive..."))
        app.after_idle(lambda: detail_lbl.configure(text="Safely dismounting drive..."))
        ejected = drive_ops.eject_drive(drive_letter)
        
        # End State
        app.after_idle(lambda: show_complete_screen(app, engine.total_files_copied, engine.total_bytes_copied, ejected))
        
    threading.Thread(target=worker, daemon=True).start()

def show_complete_screen(app, total_files, total_bytes, ejected):
    app.set_title_subtitle("Export", "Success")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Export Complete", subtitle="Everything is ready!")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    success_badge = ctk.CTkLabel(card, text="✓", font=("Segoe UI", 60, "bold"), text_color=SUCCESS_GREEN)
    success_badge.pack(pady=(30, 5))
    
    title_lbl = ctk.CTkLabel(card, text="Your PCM Drive is Ready!", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    title_lbl.pack(pady=5)
    
    size_str = format_bytes(total_bytes)
    
    status_str = "USB drive was successfully ejected." if ejected else "Failed to auto-eject. Please click 'Safely Remove Hardware' in Windows taskbar."
    text_color = SUCCESS_GREEN if ejected else WARNING_YELLOW
    
    info_lbl = ctk.CTkLabel(
        card, 
        text=f"Total Files Copied: {total_files}\n"
             f"Total Data Transferred: {size_str}\n\n"
             f"Status: {status_str}\n\n"
             "Next Steps:\n"
             "1. Safely remove this USB drive from your old computer.\n"
             "2. Plug it into your new computer.\n"
             "3. Open the USB drive folder and double click 'PCM.exe' or launcher to start restoration.",
        font=AppFonts.BODY,
        text_color=TEXT_PRIMARY,
        justify="center"
    )
    info_lbl.pack(pady=15, padx=20)
    
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(side="bottom", pady=25)
    
    def open_log():
        # Open desktop log
        desktop = os.path.join(app.selected_profile.path, 'Desktop')
        log_file = os.path.join(desktop, "PCM_Migration_Log.txt")
        if os.path.exists(log_file):
            os.startfile(log_file)
            
    log_btn = ctk.CTkButton(
        btn_frame, 
        text="Open Log Report", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR, 
        hover_color=ACCENT_BLUE,
        command=open_log,
        width=150
    )
    log_btn.pack(side="left", padx=10)
    
    exit_btn = ctk.CTkButton(
        btn_frame, 
        text="Close App", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=app.quit,
        width=120
    )
    exit_btn.pack(side="right", padx=10)

def show_error_screen(app, title, message):
    app.set_title_subtitle("Export", "Error")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Error", subtitle="Something went wrong")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    err_icon = ctk.CTkLabel(card, text="❌", font=("Segoe UI", 48, "normal"), text_color=DANGER_RED)
    err_icon.pack(pady=(45, 10))
    
    title_lbl = ctk.CTkLabel(card, text=title, font=AppFonts.HEADING_MEDIUM, text_color=DANGER_RED)
    title_lbl.pack(pady=5)
    
    msg_lbl = ctk.CTkLabel(card, text=message, font=AppFonts.BODY, text_color=TEXT_PRIMARY, justify="center")
    msg_lbl.pack(pady=20, padx=25)
    
    btn = ctk.CTkButton(
        card, 
        text="Back to Welcome", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=lambda: show_export_welcome_screen(app),
        width=180
    )
    btn.pack(side="bottom", pady=40)
