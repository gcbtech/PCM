import os
import sys
import threading
import time
import customtkinter as ctk
from gui.components import (
    PremiumCard, HeaderPanel, AppFonts,
    ACCENT_BLUE, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS_GREEN, WARNING_YELLOW, DANGER_RED, BORDER_COLOR, CARD_COLOR,
    BG_COLOR
)
import scanner
import drive_ops
import bookmarks
import copy_engine
import manifest

def show_import_welcome_screen(app):
    app.set_title_subtitle("Import", "Welcome")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Import Files", subtitle="Let's restore your files to this PC")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    # 1. Attempt detection (either running dir or scan drives)
    running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    manifest_data = manifest.read_manifest(running_dir)
    
    # Fallback to scanning parent folder if running from _pcm_data subfolder or similar
    if not manifest_data:
        parent_dir = os.path.dirname(running_dir)
        manifest_data = manifest.read_manifest(parent_dir)
        if manifest_data:
            running_dir = parent_dir
            
    detected_drives = []
    selected_drive_var = ctk.StringVar()
    
    status_lbl = ctk.CTkLabel(card, text="Scanning for PCM Transport Drive...", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    status_lbl.pack(pady=20)
    
    info_lbl = ctk.CTkLabel(
        card, 
        text="Please wait while PCM searches for your backup media...", 
        font=AppFonts.BODY,
        text_color=TEXT_SECONDARY
    )
    info_lbl.pack(pady=10)
    
    dropdown_frame = ctk.CTkFrame(card, fg_color="transparent")
    
    def on_drive_selected(choice):
        nonlocal running_dir, manifest_data
        for d in detected_drives:
            desc = f"{d['letter']} ({d['label']}) - PCM Backup"
            if choice == desc:
                manifest_data = manifest.read_manifest(d['letter'] + "\\")
                running_dir = d['letter'] + "\\"
                break
        update_ui_with_manifest()

    def scan_for_pcm_drives():
        nonlocal detected_drives, manifest_data, running_dir
        
        # Check if already found in run path
        if manifest_data:
            update_ui_with_manifest()
            return
            
        # Scan removable drives
        removables = drive_ops.list_removable_drives()
        detected_drives = []
        
        for d in removables:
            m = manifest.read_manifest(d['letter'] + "\\")
            if m:
                detected_drives.append(d)
                
        if detected_drives:
            # Found PCM drive(s)
            dropdown_frame.pack(pady=10)
            values = [f"{d['letter']} ({d['label']}) - PCM Backup" for d in detected_drives]
            selected_drive_var.set(values[0])
            
            # Select first one
            manifest_data = manifest.read_manifest(detected_drives[0]['letter'] + "\\")
            running_dir = detected_drives[0]['letter'] + "\\"
            
            # Show drop down
            for widget in dropdown_frame.winfo_children():
                widget.destroy()
                
            lbl = ctk.CTkLabel(dropdown_frame, text="Select PCM Drive: ", font=AppFonts.BODY_BOLD)
            lbl.pack(side="left", padx=5)
            
            drop = ctk.CTkOptionMenu(
                dropdown_frame, 
                values=values, 
                variable=selected_drive_var, 
                command=on_drive_selected,
                fg_color=ACCENT_BLUE,
                button_color=ACCENT_BLUE
            )
            drop.pack(side="left", padx=5)
            update_ui_with_manifest()
        else:
            # None found
            status_lbl.configure(text="No PCM Transport Drive Detected", text_color=WARNING_YELLOW)
            info_lbl.configure(
                text="We couldn't find a valid PCM backup drive connected to this computer.\n\n"
                     "Please plug in your PCM USB/Flash drive and click Refresh,\n"
                     "or switch to Export Mode if you are trying to prepare a drive instead.",
                text_color=TEXT_PRIMARY
            )
            
            # Show refresh button
            dropdown_frame.pack(pady=10)
            for widget in dropdown_frame.winfo_children():
                widget.destroy()
                
            ref_btn = ctk.CTkButton(
                dropdown_frame, 
                text="Refresh Drives", 
                font=AppFonts.BODY_BOLD, 
                fg_color=ACCENT_BLUE,
                command=scan_for_pcm_drives
            )
            ref_btn.pack()
            next_btn.configure(state="disabled")

    def update_ui_with_manifest():
        if not manifest_data:
            return
            
        app.manifest_data = manifest_data
        app.transport_drive = running_dir
        
        user_info = manifest_data["source_users"][0]
        username = user_info["username"]
        m_date = manifest_data.get("created_at", "Unknown Date").replace("T", " ")
        m_machine = manifest_data.get("source_machine", "Source PC")
        
        folders_list = ", ".join(user_info["folders"])
        
        status_lbl.configure(text="PCM Transport Drive Detected!", text_color=SUCCESS_GREEN)
        info_lbl.configure(
            text=f"Origin System: {m_machine}\n"
                 f"Backup Date: {m_date}\n"
                 f"Owner Account: {username}\n\n"
                 f"Folders Migrated: {folders_list}\n\n"
                 "Please make sure your preferred browser (Chrome, Edge, Firefox) is installed\n"
                 "on this PC so PCM can restore your bookmarks automatically.",
            text_color=TEXT_PRIMARY
        )
        next_btn.configure(state="normal")

    def proceed():
        show_target_user_screen(app)
        
    next_btn = ctk.CTkButton(
        card, 
        text="Next", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        state="disabled",
        command=proceed,
        height=40,
        width=150
    )
    next_btn.pack(side="bottom", pady=(20, 25))
    
    # Manual Switch to Export Mode Link
    switch_btn = ctk.CTkButton(
        app.container,
        text="Need to export files instead? Switch to Export Mode →",
        font=AppFonts.SMALL,
        fg_color="transparent",
        hover=False,
        text_color=ACCENT_BLUE,
        cursor="hand2",
        command=app.switch_to_export_mode
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
    
    # Initial scan trigger
    scan_for_pcm_drives()

def show_target_user_screen(app):
    # Detect local users
    app.user_profiles = scanner.scan_user_profiles()
    
    if len(app.user_profiles) <= 1:
        # If single user, auto-select and skip screen
        if len(app.user_profiles) == 1:
            app.selected_profile = app.user_profiles[0]
        else:
            # Fallback if no profile detected, write to current session username
            curr_user = os.environ.get('USERNAME', 'DefaultUser')
            users_dir = scanner.get_users_root()
            app.selected_profile = scanner.UserProfile(curr_user, os.path.join(users_dir, curr_user))
            
        show_conflict_screen(app)
        return
        
    app.set_title_subtitle("Import", "Target User")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Target User", subtitle="Select destination account")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    lbl = ctk.CTkLabel(
        card, 
        text="Select Destination User Account", 
        font=AppFonts.HEADING_MEDIUM,
        text_color=TEXT_PRIMARY
    )
    lbl.pack(pady=(40, 10))
    
    desc_lbl = ctk.CTkLabel(
        card, 
        text="We detected multiple local user profiles on this computer.\n"
             "Please choose which user account should receive the migrated files.",
        font=AppFonts.BODY,
        text_color=TEXT_SECONDARY,
        justify="center"
    )
    desc_lbl.pack(pady=(0, 30))
    
    dropdown_frame = ctk.CTkFrame(card, fg_color="transparent")
    dropdown_frame.pack(pady=10)
    
    profile_names = [p.username for p in app.user_profiles]
    selected_username_var = ctk.StringVar(value=profile_names[0])
    app.selected_profile = app.user_profiles[0]
    
    def on_user_change(choice):
        for p in app.user_profiles:
            if p.username == choice:
                app.selected_profile = p
                break
                
    lbl_sel = ctk.CTkLabel(dropdown_frame, text="Destination User: ", font=AppFonts.BODY_BOLD)
    lbl_sel.pack(side="left", padx=5)
    
    user_drop = ctk.CTkOptionMenu(
        dropdown_frame, 
        values=profile_names, 
        variable=selected_username_var, 
        command=on_user_change,
        fg_color=ACCENT_BLUE,
        button_color=ACCENT_BLUE
    )
    user_drop.pack(side="left", padx=5)
    
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(side="bottom", pady=25)
    
    back_btn = ctk.CTkButton(
        btn_frame, 
        text="Go Back", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR, 
        command=lambda: show_import_welcome_screen(app),
        width=120
    )
    back_btn.pack(side="left", padx=10)
    
    next_btn = ctk.CTkButton(
        btn_frame, 
        text="Continue", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        command=lambda: show_conflict_screen(app),
        width=120
    )
    next_btn.pack(side="right", padx=10)

def show_conflict_screen(app):
    app.set_title_subtitle("Import", "Preferences")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Preferences", subtitle="Duplicate file resolution")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    title_lbl = ctk.CTkLabel(
        card, 
        text="How should PCM handle duplicate files?", 
        font=AppFonts.HEADING_MEDIUM,
        text_color=TEXT_PRIMARY
    )
    title_lbl.pack(pady=(35, 10))
    
    desc_lbl = ctk.CTkLabel(
        card, 
        text="If a file being migrated already exists at the destination folder,\n"
             "select how you want PCM to handle the conflict:",
        font=AppFonts.BODY,
        text_color=TEXT_SECONDARY,
        justify="center"
    )
    desc_lbl.pack(pady=(0, 30))
    
    radio_var = ctk.StringVar(value="replace")
    
    # Custom styled card buttons for selection
    radio_frame = ctk.CTkFrame(card, fg_color="transparent")
    radio_frame.pack(pady=10)
    
    def set_pref(val):
        radio_var.set(val)
        
    rb_replace = ctk.CTkRadioButton(
        radio_frame, 
        text="Replace existing files (Recommended)\nOverwrites matching files with backup versions",
        variable=radio_var,
        value="replace",
        font=AppFonts.BODY_BOLD,
        text_color=TEXT_PRIMARY,
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE
    )
    rb_replace.pack(anchor="w", pady=12)
    
    rb_skip = ctk.CTkRadioButton(
        radio_frame, 
        text="Skip existing files\nKeeps current files, does not overwrite",
        variable=radio_var,
        value="skip",
        font=AppFonts.BODY_BOLD,
        text_color=TEXT_PRIMARY,
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE
    )
    rb_skip.pack(anchor="w", pady=12)
    
    rb_both = ctk.CTkRadioButton(
        radio_frame, 
        text="Keep both files\nRenames migrated files (e.g. file (1).txt)",
        variable=radio_var,
        value="keep_both",
        font=AppFonts.BODY_BOLD,
        text_color=TEXT_PRIMARY,
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE
    )
    rb_both.pack(anchor="w", pady=12)
    
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(side="bottom", pady=25)
    
    def back_click():
        # Go back either to User Selection or Drive Selection depending on count
        if len(app.user_profiles) > 1:
            show_target_user_screen(app)
        else:
            show_import_welcome_screen(app)
            
    back_btn = ctk.CTkButton(
        btn_frame, 
        text="Go Back", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR, 
        command=back_click,
        width=120
    )
    back_btn.pack(side="left", padx=10)
    
    def proceed_to_progress():
        app.conflict_pref = radio_var.get()
        show_import_progress_screen(app)
        
    next_btn = ctk.CTkButton(
        btn_frame, 
        text="Start Import", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        command=proceed_to_progress,
        width=140
    )
    next_btn.pack(side="right", padx=10)

