import customtkinter as ctk
import manifest
from utils import format_bytes

# Premium Visual Style Tokens
BG_COLOR = "#121212"
CARD_COLOR = "#1E1E1E"
ACCENT_BLUE = "#3A86FF"
SUCCESS_GREEN = "#38B000"
WARNING_YELLOW = "#FFBE0B"
DANGER_RED = "#FF006E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0A0"
BORDER_COLOR = "#2D2D2D"

class AppFonts:
    @staticmethod
    def initialize():
        # Setup fonts using system families like Inter, Outfit, Segoe UI or Arial
        # CustomTkinter falls back cleanly if families aren't present
        pass
    
    TITLE = ("Segoe UI", 22, "bold")
    SUBTITLE = ("Segoe UI", 14, "normal")
    BODY = ("Segoe UI", 13, "normal")
    BODY_BOLD = ("Segoe UI", 13, "bold")
    SMALL = ("Segoe UI", 11, "normal")
    HEADING_MEDIUM = ("Segoe UI", 16, "bold")

class PremiumCard(ctk.CTkFrame):
    """A card-like frame with rounded corners and premium styling."""
    def __init__(self, master, **kwargs):
        super().__init__(
            master, 
            fg_color=CARD_COLOR, 
            border_color=BORDER_COLOR, 
            border_width=1, 
            corner_radius=12,
            **kwargs
        )

