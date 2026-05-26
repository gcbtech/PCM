import os
import sys
import random
import threading
import time
import tempfile
import customtkinter as ctk
from gui.components import (
    PremiumCard, HeaderPanel, AppFonts, ScrollableFolderList, ScrollableSteamGamesList, ScrollableCustomItemList,
    ACCENT_BLUE, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS_GREEN, WARNING_YELLOW, DANGER_RED, BORDER_COLOR, CARD_COLOR,
    BG_COLOR, ScrollableSettingsList, ScrollableAppDataList
)
import scanner
import bookmarks
import network_engine
from utils import format_bytes

# Active references to running network threads
current_receiver = None
current_sender = None

def show_method_selection(app):
    """
    Initial launch screen allowing the user to select 
    either traditional USB Drive migration or Network Transfer.
    """
    app.set_title_subtitle("Select Transfer Method", "Choose how you want to migrate your files")
    app.clear_container()

    # Title header
    header = HeaderPanel(app.container, subtitle="Choose a file migration method to begin.")
    header.pack(fill="x", pady=(0, 20))

    # Create a grid container frame that is packed inside app.container
    grid_container = ctk.CTkFrame(app.container, fg_color="transparent")
    grid_container.pack(fill="both", expand=True)

    # Grid columns for the two options
    grid_container.columnconfigure(0, weight=1, uniform="group")
    grid_container.columnconfigure(1, weight=1, uniform="group")
    grid_container.rowconfigure(0, weight=1)

    # Column 1: USB Transfer
    usb_card = PremiumCard(grid_container)
    usb_card.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")

    usb_lbl = ctk.CTkLabel(usb_card, text="💾 USB / External Drive", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    usb_lbl.pack(pady=(20, 10))

    usb_desc = ctk.CTkLabel(
        usb_card, 
        text="Copy your files to a USB drive or external hard disk.\n\n"
             "PCM will format the drive (NTFS), save a manifest, and copy its execution file. "
             "Then plug the drive into the new computer and launch PCM directly from it.\n\n"
             "Best for: simplicity, no network setups, offline migrations.",
        font=AppFonts.SMALL, 
        text_color=TEXT_SECONDARY,
        wraplength=280,
        justify="left"
    )
    usb_desc.pack(padx=15, pady=10, fill="both", expand=True)

    usb_btn = ctk.CTkButton(
        usb_card, 
        text="Select USB Drive Flow", 
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=lambda: start_usb_flow(app)
    )
    usb_btn.pack(pady=20)

    # Column 2: Network Transfer
    net_card = PremiumCard(grid_container)
    net_card.grid(row=0, column=1, padx=15, pady=10, sticky="nsew")

    net_lbl = ctk.CTkLabel(net_card, text="🌐 Network Transfer (LAN/Link)", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    net_lbl.pack(pady=(20, 10))

    net_desc = ctk.CTkLabel(
        net_card, 
        text="Securely stream files from one computer directly to another.\n\n"
             "Both computers run PCM on the same local network or connected directly by a cable.\n\n"
             "Uses ephemeral self-signed AES-256 TLS encryption and secure pairing codes.\n\n"
             "Best for: speed, no spare external hard drive, desktop machines.",
        font=AppFonts.SMALL, 
        text_color=TEXT_SECONDARY,
        wraplength=280,
        justify="left"
    )
    net_desc.pack(padx=15, pady=10, fill="both", expand=True)

    net_btn = ctk.CTkButton(
        net_card, 
        text="Select Network Flow", 
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=lambda: show_network_role_selection(app)
    )
    net_btn.pack(pady=20)

def start_usb_flow(app):
    """Bypasses method selection and routes to traditional drive modes."""
    # Check if a manifest file is in running directory
    if app.mode == "import" and app.manifest_data:
        from gui.import_view import show_import_welcome_screen
        show_import_welcome_screen(app)
    else:
        from gui.export_view import show_export_welcome_screen
        show_export_welcome_screen(app)

def show_network_role_selection(app):
    """Prompts the user to define their role (Sender vs. Receiver)."""
    app.set_title_subtitle("Network Role Selection", "Select your computer role")
    app.clear_container()

    header = HeaderPanel(app.container, title="PCM Network Transfer", subtitle="Choose whether this computer sends or receives the files.")
    header.pack(fill="x", pady=(0, 20))

    # Create a grid container frame that is packed inside app.container
    grid_container = ctk.CTkFrame(app.container, fg_color="transparent")
    grid_container.pack(fill="both", expand=True)

    grid_container.columnconfigure(0, weight=1, uniform="group")
    grid_container.columnconfigure(1, weight=1, uniform="group")
    grid_container.rowconfigure(0, weight=1)

    # Send (Source) Card
    send_card = PremiumCard(grid_container)
    send_card.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")

    send_lbl = ctk.CTkLabel(send_card, text="📤 Send Files", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    send_lbl.pack(pady=(20, 10))

    send_desc = ctk.CTkLabel(
        send_card, 
        text="Select this option if this is the OLD computer containing the files you want to migrate.\n\n"
             "This machine will scan your files and stream them safely across the network to your new computer.\n\n"
             "You will enter the 6-digit pairing code shown on your new computer.",
        font=AppFonts.SMALL, 
        text_color=TEXT_SECONDARY,
        wraplength=280,
        justify="left"
    )
    send_desc.pack(padx=15, pady=10, fill="both", expand=True)

    send_btn = ctk.CTkButton(
        send_card, 
        text="Send Files (Old PC)", 
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=lambda: show_network_sender_user_select(app)
    )
    send_btn.pack(pady=20)

    # Receive (Destination) Card
    recv_card = PremiumCard(grid_container)
    recv_card.grid(row=0, column=1, padx=15, pady=10, sticky="nsew")

    recv_lbl = ctk.CTkLabel(recv_card, text="📥 Receive Files", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    recv_lbl.pack(pady=(20, 10))

    recv_desc = ctk.CTkLabel(
        recv_card, 
        text="Select this option if this is the NEW computer that should receive the migrated files.\n\n"
             "This machine will wait for a connection and save files directly into your new user folders.\n\n"
             "This computer will display a unique 6-digit pairing code to verify connection.",
        font=AppFonts.SMALL, 
        text_color=TEXT_SECONDARY,
        wraplength=280,
        justify="left"
    )
    recv_desc.pack(padx=15, pady=10, fill="both", expand=True)

    recv_btn = ctk.CTkButton(
        recv_card, 
        text="Receive Files (New PC)", 
        font=AppFonts.BODY_BOLD,
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=lambda: show_network_receiver_setup(app)
    )
    recv_btn.pack(pady=20)

    # Footer navigation (packed directly in app.container below the grid_container)
    footer_frame = ctk.CTkFrame(app.container, fg_color="transparent")
    footer_frame.pack(fill="x", pady=(15, 0))
    
    back_btn = ctk.CTkButton(
        footer_frame, 
        text="← Back to Method Selection", 
        font=AppFonts.BODY, 
        fg_color="transparent", 
        text_color=TEXT_SECONDARY,
        hover_color=CARD_COLOR,
        command=lambda: show_method_selection(app)
    )
    back_btn.pack(side="left")

def show_network_receiver_setup(app):
    """
    Sets up the Receiver (Destination PC). 
    Generates pairing code, starts TLS socket thread, and displays status.
    """
    global current_receiver
    app.set_title_subtitle("Receiver Setup", "Waiting for secure connection")
    app.clear_container()

    header = HeaderPanel(app.container, title="Receive Files", subtitle="Keep this screen open on your new computer.")
    header.pack(fill="x", pady=(0, 10))

    # Generate 6-digit code
    code = f"{random.randint(100, 999)} - {random.randint(100, 999)}"
    clean_code = code.replace(" - ", "")

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    pairing_lbl = ctk.CTkLabel(card, text="ENTER THIS PAIRING CODE ON YOUR OLD COMPUTER", font=AppFonts.BODY_BOLD, text_color=ACCENT_BLUE)
    pairing_lbl.pack(pady=(20, 10))

    code_lbl = ctk.CTkLabel(card, text=code, font=("Courier New", 42, "bold"), text_color=SUCCESS_GREEN)
    code_lbl.pack(pady=10)

    status_lbl = ctk.CTkLabel(card, text="⌛ Waiting for old computer to discover and connect...", font=AppFonts.SUBTITLE, text_color=TEXT_PRIMARY)
    status_lbl.pack(pady=20)

    # List local network details to help user if needed
    ips = network_engine.get_local_ips()
    ip_text = f"Local IP Address: {', '.join(ips) if ips else 'Not connected to a network'}"
    ip_lbl = ctk.CTkLabel(card, text=ip_text, font=AppFonts.SMALL, text_color=TEXT_SECONDARY)
    ip_lbl.pack(pady=5)

    back_btn = ctk.CTkButton(
        card, 
        text="Cancel Setup", 
        font=AppFonts.BODY_BOLD, 
        fg_color=DANGER_RED,
        hover_color="#CC005F",
        command=lambda: cancel_receiver(app)
    )
    back_btn.pack(pady=(20, 10))

    # Threading events for control synchronization
    manifest_event = threading.Event()
    target_selected_event = threading.Event()
    received_manifest = {}

    def manifest_callback(manifest_data):
        nonlocal received_manifest
        received_manifest.update(manifest_data)
        manifest_event.set()
        
    def progress_callback(current_file, bytes_read, files_processed, total_files):
        # Dispatches UI safe progress updates
        app.after(0, lambda: update_receiver_progress(app, current_file, bytes_read, files_processed, total_files))

    def completion_callback(summary_text):
        app.after(0, lambda: show_network_completion(app, summary_text))

    def error_callback(err_msg):
        app.after(0, lambda: show_network_error(app, err_msg))

    # Spawn receiver server
    current_receiver = network_engine.PCMNetworkReceiver(
        clean_code, 
        manifest_callback, 
        target_selected_event, 
        progress_callback, 
        completion_callback, 
        error_callback
    )

    t = threading.Thread(target=current_receiver.run, daemon=True)
    t.start()

    # Polling listener to transition screens when manifest is received
    def check_manifest():
        if manifest_event.is_set():
            show_network_receiver_target_selection(app, received_manifest, target_selected_event)
        elif not current_receiver.cancelled:
            app.after(200, check_manifest)

    app.after(200, check_manifest)

def cancel_receiver(app):
    global current_receiver
    if current_receiver:
        current_receiver.stop()
        current_receiver = None
    show_network_role_selection(app)

def show_network_receiver_target_selection(app, manifest_data, target_selected_event):
    """
    Displays metadata received from the Sender and prompts 
    the Receiver user to map destination accounts and set conflict resolution policies.
    """
    app.set_title_subtitle("Target Selection", "Select destination profile")
    app.clear_container()

    header = HeaderPanel(app.container, title="Connect Established", subtitle="Set up how you want to import these files.")
    header.pack(fill="x", pady=(0, 10))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    # Enumerate profiles
    profiles = scanner.scan_user_profiles()
    profile_names = [p.username for p in profiles]
    profile_map = {p.username: p.path for p in profiles}

    meta_lbl = ctk.CTkLabel(
        card, 
        text=f"📂 Incoming Data from: {manifest_data.get('source_machine', 'Old PC')}\n"
             f"Total Files: {manifest_data.get('total_files', 0)}  |  Total Size: {manifest_data.get('total_size', 0) / (1024*1024*1024):.2f} GB",
        font=AppFonts.BODY_BOLD,
        text_color=TEXT_PRIMARY,
        justify="left"
    )
    meta_lbl.pack(pady=15, padx=15)

    # 1. User profile selection
    dropdown_frame = ctk.CTkFrame(card, fg_color="transparent")
    dropdown_frame.pack(fill="x", padx=30, pady=10)

    user_lbl = ctk.CTkLabel(dropdown_frame, text="Select destination account:", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    user_lbl.pack(side="left", padx=10)

    selected_username_var = ctk.StringVar(value=profile_names[0] if profile_names else "")
    user_dropdown = ctk.CTkOptionMenu(
        dropdown_frame, 
        values=profile_names, 
        variable=selected_username_var, 
        font=AppFonts.BODY,
        fg_color=BORDER_COLOR,
        button_color=ACCENT_BLUE,
        button_hover_color="#2563EB"
    )
    user_dropdown.pack(side="left", padx=10)

    # 2. Conflict preference selection
    conflict_frame = ctk.CTkFrame(card, fg_color="transparent")
    conflict_frame.pack(fill="x", padx=30, pady=10)

    conflict_lbl = ctk.CTkLabel(conflict_frame, text="If a duplicate file exists:", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    conflict_lbl.pack(anchor="w", padx=10, pady=5)

    conflict_var = ctk.StringVar(value="replace")
    
    replace_radio = ctk.CTkRadioButton(conflict_frame, text="Replace existing files", variable=conflict_var, value="replace", font=AppFonts.SMALL)
    replace_radio.pack(anchor="w", padx=25, pady=2)
    
    skip_radio = ctk.CTkRadioButton(conflict_frame, text="Skip duplicate files", variable=conflict_var, value="skip", font=AppFonts.SMALL)
    skip_radio.pack(anchor="w", padx=25, pady=2)
    
    keep_radio = ctk.CTkRadioButton(conflict_frame, text="Keep both (rename incoming files)", variable=conflict_var, value="keep_both", font=AppFonts.SMALL)
    keep_radio.pack(anchor="w", padx=25, pady=2)

    # Action buttons frame
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(pady=20)
    
    def cancel_click():
        global current_receiver
        if current_receiver:
            current_receiver.stop()
            current_receiver = None
        show_network_role_selection(app)

    cancel_btn = ctk.CTkButton(
        btn_frame, 
        text="Cancel & Disconnect", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR,
        hover_color=DANGER_RED,
        command=cancel_click,
        width=160
    )
    cancel_btn.pack(side="left", padx=10)

    action_btn = ctk.CTkButton(
        btn_frame, 
        text="Start Importing Network Data", 
        font=AppFonts.BODY_BOLD, 
        fg_color=SUCCESS_GREEN,
        hover_color="#2E8E00",
        command=lambda: submit_receiver_selections(app, target_selected_event, profile_map, selected_username_var.get(), conflict_var.get(), manifest_data),
        width=220
    )
    action_btn.pack(side="right", padx=10)

def submit_receiver_selections(app, target_selected_event, profile_map, selected_username, conflict_pref, manifest_data):
    """Submits selections back to the engine thread to begin transfers."""
    global current_receiver
    if current_receiver:
        current_receiver.target_prefs = {
            'user_path': profile_map[selected_username],
            'conflict_pref': conflict_pref
        }
        # Release receiver thread blocks
        target_selected_event.set()
        
        # Redirection to network progress page
        show_network_progress(app, manifest_data['total_files'], manifest_data['total_size'], "receiver")

def show_network_sender_user_select(app):
    """
    Step 1: Choose which user account profile to migrate 
    on the Sender (Source) computer.
    """
    app.set_title_subtitle("Sender Profile", "Choose account to send")
    app.clear_container()

    header = HeaderPanel(app.container, title="Send Files", subtitle="Choose a user profile to scan.")
    header.pack(fill="x", pady=(0, 10))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    welcome_lbl = ctk.CTkLabel(card, text="Select Profile to Send", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    welcome_lbl.pack(pady=(25, 10))

    desc_lbl = ctk.CTkLabel(
        card, 
        text="PCM will scan this user profile and let you choose which folders to send.",
        font=AppFonts.BODY,
        text_color=TEXT_SECONDARY,
        justify="center"
    )
    desc_lbl.pack(pady=(0, 20))

    app.user_profiles = scanner.scan_user_profiles()
    dropdown_frame = ctk.CTkFrame(card, fg_color="transparent")
    dropdown_frame.pack(pady=10)

    selected_username_var = ctk.StringVar()

    if len(app.user_profiles) == 0:
        error_lbl = ctk.CTkLabel(card, text="No active user profiles detected on this machine.", text_color=DANGER_RED, font=AppFonts.BODY_BOLD)
        error_lbl.pack(pady=10)
        btn_state = "disabled"
    elif len(app.user_profiles) == 1:
        app.selected_profile = app.user_profiles[0]
        user_lbl = ctk.CTkLabel(dropdown_frame, text=f"Data Source: {app.selected_profile.username}", font=AppFonts.BODY_BOLD, text_color=SUCCESS_GREEN)
        user_lbl.pack()
        btn_state = "normal"
    else:
        profile_names = [p.username for p in app.user_profiles]
        selected_username_var.set(profile_names[0])
        app.selected_profile = app.user_profiles[0]

        lbl = ctk.CTkLabel(dropdown_frame, text="Select Account: ", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
        lbl.pack(side="left", padx=5)

        def on_user_change(choice):
            for p in app.user_profiles:
                if p.username == choice:
                    app.selected_profile = p
                    break

        user_drop = ctk.CTkOptionMenu(
            dropdown_frame, 
            values=profile_names, 
            variable=selected_username_var, 
            command=on_user_change,
            fg_color=ACCENT_BLUE,
            button_color=ACCENT_BLUE
        )
        user_drop.pack(side="left", padx=5)
        btn_state = "normal"

    scan_btn = ctk.CTkButton(
        card, 
        text="Scan My Files", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        state=btn_state,
        command=lambda: show_network_sender_scanning(app)
    )
    scan_btn.pack(pady=30)

    back_btn = ctk.CTkButton(
        card, 
        text="← Back to Role Selection", 
        font=AppFonts.BODY, 
        fg_color="transparent", 
        text_color=TEXT_SECONDARY,
        hover_color=CARD_COLOR,
        command=lambda: show_network_role_selection(app)
    )
    back_btn.pack(pady=5)

def show_network_sender_scanning(app):
    """
    Step 2: Scans the user folders in a background thread 
    and transitions to the folder checklist.
    """
    app.set_title_subtitle("Sender Scanning", "Scanning folder sizes...")
    app.clear_container()

    header = HeaderPanel(app.container, title="Send Files", subtitle="Analyzing folder sizes and counts.")
    header.pack(fill="x", pady=(0, 10))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=20)

    status_lbl = ctk.CTkLabel(card, text="🔍 Scanning user folders...", font=AppFonts.SUBTITLE, text_color=TEXT_PRIMARY)
    status_lbl.pack(pady=40)

    progress_bar = ctk.CTkProgressBar(card, orientation="horizontal", width=400, mode="indeterminate", progress_color=ACCENT_BLUE)
    progress_bar.pack(pady=10)
    progress_bar.start()

    def run_scan():
        try:
            # Scan profile folders
            app.folders_info = scanner.scan_profile_folders(app.selected_profile.path)

            # Scan AppData folders
            from appdata_scanner import scan_profile_appdata
            app.appdata_info = scan_profile_appdata(app.selected_profile.path)
            
            # Detect Steam games
            import steam_ops
            app.steam_games = steam_ops.detect_steam_games()
            
            app.after(500, lambda: show_network_sender_checklist(app))
        except Exception as e:
            app.after(0, lambda: show_network_error(app, f"Error scanning user folders: {e}"))

    t = threading.Thread(target=run_scan, daemon=True)
    t.start()

def show_network_sender_checklist(app):
    """
    Step 3: Display checklist of folders to send, 
    matching the premium look of show_scan_results_screen.
    """
    app.set_title_subtitle("Sender Configure", "Select folders to stream")
    app.clear_container()

    header = HeaderPanel(app.container, title="Send Files", subtitle="Configure folders and view estimate sizing.")
    header.pack(fill="x", pady=(0, 10))

    # Outer frame to arrange folder list and checklist side-by-side
    body = ctk.CTkFrame(app.container, fg_color="transparent")
    body.pack(fill="both", expand=True, pady=(0, 10))

    body.columnconfigure(0, weight=3) # Tabbed Checklist
    body.columnconfigure(1, weight=2) # Details Panel
    body.rowconfigure(0, weight=1)

    # Left side: CTkTabview for Folder, Steam, and Custom checklists
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

    # Personal folders checklist
    folder_checklist = ScrollableFolderList(tabview.tab("Personal Folders"), app.folders_info, border_width=0, corner_radius=0)
    folder_checklist.grid(row=0, column=0, sticky="nsew")
    tabview.tab("Personal Folders").grid_rowconfigure(0, weight=1)
    tabview.tab("Personal Folders").grid_columnconfigure(0, weight=1)

    # Steam games checklist
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

    # Custom items checklist
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

    # Right side: Details Panel Summary Card
    summary_card = PremiumCard(body)
    summary_card.grid(row=0, column=1, sticky="nsew")
    
    title_lbl = ctk.CTkLabel(summary_card, text="Stream Sizing", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
    title_lbl.pack(pady=(20, 15), padx=10)

    size_summary_lbl = ctk.CTkLabel(summary_card, text="Selected: 0.00 B", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    size_summary_lbl.pack(pady=5)

    def update_size_estimate():
        checked = folder_checklist.get_selected_folders()
        total_bytes = 0
        for name in checked:
            info = app.folders_info.get(name)
            if info:
                total_bytes += info.size_bytes
                
        # Steam games
        selected_games = steam_checklist.get_selected_games()
        for appid in selected_games:
            game = app.steam_games.get(appid)
            if game:
                total_bytes += game['size_bytes']
                
        # Custom items
        for item in app.custom_items:
            total_bytes += item['size_bytes']

        # Settings
        selected_settings = settings_checklist.get_selected_settings()
        for name in selected_settings:
            data = settings_checklist.checkboxes.get(name)
            if data:
                total_bytes += data['size_bytes']

        # AppData
        selected_apps = appdata_checklist.get_selected_apps()
        for name in selected_apps:
            info = app.appdata_info.get(name)
            if info:
                total_bytes += info.size_bytes
            
        total_bytes += int(total_bytes * 0.05) + (50 * 1024 * 1024)
        size_str = format_bytes(total_bytes)
        size_summary_lbl.configure(text=f"Estimate Required:\n{size_str}")

    # Hook checkbox toggles
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

    # Call initial list refresh AFTER size_summary_lbl is constructed!
    refresh_custom_items_list()

    def proceed():
        app.selected_folders = folder_checklist.get_selected_folders()
        app.selected_games = steam_checklist.get_selected_games()
        app.selected_settings = settings_checklist.get_selected_settings()
        app.selected_apps = appdata_checklist.get_selected_apps()
        show_network_sender_connection(app)

    back_btn = ctk.CTkButton(
        summary_card,
        text="← Back to Profile Select",
        font=AppFonts.BODY_BOLD,
        fg_color=BORDER_COLOR,
        hover_color=ACCENT_BLUE,
        command=lambda: show_network_sender_user_select(app),
        height=35
    )
    back_btn.pack(side="bottom", fill="x", pady=(0, 20), padx=20)

    next_btn = ctk.CTkButton(
        summary_card, 
        text="Proceed to Connection", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=proceed,
        height=40
    )
    next_btn.pack(side="bottom", fill="x", pady=(20, 10), padx=20)


def show_network_sender_connection(app):
    """
    Step 4: Prompt for pairing code entry to establish network tunnel.
    """
    app.set_title_subtitle("Sender Connection", "Secure link configuration")
    app.clear_container()

    header = HeaderPanel(app.container, title="Secure Connection", subtitle="Link up securely with your new PC.")
    header.pack(fill="x", pady=(0, 10))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    instruction_lbl = ctk.CTkLabel(
        card, 
        text="1. Make sure PCM is open on your new computer and set to 'Receive Files'.\n"
             "2. Enter the 6-digit code shown on the new computer screen below.",
        font=AppFonts.BODY, 
        text_color=TEXT_PRIMARY,
        justify="left"
    )
    instruction_lbl.pack(pady=(20, 10))

    entry_frame = ctk.CTkFrame(card, fg_color="transparent")
    entry_frame.pack(pady=10)

    code_lbl = ctk.CTkLabel(entry_frame, text="Pairing Code:", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    code_lbl.pack(side="left", padx=10)

    code_entry = ctk.CTkEntry(
        entry_frame, 
        placeholder_text="e.g. 582917", 
        width=180, 
        font=("Courier New", 20, "bold"),
        justify="center",
        border_color=BORDER_COLOR
    )
    code_entry.pack(side="left", padx=10)

    # Optional IP Entry Box for virtualization / blocked UDP networks
    ip_frame = ctk.CTkFrame(card, fg_color="transparent")
    ip_frame.pack(pady=10)

    ip_lbl = ctk.CTkLabel(ip_frame, text="Receiver IP (Optional):", font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    ip_lbl.pack(side="left", padx=10)

    ip_entry = ctk.CTkEntry(
        ip_frame, 
        placeholder_text="e.g. 172.20.15.42 (Auto-detects)", 
        width=250, 
        font=AppFonts.BODY,
        border_color=BORDER_COLOR
    )
    ip_entry.pack(side="left", padx=10)

    action_btn = ctk.CTkButton(
        card, 
        text="Connect & Stream Files", 
        font=AppFonts.BODY_BOLD, 
        fg_color=SUCCESS_GREEN,
        hover_color="#2E8E00",
        command=lambda: initiate_network_sender(app, code_entry.get(), ip_entry.get())
    )
    action_btn.pack(pady=15)

    back_btn = ctk.CTkButton(
        card, 
        text="← Back to Checklist", 
        font=AppFonts.BODY, 
        fg_color="transparent", 
        text_color=TEXT_SECONDARY,
        hover_color=CARD_COLOR,
        command=lambda: show_network_sender_checklist(app)
    )
    back_btn.pack(pady=5)

def initiate_network_sender(app, code, receiver_ip=None):
    """Validates parameters, scans local files, and launches the sender thread."""
    clean_code = code.strip().replace(" ", "").replace("-", "")
    if len(clean_code) != 6 or not clean_code.isdigit():
        show_network_error(app, "Invalid Pairing Code format. Please enter a 6-digit numeric code.")
        return

    # Prompt user that scanning is commencing
    app.set_title_subtitle("Scanning User Folders", "Preparing file scan...")
    app.clear_container()
    
    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=20)

    status_lbl = ctk.CTkLabel(card, text="⌛ Connecting to receiver and preparing data transmission...", font=AppFonts.SUBTITLE, text_color=TEXT_PRIMARY)
    status_lbl.pack(pady=40)

    progress_bar = ctk.CTkProgressBar(card, orientation="horizontal", width=400, mode="indeterminate", progress_color=ACCENT_BLUE)
    progress_bar.pack(pady=10)
    progress_bar.start()

    def do_scan_and_send():
        current_profile = app.selected_profile
        folders_dict = app.folders_info
        
        # Enumerate files recursively ONLY for selected categories
        files_to_send = []
        for name, folder_info in folders_dict.items():
            if name not in app.selected_folders:
                continue
            if folder_info.exists:
                for root, dirs, files in os.walk(folder_info.path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            # Skip symlinks/reparse points to avoid loop hangs
                            from copy_engine import is_reparse_point
                            if is_reparse_point(file_path):
                                continue
                            file_size = os.path.getsize(file_path)
                            rel_path = os.path.relpath(file_path, folder_info.path)
                            files_to_send.append({
                                'src_path': file_path,
                                'rel_path': rel_path,
                                'size': file_size,
                                'category': name
                            })
                        except Exception:
                            pass

        # Enumerate Steam Games
        selected_games = getattr(app, 'selected_games', [])
        for appid in selected_games:
            game = getattr(app, 'steam_games', {}).get(appid)
            if game:
                # 1. ACF manifest file
                acf_path = game['manifest_path']
                if os.path.exists(acf_path):
                    files_to_send.append({
                        'src_path': acf_path,
                        'rel_path': os.path.basename(acf_path),
                        'size': os.path.getsize(acf_path),
                        'category': 'SteamGames'
                    })
                # 2. Game files in common
                common_dir = game['common_path']
                if os.path.exists(common_dir):
                    for root, dirs, files in os.walk(common_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                from copy_engine import is_reparse_point
                                if is_reparse_point(file_path):
                                    continue
                                file_size = os.path.getsize(file_path)
                                rel_path = os.path.join("common", game['installdir'], os.path.relpath(file_path, common_dir))
                                files_to_send.append({
                                    'src_path': file_path,
                                    'rel_path': rel_path,
                                    'size': file_size,
                                    'category': 'SteamGames'
                                })
                            except Exception:
                                pass

        # Enumerate Custom Items
        for item in getattr(app, 'custom_items', []):
            item_path = item['path']
            item_type = item['type']
            if os.path.exists(item_path):
                if item_type == 'file':
                    files_to_send.append({
                        'src_path': item_path,
                        'rel_path': item_path,
                        'size': os.path.getsize(item_path),
                        'category': 'CustomItems'
                    })
                else: # folder
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                from copy_engine import is_reparse_point
                                if is_reparse_point(file_path):
                                    continue
                                file_size = os.path.getsize(file_path)
                                files_to_send.append({
                                    'src_path': file_path,
                                    'rel_path': file_path,
                                    'size': file_size,
                                    'category': 'CustomItems'
                                })
                            except Exception:
                                pass

        # Always export browser bookmarks alongside file folders
        try:
            import shutil
            temp_bookmarks_path = os.path.join(tempfile.gettempdir(), "_pcm_bookmarks_net")
            if os.path.exists(temp_bookmarks_path):
                shutil.rmtree(temp_bookmarks_path)
            os.makedirs(temp_bookmarks_path, exist_ok=True)

            bookmarks.export_browser_bookmarks(current_profile.path, temp_bookmarks_path)

            # Walk bookmarks export and add to send queue
            for root, dirs, files in os.walk(temp_bookmarks_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)
                    rel_path = os.path.relpath(file_path, temp_bookmarks_path)
                    files_to_send.append({
                        'src_path': file_path,
                        'rel_path': rel_path,
                        'size': file_size,
                        'category': 'Bookmarks'
                    })
        except Exception as e:
            print(f"[Network] Bookmark export exception: {e}")

        # Export and queue Windows Settings
        selected_settings = getattr(app, 'selected_settings', [])
        if selected_settings:
            try:
                import shutil
                temp_settings_path = os.path.join(tempfile.gettempdir(), "_pcm_settings_net")
                if os.path.exists(temp_settings_path):
                    shutil.rmtree(temp_settings_path)
                os.makedirs(temp_settings_path, exist_ok=True)
                
                import settings_ops
                if "Windows Personalization Settings" in selected_settings:
                    settings_ops.export_personalization_settings(temp_settings_path)
                if "Wi-Fi Network Profiles" in selected_settings:
                    settings_ops.export_wifi_profiles(temp_settings_path)
                    
                for root, dirs, files in os.walk(temp_settings_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        rel_path = os.path.relpath(file_path, temp_settings_path)
                        files_to_send.append({
                            'src_path': file_path,
                            'rel_path': rel_path.replace("\\", "/"),
                            'size': file_size,
                            'category': 'Settings'
                        })
            except Exception as e:
                print(f"[Network] Settings export exception: {e}")

        # Export and queue AppData Preferences
        selected_apps = getattr(app, 'selected_apps', [])
        if selected_apps:
            try:
                from appdata_scanner import get_appdata_definitions
                definitions = get_appdata_definitions(current_profile.path)
                for app_name in selected_apps:
                    items = definitions.get(app_name, [])
                    for item in items:
                        item_path = item["path"]
                        rel_path = item["rel_path"]
                        if os.path.exists(item_path):
                            if item["type"] == "folder":
                                for root, dirs, files in os.walk(item_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        try:
                                            from copy_engine import is_reparse_point
                                            if is_reparse_point(file_path):
                                                continue
                                            file_size = os.path.getsize(file_path)
                                            sub_rel = os.path.relpath(file_path, item_path)
                                            send_rel_path = os.path.normpath(os.path.join(rel_path, sub_rel))
                                            files_to_send.append({
                                                'src_path': file_path,
                                                'rel_path': send_rel_path.replace("\\", "/"),
                                                'size': file_size,
                                                'category': 'AppData'
                                            })
                                        except Exception:
                                            pass
                            else:
                                try:
                                    file_size = os.path.getsize(item_path)
                                    files_to_send.append({
                                        'src_path': item_path,
                                        'rel_path': rel_path.replace("\\", "/"),
                                        'size': file_size,
                                        'category': 'AppData'
                                    })
                                except Exception:
                                    pass
            except Exception as e:
                print(f"[Network] AppData export exception: {e}")

        if not files_to_send:
            app.after(0, lambda: show_network_error(app, "No files found to migrate in the selected folders!"))
            return

        # Setup Sender engine hooks
        total_size = sum(f['size'] for f in files_to_send)
        total_files = len(files_to_send)

        # Triggers UI safe updates
        app.after(0, lambda: show_network_progress(app, total_files, total_size, "sender"))

        def progress_callback(current_file, bytes_sent, files_processed, total):
            app.after(0, lambda: update_sender_progress(app, current_file, bytes_sent, files_processed, total))

        def completion_callback(summary_text):
            app.after(0, lambda: show_network_completion(app, summary_text))

        def error_callback(err_msg):
            app.after(0, lambda: show_network_error(app, err_msg))

        global current_sender
        current_sender = network_engine.PCMNetworkSender(
            clean_code, 
            files_to_send, 
            progress_callback, 
            completion_callback, 
            error_callback,
            receiver_ip=receiver_ip
        )
        
        current_sender.run()

    t = threading.Thread(target=do_scan_and_send, daemon=True)
    t.start()

# Global UI state objects for progress tracking
progress_widgets = {}

def show_network_progress(app, total_files, total_size, role):
    """Unified network streaming progress bar display."""
    app.set_title_subtitle("Network Migration in Progress", "Transferring data securely...")
    app.clear_container()

    header = HeaderPanel(app.container, title="Network Transfer", subtitle="Please do not disconnect the network or turn off either computer.")
    header.pack(fill="x", pady=(0, 10))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    # UI Widgets creation
    role_text = "Sending your files to the new computer..." if role == "sender" else "Receiving files from your old computer..."
    role_lbl = ctk.CTkLabel(card, text=role_text, font=AppFonts.BODY_BOLD, text_color=TEXT_PRIMARY)
    role_lbl.pack(pady=(15, 5))

    current_file_lbl = ctk.CTkLabel(card, text="Connecting...", font=AppFonts.SMALL, text_color=TEXT_SECONDARY, wraplength=550)
    current_file_lbl.pack(pady=5)

    progress_bar = ctk.CTkProgressBar(card, orientation="horizontal", width=500, progress_color=ACCENT_BLUE)
    progress_bar.pack(pady=15)
    progress_bar.set(0.0)

    stats_lbl = ctk.CTkLabel(
        card, 
        text="Speed: 0.00 MB/s  |  Remaining: Estimating...  |  Files: 0 of 0", 
        font=AppFonts.BODY, 
        text_color=TEXT_PRIMARY
    )
    stats_lbl.pack(pady=10)

    cancel_btn = ctk.CTkButton(
        card, 
        text="Abort Migration", 
        font=AppFonts.BODY_BOLD, 
        fg_color=DANGER_RED,
        hover_color="#CC005F",
        command=lambda: abort_migration(app, role)
    )
    cancel_btn.pack(pady=15)

    # Register tracking stats
    global progress_widgets
    progress_widgets = {
        'total_files': total_files,
        'total_size': total_size,
        'bytes_transferred': 0,
        'start_time': time.time(),
        'last_update_time': time.time(),
        'last_update_bytes': 0,
        'current_speed': 0,
        
        # UI controls
        'current_file_lbl': current_file_lbl,
        'progress_bar': progress_bar,
        'stats_lbl': stats_lbl,
        'cancel_btn': cancel_btn
    }

def update_receiver_progress(app, current_file, bytes_read, files_processed, total_files):
    update_progress_stats(current_file, bytes_read, files_processed, total_files)

def update_sender_progress(app, current_file, bytes_sent, files_processed, total_files):
    update_progress_stats(current_file, bytes_sent, files_processed, total_files)

def update_progress_stats(current_file, bytes_delta, files_processed, total_files):
    """Performs dynamic MB/s speed estimates, ETA and progress modifications."""
    global progress_widgets
    if not progress_widgets:
        return
        
    # Increment counters
    progress_widgets['bytes_transferred'] += bytes_delta
    
    current_time = time.time()
    elapsed = current_time - progress_widgets['start_time']
    
    # Calculate speed every 0.5s for display stability
    time_delta = current_time - progress_widgets['last_update_time']
    if time_delta >= 0.5:
        bytes_delta_chunk = progress_widgets['bytes_transferred'] - progress_widgets['last_update_bytes']
        speed = bytes_delta_chunk / time_delta # bytes/sec
        progress_widgets['current_speed'] = speed / (1024 * 1024) # MB/s
        
        progress_widgets['last_update_time'] = current_time
        progress_widgets['last_update_bytes'] = progress_widgets['bytes_transferred']

    current_speed_mbs = progress_widgets['current_speed']
    
    # Calculate overall progress ratio
    total_size = progress_widgets['total_size']
    ratio = 0.0
    if total_size > 0:
        ratio = progress_widgets['bytes_transferred'] / total_size
        ratio = min(max(ratio, 0.0), 1.0)
        
    # Calculate remaining time
    eta_text = "Estimating..."
    if ratio > 0.02 and current_speed_mbs > 0:
        remaining_bytes = total_size - progress_widgets['bytes_transferred']
        remaining_seconds = remaining_bytes / (current_speed_mbs * 1024 * 1024)
        if remaining_seconds > 60:
            eta_text = f"{int(remaining_seconds // 60)}m {int(remaining_seconds % 60)}s"
        else:
            eta_text = f"{int(remaining_seconds)}s"

    # Update GUI widgets
    try:
        progress_widgets['current_file_lbl'].configure(text=f"Current: {current_file}")
        progress_widgets['progress_bar'].set(ratio)
        progress_widgets['stats_lbl'].configure(
            text=f"Speed: {current_speed_mbs:.2f} MB/s  |  "
                 f"Remaining: {eta_text}  |  "
                 f"Files: {files_processed} of {total_files}  |  "
                 f"{progress_widgets['bytes_transferred'] / (1024*1024*1024):.2f} GB of {total_size / (1024*1024*1024):.2f} GB"
        )
    except Exception:
        pass

def abort_migration(app, role):
    """Clean thread shutdowns on termination aborts."""
    global current_receiver, current_sender
    if role == "receiver" and current_receiver:
        current_receiver.stop()
        current_receiver = None
    elif role == "sender" and current_sender:
        current_sender.stop()
        current_sender = None
        
    network_engine.remove_firewall_rule()
    show_network_role_selection(app)

def show_network_completion(app, summary):
    """Completion screen displaying successful migration logs."""
    network_engine.remove_firewall_rule()
    app.set_title_subtitle("Network Migration Complete", "Success")
    app.clear_container()

    header = HeaderPanel(app.container, title="Migration Succeeded!", subtitle="Network migration was fully completed.")
    header.pack(fill="x", pady=(0, 20))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    success_lbl = ctk.CTkLabel(card, text="✅", font=("Segoe UI", 56, "normal"), text_color=SUCCESS_GREEN)
    success_lbl.pack(pady=(20, 5))

    heading_lbl = ctk.CTkLabel(card, text="Your files have been moved!", font=AppFonts.TITLE, text_color=TEXT_PRIMARY)
    heading_lbl.pack(pady=5)

    summary_lbl = ctk.CTkLabel(card, text=summary, font=AppFonts.BODY, text_color=TEXT_SECONDARY, wraplength=550)
    summary_lbl.pack(pady=15, padx=20)

    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(pady=20)

    back_btn = ctk.CTkButton(
        btn_frame, 
        text="Back to Welcome", 
        font=AppFonts.BODY_BOLD, 
        fg_color=BORDER_COLOR,
        hover_color=ACCENT_BLUE,
        command=lambda: show_method_selection(app),
        width=160
    )
    back_btn.pack(side="left", padx=10)

    action_btn = ctk.CTkButton(
        btn_frame, 
        text="Close Application", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=app.destroy,
        width=160
    )
    action_btn.pack(side="right", padx=10)

def show_network_error(app, error_msg):
    """Unified error screen showing socket / handshake failures."""
    network_engine.remove_firewall_rule()
    app.set_title_subtitle("Network Error Encountered", "Error")
    app.clear_container()

    header = HeaderPanel(app.container, title="Transfer Error", subtitle="Something went wrong during the network migration.")
    header.pack(fill="x", pady=(0, 20))

    card = PremiumCard(app.container)
    card.pack(fill="both", expand=True, padx=20, pady=10)

    err_lbl = ctk.CTkLabel(card, text="❌", font=("Segoe UI", 56, "normal"), text_color=DANGER_RED)
    err_lbl.pack(pady=(20, 5))

    heading_lbl = ctk.CTkLabel(card, text="An Error Occurred", font=AppFonts.TITLE, text_color=TEXT_PRIMARY)
    heading_lbl.pack(pady=5)

    desc_lbl = ctk.CTkLabel(card, text=error_msg, font=AppFonts.BODY, text_color=TEXT_SECONDARY, wraplength=550)
    desc_lbl.pack(pady=15, padx=20)

    retry_btn = ctk.CTkButton(
        card, 
        text="Retry Setup", 
        font=AppFonts.BODY_BOLD, 
        fg_color=ACCENT_BLUE,
        hover_color="#2563EB",
        command=lambda: show_network_role_selection(app)
    )
    retry_btn.pack(pady=20)