def show_import_progress_screen(app):
    app.set_title_subtitle("Import", "Progress")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Importing", subtitle="Restoring files to this computer...")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    op_title = ctk.CTkLabel(card, text="Preparing restore...", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    op_title.pack(pady=(45, 10))
    
    progress = ctk.CTkProgressBar(card, width=450, fg_color=BG_COLOR, progress_color=ACCENT_BLUE)
    progress.pack(pady=10)
    progress.set(0.0)
    
    percent_lbl = ctk.CTkLabel(card, text="0% completed (0.00 B / 0.00 B)", font=AppFonts.BODY, text_color=TEXT_SECONDARY)
    percent_lbl.pack(pady=5)
    
    detail_lbl = ctk.CTkLabel(card, text="", font=AppFonts.SMALL, text_color=TEXT_SECONDARY, justify="center")
    detail_lbl.pack(pady=20, padx=20)
    
    cancel_btn = ctk.CTkButton(card, text="Cancel", font=AppFonts.BODY_BOLD, fg_color=BORDER_COLOR, hover_color=DANGER_RED)
    cancel_btn.pack(side="bottom", pady=25)
    
    # State tracker
    engine = copy_engine.CopyEngine(conflict_pref=app.conflict_pref)
    
    def on_cancel():
        engine.cancel()
        cancel_btn.configure(state="disabled", text="Cancelling...")
        
    cancel_btn.configure(command=on_cancel)
    
    # Calculated size
    total_size_bytes = app.manifest_data.get("total_size_bytes", 1)
    
    def progress_callback(file_path, bytes_just_copied, total_bytes_copied, total_files_copied):
        fraction = min(1.0, total_bytes_copied / total_size_bytes)
        
        def get_friendly_bytes(bytes_count):
            size = bytes_count
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
            return f"{size:.2f} GB"
            
        percent = int(fraction * 100)
        curr_str = get_friendly_bytes(total_bytes_copied)
        req_str = get_friendly_bytes(total_size_bytes)
        filename = os.path.basename(file_path)
        
        app.after_idle(lambda: progress.set(fraction))
        app.after_idle(lambda: percent_lbl.configure(text=f"{percent}% completed ({curr_str} / {req_str})"))
        app.after_idle(lambda: detail_lbl.configure(text=f"Restoring file: ...\\{filename}"))

    engine.progress_callback = progress_callback
    
    def worker():
        # Source paths on PCM drive
        pcm_root = os.path.join(app.transport_drive, "_pcm_data")
        user_info = app.manifest_data["source_users"][0]
        migrated_folders = user_info["folders"]
        
        dest_user_path = app.selected_profile.path
        
        # Step 1: Copy Profile Folders
        app.after_idle(lambda: op_title.configure(text="Restoring Personal Files..."))
        
        for folder_name in migrated_folders:
            if engine.cancelled:
                break
                
            src_dir = os.path.join(pcm_root, folder_name)
            if os.path.exists(src_dir):
                app.after_idle(lambda f=folder_name: detail_lbl.configure(text=f"Restoring folder: {f}..."))
                
                # Construct exact local target folder
                # Handle OneDrive mapping. If OneDrive is set on local target, place it in local OneDrive,
                # otherwise standard folder.
                od_path = os.path.join(dest_user_path, 'OneDrive', folder_name)
                std_path = os.path.join(dest_user_path, folder_name)
                
                dest_dir = std_path
                if os.path.exists(od_path):
                    dest_dir = od_path
                    
                engine.copy_folder_recursive(src_dir, dest_dir)
                
        if engine.cancelled:
            app.after_idle(lambda: show_import_welcome_screen(app))
            return
            
        # Step 2: Import Bookmarks
        app.after_idle(lambda: op_title.configure(text="Restoring Browser Bookmarks..."))
        app.after_idle(lambda: detail_lbl.configure(text="Injecting bookmarks and exporting HTML backups..."))
        
        src_bookmarks = os.path.join(pcm_root, "_pcm_bookmarks")
        restored_browsers, desktop_fallback = bookmarks.import_browser_bookmarks(src_bookmarks, dest_user_path)
        
        # Step 3: Write logs
        # Generate and save log copies on desktop + transport drive
        engine.write_log_files(desktop_user_path=dest_user_path, drive_root_path=app.transport_drive)
        
        # End State
        app.after_idle(lambda: show_complete_screen(app, engine.total_files_copied, engine.total_bytes_copied, restored_browsers, desktop_fallback))
        
    threading.Thread(target=worker, daemon=True).start()