class HeaderPanel(ctk.CTkFrame):
    """Standard header banner displayed across all screens."""
    def __init__(self, master, title=None, subtitle="File Migration Utility", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        if title is None:
            title = f"PCM (PC Mover) V{manifest.CURRENT_VERSION}"
        
        # Grid layout
        self.columnconfigure(0, weight=1)
        
        # Title
        self.title_label = ctk.CTkLabel(
            self, 
            text=title, 
            font=AppFonts.TITLE, 
            text_color=TEXT_PRIMARY,
            anchor="w"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        
        # Subtitle
        self.sub_label = ctk.CTkLabel(
            self, 
            text=subtitle, 
            font=AppFonts.SUBTITLE, 
            text_color=TEXT_SECONDARY,
            anchor="w"
        )
        self.sub_label.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        # Divider Line
        self.divider = ctk.CTkFrame(self, height=2, fg_color=BORDER_COLOR)
        self.divider.grid(row=2, column=0, sticky="we", pady=(0, 15))

class ScrollableFolderList(ctk.CTkScrollableFrame):
    """
    Scrollable checklist containing folders with item counts and sizes.
    Allows user to select which folders to export.
    """
    def __init__(self, master, folders_dict, **kwargs):
        border_width = kwargs.pop('border_width', 1)
        corner_radius = kwargs.pop('corner_radius', 12)
        super().__init__(
            master, 
            fg_color=CARD_COLOR, 
            label_text="Select Folders to Migrate",
            label_font=AppFonts.HEADING_MEDIUM,
            label_text_color=TEXT_PRIMARY,
            border_color=BORDER_COLOR,
            border_width=border_width,
            corner_radius=corner_radius,
            **kwargs
        )
        self.checkboxes = {}
        self.on_toggle_callback = None
        
        # Add Select All row if there are items
        if folders_dict:
            sel_all_frame = ctk.CTkFrame(self, fg_color="transparent")
            sel_all_frame.pack(fill="x", pady=(2, 6), padx=8)
            
            # Check if any folders actually exist to set default select all state
            any_exists = any(info.exists for info in folders_dict.values())
            self.select_all_var = ctk.StringVar(value="on" if any_exists else "off")
            
            self.select_all_cb = ctk.CTkCheckBox(
                sel_all_frame,
                text="Select All / Deselect All",
                font=AppFonts.BODY_BOLD,
                text_color=ACCENT_BLUE,
                variable=self.select_all_var,
                onvalue="on",
                offvalue="off",
                checkmark_color=TEXT_PRIMARY,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE,
                command=self.toggle_all
            )
            self.select_all_cb.pack(side="left", anchor="w")
            
            # Simple divider
            div = ctk.CTkFrame(self, height=1, fg_color=BORDER_COLOR)
            div.pack(fill="x", pady=(0, 6), padx=8)
        
        # Add checkbox row for each folder
        for idx, (name, folder_info) in enumerate(folders_dict.items()):
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(fill="x", pady=4, padx=8)
            
            # Checkbox
            var = ctk.StringVar(value="on" if folder_info.exists else "off")
            cb = ctk.CTkCheckBox(
                row_frame, 
                text=name, 
                font=AppFonts.BODY_BOLD,
                text_color=TEXT_PRIMARY,
                variable=var,
                onvalue="on",
                offvalue="off",
                state="normal" if folder_info.exists else "disabled",
                checkmark_color=TEXT_PRIMARY,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE
            )
            cb.pack(side="left", anchor="w")
            
            self.checkboxes[name] = {
                'var': var,
                'checkbox': cb,
                'info': folder_info
            }
            
            # Size details
            if folder_info.exists:
                desc = f"{folder_info.file_count} files  |  {folder_info.get_friendly_size()}"
                text_color = TEXT_PRIMARY
            else:
                desc = "Folder not found / empty"
                text_color = TEXT_SECONDARY
                
            details_lbl = ctk.CTkLabel(
                row_frame, 
                text=desc, 
                font=AppFonts.SMALL,
                text_color=text_color
            )
            details_lbl.pack(side="right", anchor="e", padx=(10, 0))

    def get_selected_folders(self):
        """Returns list of folder names currently checked."""
        selected = []
        for name, data in self.checkboxes.items():
            if data['var'].get() == "on":
                selected.append(name)
        return selected

    def toggle_all(self):
        val = self.select_all_var.get()
        for name, data in self.checkboxes.items():
            if data['checkbox'].cget('state') == 'normal':
                data['var'].set(val)
        if self.on_toggle_callback:
            self.on_toggle_callback()

class ScrollableSteamGamesList(ctk.CTkScrollableFrame):
    """
    Scrollable checklist containing installed Steam games with their size on disk.
    Allows user to select which games to export.
    """
    def __init__(self, master, games_dict, **kwargs):
        border_width = kwargs.pop('border_width', 1)
        corner_radius = kwargs.pop('corner_radius', 12)
        super().__init__(
            master, 
            fg_color=CARD_COLOR, 
            label_text="Select Steam Games to Migrate",
            label_font=AppFonts.HEADING_MEDIUM,
            label_text_color=TEXT_PRIMARY,
            border_color=BORDER_COLOR,
            border_width=border_width,
            corner_radius=corner_radius,
            **kwargs
        )
        self.checkboxes = {}
        self.on_toggle_callback = None
        
        # Add Select All row if there are items
        if games_dict:
            sel_all_frame = ctk.CTkFrame(self, fg_color="transparent")
            sel_all_frame.pack(fill="x", pady=(2, 6), padx=8)
            
            self.select_all_var = ctk.StringVar(value="off") # Default Steam games to off
            
            self.select_all_cb = ctk.CTkCheckBox(
                sel_all_frame,
                text="Select All / Deselect All",
                font=AppFonts.BODY_BOLD,
                text_color=ACCENT_BLUE,
                variable=self.select_all_var,
                onvalue="on",
                offvalue="off",
                checkmark_color=TEXT_PRIMARY,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE,
                command=self.toggle_all
            )
            self.select_all_cb.pack(side="left", anchor="w")
            
            # Simple divider
            div = ctk.CTkFrame(self, height=1, fg_color=BORDER_COLOR)
            div.pack(fill="x", pady=(0, 6), padx=8)
        
        # Add checkbox row for each game
        if not games_dict:
            # Show empty label
            empty_lbl = ctk.CTkLabel(
                self, 
                text="No Steam games detected on this system.", 
                font=AppFonts.BODY,
                text_color=TEXT_SECONDARY
            )
            empty_lbl.pack(pady=40)
            return

        for idx, (appid, game) in enumerate(games_dict.items()):
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(fill="x", pady=4, padx=8)
            
            # Checkbox
            var = ctk.StringVar(value="off") # default unchecked, since steam games can be HUGE!
            cb = ctk.CTkCheckBox(
                row_frame, 
                text=game['name'], 
                font=AppFonts.BODY_BOLD,
                text_color=TEXT_PRIMARY,
                variable=var,
                onvalue="on",
                offvalue="off",
                checkmark_color=TEXT_PRIMARY,
                fg_color=ACCENT_BLUE,
                hover_color=ACCENT_BLUE
            )
            cb.pack(side="left", anchor="w")
            
            self.checkboxes[appid] = {
                'var': var,
                'checkbox': cb,
                'game': game
            }
            
            # Size details
            desc = format_bytes(game['size_bytes'])
            details_lbl = ctk.CTkLabel(
                row_frame, 
                text=desc, 
                font=AppFonts.SMALL,
                text_color=TEXT_PRIMARY
            )
            details_lbl.pack(side="right", anchor="e", padx=(10, 0))

    def get_selected_games(self):
        """Returns list of appids currently checked."""
        selected = []
        for appid, data in self.checkboxes.items():
            if data['var'].get() == "on":
                selected.append(appid)
        return selected

    def toggle_all(self):
        val = self.select_all_var.get()
        for appid, data in self.checkboxes.items():
            if data['checkbox'].cget('state') == 'normal':
                data['var'].set(val)
        if self.on_toggle_callback:
            self.on_toggle_callback()

