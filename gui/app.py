import os
import sys
import customtkinter as ctk
from gui.components import BG_COLOR, TEXT_PRIMARY, AppFonts
import scanner
import manifest

class PCMApp(ctk.CTk):
    def __init__(self, mode="export"):
        super().__init__()
        
        # Window configuration
        self.title(f"PCM (PC Mover) V{manifest.CURRENT_VERSION}")
        self.geometry("780x640")
        self.minsize(700, 580)
        self.configure(fg_color=BG_COLOR)
        
        # Center the window on screen
        self.center_window()
        
        # Styling initialization
        ctk.set_appearance_mode("dark")
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

        self.selected_drive = None          # Selected removable drive (e.g. {'letter': 'E:', ...})
        self.manifest_data = None           # Read when in import mode
        self.conflict_pref = "replace"      # Default conflict resolution policy
        self.user_mappings = []             # Import: [{'src_username': str, 'dest_profile': UserProfile}]
        self.transport_drive = None         # Path to the PCM transport drive root (import mode)
        
        # Container frame for current screen
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Import module views locally to prevent circular dependencies
        from gui.export_view import show_export_welcome_screen
        from gui.import_view import show_import_welcome_screen
        from gui.network_view import show_method_selection
        
        # Bind exit protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Setup initial screen based on auto-detected mode
        if self.mode == "import":
            # Auto-detect if manifest exists in running dir
            running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            self.manifest_data = manifest.read_manifest(running_dir)
            if not self.manifest_data:
                # If we're launched but don't find it, we'll prompt user on the import screen
                pass
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