def show_complete_screen(app, total_files, total_bytes, restored_browsers, desktop_fallback):
    app.set_title_subtitle("Import", "Success")
    app.clear_container()
    
    header = HeaderPanel(app.container, title="PCM (PC Mover) — Restoration Complete", subtitle="Welcome to your new PC!")
    header.pack(fill="x")
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, pady=(0, 15))
    
    success_badge = ctk.CTkLabel(card, text="✓", font=("Segoe UI", 60, "bold"), text_color=SUCCESS_GREEN)
    success_badge.pack(pady=(20, 5))
    
    title_lbl = ctk.CTkLabel(card, text="Files Restored Successfully!", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    title_lbl.pack(pady=5)
    
    def get_friendly_bytes(bytes_count):
        size = bytes_count
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} GB"
        
    size_str = get_friendly_bytes(total_bytes)
    
    # Bookmarks summary
    b_desc = ""
    if restored_browsers:
        b_desc = f"Browser Bookmarks Imported: {', '.join(restored_browsers)}\n"
        
    if desktop_fallback:
        b_desc += f"A folder 'PCM Migrated Bookmarks' has been added to your Desktop."
    else:
        b_desc += "No browser bookmarks were found/migrated."
        
    info_lbl = ctk.CTkLabel(
        card, 
        text=f"Total Files Restored: {total_files}\n"
             f"Total Data Restored: {size_str}\n\n"
             f"{b_desc}\n\n"
             "A detailed migration log file has been saved to your Desktop.\n"
             "You can now safely disconnect your PCM external drive.",
        font=AppFonts.BODY,
        text_color=TEXT_PRIMARY,
        justify="center"
    )
    info_lbl.pack(pady=15, padx=20)
    
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(side="bottom", pady=25)
    
    def open_log():
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
        text="Finish", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color=ACCENT_BLUE,
        command=app.quit,
        width=120
    )
    exit_btn.pack(side="right", padx=10)
