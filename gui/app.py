import os
import sys
import json
import customtkinter as ctk
from gui.components import BG_COLOR, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_BLUE, AppFonts, CARD_COLOR, BORDER_COLOR
import scanner
import manifest

def get_settings_file_path():
    appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    pcm_dir = os.path.join(appdata, "PCM")
    os.makedirs(pcm_dir, exist_ok=True)
    return os.path.join(pcm_dir, "settings.json")

def load_app_settings():
    path = get_settings_file_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"appearance_mode": "system"}

def save_app_settings(settings):
    path = get_settings_file_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
    except Exception:
        pass

class PCMApp(ctk.CTk):
    def __init__(self, mode="export"):
        super().__init__()
        
        # Window configuration
        self.title(f"PCM (PC Mover) V{manifest.CURRENT_VERSION}")
        self.geometry("1024x768")
        self.minsize(980, 700)
        self.configure(fg_color=BG_COLOR)
        
        # Center the window on screen
        self.center_window()
        
        # Styling initialization
        self.settings = load_app_settings()
        self.appearance_mode = self.settings.get("appearance_mode", "system")
        ctk.set_appearance_mode(self.appearance_mode)
        ctk.set_default_color_theme("blue")
        
        # Shared state
        self.mode = mode  # "export" or "import"
        self.user_profiles = []
        self.selected_profile = None        # Primary profile (first selected, backward compat)
        self.selected_profiles = []         # All checked profiles for multi-user export
        self.all_users_folders_info = {}    # {username: folders_info} for multi-user scan
        self.folders_info = {}              # Aggregated folder info for the checklist view
        self.selected_folders = []
        self.migration_size_bytes = 0       # Estimated bytes to transfer (for progress %)
        self.custom_items = []              # Custom files/folders selected manually
        
        self.selected_drive = None          # Selected removable drive (e.g. {'letter': 'E:', ...})
        self.manifest_data = None           # Read when in import mode
        self.conflict_pref = "replace"      # Default conflict resolution policy
        self.user_mappings = []             # Import: [{'src_username': str, 'dest_profile': UserProfile}]
        self.transport_drive = None         # Path to the PCM transport drive root (import mode)
        
        # Container frame for current screen
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Settings Gear Cog Button (absolute position at top-right)
        self.settings_btn = ctk.CTkButton(
            self,
            text="⚙",
            font=("Segoe UI", 18, "normal"),
            width=30,
            height=30,
            fg_color="transparent",
            hover_color=CARD_COLOR,
            text_color=TEXT_SECONDARY,
            command=self.show_settings_popup
        )
        self.settings_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
        
        # Show Loading spinner/text to user instantly
        loading_lbl = ctk.CTkLabel(
            self.container, 
            text="PCM (PC Mover)", 
            font=("Segoe UI", 26, "bold"), 
            text_color=TEXT_PRIMARY
        )
        loading_lbl.pack(pady=(160, 10))
        
        loading_sub = ctk.CTkLabel(
            self.container, 
            text="Loading program libraries and modules...", 
            font=("Segoe UI", 13, "normal"), 
            text_color=TEXT_SECONDARY
        )
        loading_sub.pack(pady=5)
        
        self.progress = ctk.CTkProgressBar(self.container, width=250, fg_color="#2D2D2D", progress_color=ACCENT_BLUE)
        self.progress.pack(pady=15)
        self.progress.set(0.0)
        self.progress.start()
        
        # Bind exit protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Force the OS to map/draw the window instantly so the user sees it immediately
        self.update()
        
        # Schedule program libraries and views loading as a deferred callback
        self.after(150, self.load_initial_screen)


    def load_initial_screen(self):
        """Deferred launcher that loads view modules and sets up initial screen."""
        # Stop loading progress
        try:
            self.progress.stop()
        except Exception:
            pass
            
        self.clear_container()
        
        # Load views dynamically to keep app startup instant
        from gui.export_view import show_export_welcome_screen
        from gui.import_view import show_import_welcome_screen
        from gui.network_view import show_method_selection
        
        if self.mode == "import":
            # Auto-detect if manifest exists next to running executable
            running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            self.manifest_data = manifest.read_manifest(running_dir)
            if not self.manifest_data:
                parent_dir = os.path.dirname(running_dir)
                self.manifest_data = manifest.read_manifest(parent_dir)
            show_import_welcome_screen(self)
        else:
            show_method_selection(self)

    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

    def clear_container(self):
        """Destroys all widgets in the main container frame to prepare for a new screen."""
        for widget in self.container.winfo_children():
            widget.destroy()

    def set_title_subtitle(self, title, subtitle):
        """Sets the application title bar description dynamically."""
        self.title(f"PCM (PC Mover) V{manifest.CURRENT_VERSION} - {title}")

    def switch_to_export_mode(self):
        """Force switch to export mode via manual override."""
        self.mode = "export"
        self.manifest_data = None
        self.clear_container()
        from gui.export_view import show_export_welcome_screen
        show_export_welcome_screen(self)

    def switch_to_import_mode(self):
        """Force switch to import mode via manual override."""
        self.mode = "import"
        self.clear_container()
        from gui.import_view import show_import_welcome_screen
        show_import_welcome_screen(self)

    def on_closing(self):
        """Clean shutdown handler to shut down network threads and firewall exceptions."""
        print("[App] Shutting down application...")
        # Terminate any running receiver or sender
        from gui.network_view import current_receiver, current_sender
        import network_engine
        try:
            if current_receiver:
                current_receiver.stop()
            if current_sender:
                current_sender.stop()
        except Exception:
            pass
        
        # Clean firewall rules
        try:
            network_engine.remove_firewall_rule()
        except Exception:
            pass
            
        self.destroy()
        sys.exit(0)

    def set_theme(self, theme_mode):
        self.appearance_mode = theme_mode
        self.settings["appearance_mode"] = theme_mode
        save_app_settings(self.settings)
        ctk.set_appearance_mode(theme_mode)

    def show_settings_popup(self):
        # Create a small custom modal window for settings
        popup = ctk.CTkToplevel(self)
        popup.title("Settings")
        popup.geometry("320x220")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        
        # Center popup relative to main window
        self.update_idletasks()
        mx = self.winfo_x()
        my = self.winfo_y()
        mw = self.winfo_width()
        mh = self.winfo_height()
        popup.geometry(f"+{mx + mw//2 - 160}+{my + mh//2 - 110}")
        
        popup.configure(fg_color=BG_COLOR)
        
        # Title
        title_lbl = ctk.CTkLabel(popup, text="Settings", font=AppFonts.HEADING_MEDIUM, text_color=TEXT_PRIMARY)
        title_lbl.pack(pady=(20, 10))
        
        # Theme Section
        theme_lbl = ctk.CTkLabel(popup, text="Appearance Mode:", font=AppFonts.BODY, text_color=TEXT_SECONDARY)
        theme_lbl.pack(pady=5)
        
        theme_var = ctk.StringVar(value=self.appearance_mode.capitalize())
        
        def on_theme_change(choice):
            mode = choice.lower()
            self.set_theme(mode)
            
        theme_menu = ctk.CTkOptionMenu(
            popup,
            values=["System", "Light", "Dark"],
            variable=theme_var,
            command=on_theme_change,
            fg_color=ACCENT_BLUE,
            button_color=ACCENT_BLUE
        )
        theme_menu.pack(pady=5)
        
        # Close Button
        close_btn = ctk.CTkButton(
            popup,
            text="Close",
            font=AppFonts.BODY_BOLD,
            fg_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            command=popup.destroy
        )
        close_btn.pack(pady=(20, 10))

