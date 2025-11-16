import os
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from io import BytesIO
from functools import lru_cache
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- ensure dependencies ----

import customtkinter as ctk
from PIL import Image, ImageTk
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TPOS, TRCK, COMM, APIC
# Appearance - Start with system theme
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("dark-blue")

JSON_FIND_RE = re.compile(r"\{.*\}", re.DOTALL)


# -------------------------------
# Helper functions for MP3 JSON & cover
# -------------------------------
@lru_cache(maxsize=100)
def extract_json_from_mp3_cached(path):
    """Cached version of extract_json_from_mp3"""
    return extract_json_from_mp3(path)

def extract_json_from_mp3(path):
    """Return parsed JSON dict or None."""
    try:
        audio = MP3(path)
        if not audio.tags:
            return None
        # Gather COMM frames
        comms = [v for k, v in audio.tags.items() if k.startswith("COMM")]
        for c in comms:
            text = ""
            try:
                # COMM frame: .text may be list
                text = "".join(c.text) if hasattr(c, "text") else str(c)
            except Exception:
                text = str(c)
            m = JSON_FIND_RE.search(text)
            if m:
                raw = m.group(0)
                try:
                    return json.loads(raw)
                except Exception:
                    # try sanitize
                    try:
                        return json.loads(raw.replace("'", '"'))
                    except Exception:
                        continue
        return None
    except Exception:
        return None


def read_cover_from_mp3(path):
    """Return (PIL Image, mime) or (None, None)."""
    try:
        tags = ID3(path)
    except Exception:
        return None, None
    apics = tags.getall("APIC")
    if not apics:
        return None, None
    ap = apics[0]
    try:
        img = Image.open(BytesIO(ap.data))
        return img, ap.mime
    except Exception:
        return None, None


def write_id3_tags(path, title=None, artist=None, album=None, track=None, disc=None, date=None, cover_bytes=None, cover_mime="image/jpeg"):
    """Write provided tags to file (only provided ones). Returns True/False."""
    try:
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        if title is not None:
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=title))
        if artist is not None:
            tags.delall("TPE1")
            tags.add(TPE1(encoding=3, text=artist))
        if album is not None:
            tags.delall("TALB")
            tags.add(TALB(encoding=3, text=album))
        if date is not None:
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=str(date)))
        if track is not None:
            tags.delall("TRCK")
            tags.add(TRCK(encoding=3, text=str(track)))
        if disc is not None:
            tags.delall("TPOS")
            tags.add(TPOS(encoding=3, text=str(disc)))
        if cover_bytes:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_bytes))
        tags.save(path)
        return True
    except Exception as e:
        print("Error writing tags:", e)
        return False


# -------------------------------
# Progress Dialog
# -------------------------------
class ProgressDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Processing..."):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x120")
        self.resizable(False, False)
        
        # Center the dialog
        self.transient(parent)
        self.grab_set()
        
        # Make it modal
        self.focus_set()
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        self.label = ctk.CTkLabel(self, text="Starting...")
        self.label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.progress.set(0)
        
        self.percent_label = ctk.CTkLabel(self, text="0%")
        self.percent_label.grid(row=1, column=0, padx=20, pady=10, sticky="e")
        
        self.cancel_button = ctk.CTkButton(self, text="Cancel", command=self.cancel)
        self.cancel_button.grid(row=2, column=0, padx=20, pady=(10, 20))
        
        self.cancelled = False
        
    def update_progress(self, current, total, text=None):
        if self.cancelled:
            return False
            
        progress = current / total if total > 0 else 0
        self.progress.set(progress)
        self.percent_label.configure(text=f"{int(progress * 100)}%")
        
        if text:
            self.label.configure(text=text)
        else:
            self.label.configure(text=f"Processing {current} of {total} files...")
            
        self.update()
        return True
        
    def cancel(self):
        self.cancelled = True
        self.label.configure(text="Cancelling...")
        self.cancel_button.configure(state="disabled")


# -------------------------------
# Rule row (CTk widget)
# -------------------------------
class RuleRow(ctk.CTkFrame):
    def __init__(self, master, fields, operators, move_callback, delete_callback, **kwargs):
        super().__init__(master, **kwargs)

        self.move_callback = move_callback
        self.delete_callback = delete_callback

        # layout
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=1)
        self.grid_columnconfigure(4, weight=0)
        self.grid_columnconfigure(5, weight=1)
        self.grid_columnconfigure(6, weight=0)
        self.grid_columnconfigure(7, weight=0)
        self.grid_columnconfigure(8, weight=0)

        self.if_label = ctk.CTkLabel(self, text="IF")
        self.if_label.grid(row=0, column=0, padx=(6, 4), pady=6, sticky="w")

        self.field_var = tk.StringVar()
        self.field_menu = ctk.CTkOptionMenu(self, values=fields, variable=self.field_var, width=120)
        self.field_menu.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        self.field_var.set(fields[0])

        self.op_var = tk.StringVar()
        self.op_menu = ctk.CTkOptionMenu(self, values=operators, variable=self.op_var, width=140)
        self.op_menu.grid(row=0, column=2, padx=4, pady=6, sticky="w")
        self.op_var.set(operators[0])

        self.value_entry = ctk.CTkEntry(self, placeholder_text="value (leave empty for 'is empty' etc.)")
        self.value_entry.grid(row=0, column=3, padx=6, pady=6, sticky="ew")

        self.then_label = ctk.CTkLabel(self, text="THEN")
        self.then_label.grid(row=0, column=4, padx=(10, 4), pady=6, sticky="w")

        self.template_entry = ctk.CTkEntry(self, placeholder_text="{Artist} (feat. {CoverArtist})")
        self.template_entry.grid(row=0, column=5, padx=6, pady=6, sticky="ew")

        # small action buttons
        self.up_btn = ctk.CTkButton(self, text="▲", width=28, command=lambda: move_callback(self, -1))
        self.up_btn.grid(row=0, column=6, padx=4, pady=6)
        self.down_btn = ctk.CTkButton(self, text="▼", width=28, command=lambda: move_callback(self, 1))
        self.down_btn.grid(row=0, column=7, padx=2, pady=6)
        self.del_btn = ctk.CTkButton(self, text="✖", width=28, fg_color="#b33", hover_color="#c55", command=lambda: delete_callback(self))
        self.del_btn.grid(row=0, column=8, padx=(6, 8), pady=6)

    def get_rule(self):
        return {
            "if_field": self.field_var.get(),
            "if_operator": self.op_var.get(),
            "if_value": self.value_entry.get(),
            "then_template": self.template_entry.get(),
        }


# -------------------------------
# Main Application
# -------------------------------
class DFApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DF — Metadata Customizer")
        self.geometry("1350x820")
        self.minsize(1100, 700)

        # Data model
        self.mp3_files = []            # list of file paths
        self.current_index = None
        self.current_json = None
        self.current_cover_bytes = None
        self.latest_versions = {}      # title -> latest version string
        self.song_versions = {}        # title -> [versions]
        # Remove 'album' from column order since JSON doesn't have album data
        self.column_order = ["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"]
        self.file_data_cache = {}      # Cache for file metadata
        self.scan_thread = None        # Background scanning thread
        self.visible_file_indices = [] # Track visible files for prev/next navigation
        self.progress_dialog = None    # Progress dialog reference

        # Theme management
        self.current_theme = "System"  # Start with system theme
        self.theme_icon_cache = {}     # Cache for theme icons

        # Default fields/operators
        self.rule_fields = ["Title", "Artist", "CoverArtist", "Version", "Discnumber", "Track", "Date", "Comment"]
        self.rule_ops = ["is", "contains", "starts with", "ends with", "is empty", "is not empty", "is latest version", "is not latest version"]

        # Build UI
        self._build_ui()
        # default presets container
        self.presets = {}

    def _build_ui(self):
        # Use a PanedWindow for draggable splitter
        self.paned = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", sashwidth=6)
        self.paned.pack(fill="both", expand=True, padx=8, pady=8)

        # Left (song list) frame
        self.left_frame = ctk.CTkFrame(self.paned, corner_radius=8)
        self.paned.add(self.left_frame, minsize=620)  # left bigger by default

        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(2, weight=1)  # Treeview row expands
        self.left_frame.grid_rowconfigure(3, weight=0)  # Status row fixed

        # Top controls: folder select + search + select all
        top_ctl = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        top_ctl.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        top_ctl.grid_columnconfigure(2, weight=1)  # Give more weight to search

        self.btn_select_folder = ctk.CTkButton(top_ctl, text="Select Folder", command=self.select_folder)
        self.btn_select_folder.grid(row=0, column=0, padx=(0, 8))

        self.btn_scan_versions = ctk.CTkButton(top_ctl, text="Scan Versions", command=self.scan_versions)
        self.btn_scan_versions.grid(row=0, column=1, padx=(0, 8))

        self.search_var = tk.StringVar()
        self.entry_search = ctk.CTkEntry(top_ctl, placeholder_text="Search title / artist / coverartist / disc / track", textvariable=self.search_var)
        self.entry_search.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", self.on_search_keyrelease)

        self.select_all_var = tk.BooleanVar(value=False)
        self.chk_select_all = ctk.CTkCheckBox(top_ctl, text="Select All", variable=self.select_all_var, command=self.on_select_all)
        self.chk_select_all.grid(row=0, column=3, padx=(0, 0))

        # Sort controls
        sort_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        sort_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        sort_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(sort_frame, text="Sort by:").grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.sort_var = tk.StringVar(value="title")
        # All available sort options - remove 'album' from sort options
        sort_options = ["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"]
        sort_combo = ttk.Combobox(sort_frame, textvariable=self.sort_var, state="readonly", width=12,
                                 values=sort_options)
        sort_combo.grid(row=0, column=1, sticky="w", padx=(0, 8))
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_tree())
        
        self.sort_order_var = tk.StringVar(value="asc")
        sort_order_combo = ttk.Combobox(sort_frame, textvariable=self.sort_order_var, state="readonly", width=8,
                                       values=["asc", "desc"])
        sort_order_combo.grid(row=0, column=2, sticky="w")
        sort_order_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_tree())

        # Treeview song list
        tree_frame = ctk.CTkFrame(self.left_frame)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 4))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Extended columns to show all JSON elements including Comment - removed 'album'
        columns = tuple(self.column_order)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        
        # Configure treeview style - will be updated by theme
        self.style = ttk.Style()
        self._update_treeview_style()
        
        # Configure columns - removed album column
        column_configs = {
            "title": ("Title", 180, "w"),
            "artist": ("Artist", 100, "w"),
            "coverartist": ("Cover Artist", 100, "w"),
            "version": ("Version", 70, "center"),
            "disc": ("Disc", 40, "center"),
            "track": ("Track", 40, "center"),
            "date": ("Date", 70, "center"),
            "comment": ("Comment", 120, "w"),
            "file": ("File", 120, "w")
        }

        for col in self.column_order:
            heading, width, anchor = column_configs[col]
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor=anchor)

        # Enable column reordering
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.dragged_column = None

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Vertical scrollbar
        self.tree_scroll_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll_v.set)
        
        # Horizontal scrollbar
        self.tree_scroll_h = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.tree_scroll_h.set)
        
        # Grid the tree and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_v.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_h.grid(row=1, column=0, sticky="ew")

        # Status row at bottom
        status_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        status_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        status_frame.grid_columnconfigure(0, weight=1)
        
        self.lbl_file_info = ctk.CTkLabel(status_frame, text="No folder selected")
        self.lbl_file_info.grid(row=0, column=0, sticky="w")
        
        self.lbl_selection_info = ctk.CTkLabel(status_frame, text="0 song(s) selected")
        self.lbl_selection_info.grid(row=0, column=1, sticky="e")

        # Right (metadata & rules) frame
        self.right_frame = ctk.CTkFrame(self.paned, corner_radius=8)
        self.paned.add(self.right_frame, minsize=480)

        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=1)  # tab area expands
        self.right_frame.grid_rowconfigure(2, weight=2)  # preview area expands

        # Preset controls with theme toggle
        preset_row = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        preset_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        preset_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(preset_row, text="Presets:").grid(row=0, column=0, padx=(4, 8), sticky="w")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly", width=20)
        self.preset_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)

        ctk.CTkButton(preset_row, text="Save Preset", command=self.save_preset, width=80).grid(row=0, column=2, padx=4)
        ctk.CTkButton(preset_row, text="Delete", command=self.delete_preset, width=60).grid(row=0, column=3, padx=4)
        
        # Theme toggle button
        self.theme_btn = ctk.CTkButton(preset_row, text="", width=40, height=30, 
                                      command=self.toggle_theme, 
                                      fg_color="transparent",
                                      hover_color=("gray70", "gray30"))
        self.theme_btn.grid(row=0, column=4, padx=(8, 0))
        self._update_theme_button()

        # Tabs for rule builders
        self.tabview = ctk.CTkTabview(self.right_frame)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)

        # We'll keep rule containers per tab in a dict
        self.rule_containers = {}
        for name in ("Title", "Artist", "Album"):
            self._create_rule_tab(name)

        # Preview area (JSON, Cover, Output)
        preview_outer = ctk.CTkFrame(self.right_frame)
        preview_outer.grid(row=2, column=0, sticky="nsew", padx=8, pady=(6, 8))
        preview_outer.grid_columnconfigure(0, weight=2)
        preview_outer.grid_columnconfigure(1, weight=1)
        preview_outer.grid_rowconfigure(0, weight=1)

        # JSON viewer
        json_frame = ctk.CTkFrame(preview_outer)
        json_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        json_frame.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(json_frame, text="JSON (from comment)").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 4))
        
        # Configure text widget for theme
        self.json_text = tk.Text(json_frame, wrap="none", height=12)
        self._update_json_text_style()
        self.json_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.json_scroll = ttk.Scrollbar(json_frame, orient="vertical", command=self.json_text.yview)
        self.json_text.configure(yscrollcommand=self.json_scroll.set)
        self.json_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 6))

        # Cover preview on right
        cover_frame = ctk.CTkFrame(preview_outer)
        cover_frame.grid(row=0, column=1, sticky="nsew")
        cover_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(cover_frame, text="Cover Preview").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 4))
        self.cover_display = ctk.CTkLabel(cover_frame, text="No cover", corner_radius=8)
        self.cover_display.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")

        # Output preview (Title, Artist, Album, Disc, Track, Versions)
        out_frame = ctk.CTkFrame(self.right_frame)
        out_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        out_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(out_frame, text="New Title:").grid(row=0, column=0, sticky="e", padx=(6, 6), pady=(6, 2))
        self.lbl_out_title = ctk.CTkLabel(out_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_title.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(6, 2))

        ctk.CTkLabel(out_frame, text="New Artist:").grid(row=1, column=0, sticky="e", padx=(6, 6), pady=(2, 2))
        self.lbl_out_artist = ctk.CTkLabel(out_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_artist.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=(2, 2))

        ctk.CTkLabel(out_frame, text="New Album:").grid(row=2, column=0, sticky="e", padx=(6, 6), pady=(2, 6))
        self.lbl_out_album = ctk.CTkLabel(out_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_album.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=(2, 6))

        # Disc / Track / Versions small labels
        dt_frame = ctk.CTkFrame(out_frame, fg_color="transparent")
        dt_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        dt_frame.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(dt_frame, text="Disc:").grid(row=0, column=0, sticky="e", padx=(0, 4))
        self.lbl_out_disc = ctk.CTkLabel(dt_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_disc.grid(row=0, column=1, sticky="w", padx=(0, 12))

        ctk.CTkLabel(dt_frame, text="Track:").grid(row=0, column=2, sticky="e", padx=(0, 4))
        self.lbl_out_track = ctk.CTkLabel(dt_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_track.grid(row=0, column=3, sticky="w", padx=(0, 12))

        ctk.CTkLabel(dt_frame, text="All Versions:").grid(row=0, column=4, sticky="e", padx=(0, 4))
        self.lbl_out_versions = ctk.CTkLabel(dt_frame, text="", anchor="w", corner_radius=6)
        self.lbl_out_versions.grid(row=0, column=5, sticky="w", padx=(0, 12))

        # Update output preview styles
        self._update_output_preview_style()

        # Bottom buttons (Prev/Next/Apply Selected/Apply All) in one row
        bottom = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        bottom.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkButton(bottom, text="◀ Prev", command=self.prev_file).grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(bottom, text="Next ▶", command=self.next_file).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(bottom, text="Apply to Selected", command=self.apply_to_selected).grid(row=0, column=2, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(bottom, text="Apply to All", command=self.apply_to_all).grid(row=0, column=3, padx=6, pady=6, sticky="ew")

        # Set default sash location after window appears
        self.after(150, lambda: self.paned.sash_place(0, int(self.winfo_screenwidth() * 0.62), 0))

    def _update_treeview_style(self):
        """Update treeview style based on current theme"""
        if self.current_theme == "Dark" or (self.current_theme == "System" and ctk.get_appearance_mode() == "Dark"):
            # Dark theme
            self.style.theme_use('default')
            self.style.configure("Treeview", 
                               background="#2b2b2b",
                               foreground="white",
                               fieldbackground="#2b2b2b",
                               borderwidth=0)
            self.style.configure("Treeview.Heading",
                               background="#3b3b3b", 
                               foreground="white",
                               relief="flat")
            self.style.map('Treeview', background=[('selected', '#1f6aa5')])
            self.style.map('Treeview.Heading', background=[('active', '#4b4b4b')])
        else:
            # Light theme
            self.style.theme_use('default')
            self.style.configure("Treeview", 
                               background="white",
                               foreground="black",
                               fieldbackground="white",
                               borderwidth=0)
            self.style.configure("Treeview.Heading",
                               background="#f0f0f0", 
                               foreground="black",
                               relief="flat")
            self.style.map('Treeview', background=[('selected', '#0078d7')])
            self.style.map('Treeview.Heading', background=[('active', '#e0e0e0')])

    def _update_json_text_style(self):
        """Update JSON text widget style based on current theme"""
        if self.current_theme == "Dark" or (self.current_theme == "System" and ctk.get_appearance_mode() == "Dark"):
            # Dark theme
            self.json_text.configure(
                bg="#2b2b2b",
                fg="white",
                insertbackground="white",
                selectbackground="#1f6aa5"
            )
        else:
            # Light theme
            self.json_text.configure(
                bg="white",
                fg="black",
                insertbackground="black",
                selectbackground="#0078d7"
            )

    def _update_output_preview_style(self):
        """Update output preview labels style based on current theme"""
        if self.current_theme == "Dark" or (self.current_theme == "System" and ctk.get_appearance_mode() == "Dark"):
            # Dark theme
            bg_color = "#3b3b3b"
            text_color = "white"
        else:
            # Light theme
            bg_color = "#e0e0e0"
            text_color = "black"
            
        # Update all output preview labels
        for label in [self.lbl_out_title, self.lbl_out_artist, self.lbl_out_album, 
                     self.lbl_out_disc, self.lbl_out_track, self.lbl_out_versions]:
            label.configure(fg_color=bg_color, text_color=text_color)

    def _update_theme_button(self):
        """Update theme button icon based on current theme"""
        if self.current_theme == "Dark" or (self.current_theme == "System" and ctk.get_appearance_mode() == "Dark"):
            # Currently dark, show light theme icon
            self.theme_btn.configure(text="☀️")  # Sun icon for light mode
        else:
            # Currently light, show dark theme icon
            self.theme_btn.configure(text="🌙")  # Moon icon for dark mode

    def toggle_theme(self):
        """Toggle between dark and light themes"""
        if self.current_theme == "System":
            # If system, switch to explicit dark
            self.current_theme = "Dark"
        elif self.current_theme == "Dark":
            self.current_theme = "Light"
        else:
            self.current_theme = "Dark"
        
        # Apply the theme
        ctk.set_appearance_mode(self.current_theme)
        
        # Update all theme-dependent elements
        self._update_treeview_style()
        self._update_json_text_style()
        self._update_output_preview_style()
        self._update_theme_button()
        
        # Refresh the tree to apply new styles
        if self.tree.get_children():
            self.after(100, self.refresh_tree)

    def on_search_keyrelease(self, event=None):
        """Debounced search handler"""
        if hasattr(self, '_search_after_id'):
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(300, self.refresh_tree)  # 300ms delay

    def on_tree_click(self, event):
        """Handle column header clicks for reordering"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            column = self.tree.identify_column(event.x)
            column_index = int(column.replace('#', '')) - 1
            if 0 <= column_index < len(self.column_order):
                self.dragged_column = self.column_order[column_index]
                self.tree.bind('<B1-Motion>', self.on_column_drag)
                self.tree.bind('<ButtonRelease-1>', self.on_column_drop)

    def on_column_drag(self, event):
        """Visual feedback during column drag"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            column = self.tree.identify_column(event.x)
            # Could add visual feedback here if needed

    def on_column_drop(self, event):
        """Handle column reordering when dropped"""
        self.tree.unbind('<B1-Motion>')
        self.tree.unbind('<ButtonRelease-1>')
        
        if self.dragged_column:
            region = self.tree.identify_region(event.x, event.y)
            if region == "heading":
                column = self.tree.identify_column(event.x)
                drop_index = int(column.replace('#', '')) - 1
                if 0 <= drop_index < len(self.column_order):
                    # Reorder the columns
                    current_index = self.column_order.index(self.dragged_column)
                    if current_index != drop_index:
                        self.column_order.pop(current_index)
                        self.column_order.insert(drop_index, self.dragged_column)
                        self.rebuild_tree_columns()
            
            self.dragged_column = None

    def rebuild_tree_columns(self):
        """Rebuild tree columns with new order"""
        # Save current selection and scroll position
        selection = self.tree.selection()
        scroll_v = self.tree.yview()
        scroll_h = self.tree.xview()
        
        # Reconfigure columns
        for col in self.tree['columns']:
            self.tree.heading(col, text="")
        
        column_configs = {
            "title": ("Title", 180, "w"),
            "artist": ("Artist", 100, "w"),
            "coverartist": ("Cover Artist", 100, "w"),
            "version": ("Version", 70, "center"),
            "disc": ("Disc", 40, "center"),
            "track": ("Track", 40, "center"),
            "date": ("Date", 70, "center"),
            "comment": ("Comment", 120, "w"),
            "file": ("File", 120, "w")
        }
        
        # Recreate columns in new order
        self.tree['columns'] = self.column_order
        for col in self.column_order:
            heading, width, anchor = column_configs[col]
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor=anchor)
        
        # Restore selection and scroll position
        if selection:
            self.tree.selection_set(selection)
        self.tree.yview_moveto(scroll_v[0])
        self.tree.xview_moveto(scroll_h[0])

    # -------------------------
    # Rule tab creation
    # -------------------------
    def _create_rule_tab(self, name):
        tab = self.tabview.add(name)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Create a header frame with label and add button
        header_frame = ctk.CTkFrame(tab, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 5))
        header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header_frame, text=f"{name} Rules", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=8)
        
        add_btn = ctk.CTkButton(header_frame, text="+ Add Rule", width=80,
                               command=lambda: self.add_rule_to_tab(name))
        add_btn.grid(row=0, column=1, padx=8, pady=2, sticky="e")

        wrapper = ctk.CTkFrame(tab)
        wrapper.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)

        # Scrollable container for rules
        scroll = ctk.CTkScrollableFrame(wrapper)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # store container
        self.rule_containers[name.lower()] = scroll

    def add_rule_to_tab(self, tab_name):
        """Add a rule to the specified tab"""
        container = self.rule_containers.get(tab_name.lower())
        if container:
            self.add_rule(container)

    # -------------------------
    # Rule operations
    # -------------------------
    def add_rule(self, container):
        row = RuleRow(container, self.rule_fields, self.rule_ops, move_callback=self.move_rule, delete_callback=self.delete_rule)
        row.pack(fill="x", padx=6, pady=6)

        # default template suggestions based on container tab
        parent_tab = self._container_to_tab(container)
        if parent_tab == "title":
            row.template_entry.insert(0, "{CoverArtist} - {Title}")
        elif parent_tab == "artist":
            row.template_entry.insert(0, "{CoverArtist}")
        elif parent_tab == "album":
            row.template_entry.insert(0, "Archive VOL {Discnumber}")

        # hook live preview
        row.field_menu.configure(command=lambda val=None: self.update_preview())
        row.op_menu.configure(command=lambda val=None: self.update_preview())
        row.value_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        row.template_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        self.update_preview()

    def move_rule(self, widget, direction):
        container = widget.master
        children = [w for w in container.winfo_children() if isinstance(w, RuleRow)]
        if widget in children:
            idx = children.index(widget)
            new = idx + direction
            if 0 <= new < len(children):
                widget.pack_forget()
                # Repack in new position
                if direction < 0:
                    widget.pack(before=children[new], fill="x", padx=6, pady=6)
                else:
                    # place after the target
                    widget.pack(after=children[new], fill="x", padx=6, pady=6)
        self.update_preview()

    def delete_rule(self, widget):
        widget.destroy()
        self.update_preview()

    def _container_to_tab(self, container):
        # container is CTkScrollableFrame, find which key maps to it
        for k, v in self.rule_containers.items():
            if v is container:
                return k
        return None

    def collect_rules_for(self, tab):
        """Return list of rule dicts for tab name (title/artist/album)."""
        container = self.rule_containers.get(tab)
        if not container:
            return []
        rules = []
        for w in container.winfo_children():
            if isinstance(w, RuleRow):
                rules.append(w.get_rule())
        return rules

    # -------------------------
    # File / tree operations
    # -------------------------
    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.mp3_files = []
        pattern = "**/*.mp3"
        if not self._ask_include_subfolders():
            pattern = "*.mp3"
        
        # Clear cache when loading new folder
        self.file_data_cache.clear()
        extract_json_from_mp3_cached.cache_clear()
        
        # Show loading state
        self.lbl_file_info.configure(text="Scanning folder...")
        self.btn_select_folder.configure(state="disabled")
        
        # Create progress dialog
        self.progress_dialog = ProgressDialog(self, "Scanning Folder")
        
        # Scan in background thread
        def scan_folder():
            files = []
            count = 0
            total = 0
            
            # First count total files for progress
            for p in Path(folder).glob(pattern):
                if p.is_file():
                    total += 1
            
            for p in Path(folder).glob(pattern):
                if p.is_file():
                    files.append(str(p))
                    count += 1
                    # Update progress
                    if not self.progress_dialog.update_progress(count, total, f"Found {count} files..."):
                        # Cancelled
                        return None
            return files
        
        def on_scan_complete(files):
            if files is None:  # Cancelled
                self.lbl_file_info.configure(text="Scan cancelled")
                self.btn_select_folder.configure(state="normal")
                if self.progress_dialog:
                    self.progress_dialog.destroy()
                    self.progress_dialog = None
                return
                
            self.mp3_files = files
            if not self.mp3_files:
                messagebox.showwarning("No files", "No mp3 files found in that folder")
                self.lbl_file_info.configure(text="No files")
                self.btn_select_folder.configure(state="normal")
                if self.progress_dialog:
                    self.progress_dialog.destroy()
                    self.progress_dialog = None
                return
            
            self.lbl_file_info.configure(text=f"Files: {len(self.mp3_files)}")
            self.btn_select_folder.configure(state="normal")
            
            # Update progress dialog for loading data
            if self.progress_dialog:
                self.progress_dialog.label.configure(text="Loading file metadata...")
                self.progress_dialog.progress.set(0)
            
            self.populate_tree()
        
        # Start background scan
        threading.Thread(target=lambda: self.after(0, lambda: on_scan_complete(scan_folder())), daemon=True).start()

    def _ask_include_subfolders(self):
        return True

    def get_file_data(self, file_path):
        """Get cached file data with fallback"""
        if file_path not in self.file_data_cache:
            jsond = extract_json_from_mp3_cached(file_path) or {}
            self.file_data_cache[file_path] = jsond
        return self.file_data_cache[file_path]

    def populate_tree(self):
        """Populate tree with threaded data loading"""
        # Clear tree
        for it in self.tree.get_children():
            self.tree.delete(it)
        
        self.lbl_file_info.configure(text=f"Loading {len(self.mp3_files)} files...")
        
        def load_file_data():
            file_data = []
            total = len(self.mp3_files)
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.get_file_data, p): i for i, p in enumerate(self.mp3_files)}
                completed = 0
                
                for future in as_completed(futures):
                    if self.progress_dialog and self.progress_dialog.cancelled:
                        break
                        
                    i = futures[future]
                    p = self.mp3_files[i]
                    try:
                        jsond = future.result()
                        title = jsond.get("Title") or os.path.splitext(os.path.basename(p))[0]
                        artist = jsond.get("Artist") or ""
                        coverartist = jsond.get("CoverArtist") or ""
                        version = jsond.get("Version") or ""
                        disc = jsond.get("Discnumber") or ""
                        track = jsond.get("Track") or ""
                        date = jsond.get("Date") or ""
                        comment = jsond.get("Comment") or ""
                        filename = os.path.basename(p)
                        
                        file_data.append((i, title, artist, coverartist, version, disc, track, date, comment, filename))
                        completed += 1
                        
                        # Update progress
                        if self.progress_dialog:
                            self.progress_dialog.update_progress(completed, total, f"Loading metadata... {completed}/{total}")
                            
                    except Exception as e:
                        print(f"Error loading {p}: {e}")
                        completed += 1
            return file_data
        
        def on_data_loaded(file_data):
            if self.progress_dialog and self.progress_dialog.cancelled:
                self.lbl_file_info.configure(text="Loading cancelled")
                if self.progress_dialog:
                    self.progress_dialog.destroy()
                    self.progress_dialog = None
                return
            
            # Sort data
            sort_by = self.sort_var.get()
            sort_order = self.sort_order_var.get()
            
            if sort_by in ["title", "artist", "coverartist", "comment", "file"]:
                file_data.sort(key=lambda x: x[["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"].index(sort_by) + 1].lower(), 
                              reverse=(sort_order == "desc"))
            elif sort_by in ["version", "disc", "track", "date"]:
                file_data.sort(key=lambda x: x[["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"].index(sort_by) + 1], 
                              reverse=(sort_order == "desc"))
            
            # Populate tree and track visible indices
            self.visible_file_indices = []
            for orig_idx, title, artist, coverartist, version, disc, track, date, comment, filename in file_data:
                self.tree.insert("", "end", iid=str(orig_idx), 
                               values=(title, artist, coverartist, version, disc, track, date, comment, filename))
                self.visible_file_indices.append(orig_idx)

            # select first
            children = self.tree.get_children()
            if children:
                self.tree.selection_set(children[0])
                self.on_tree_select()
            
            self.lbl_file_info.configure(text=f"Files: {len(self.mp3_files)}")
            
            # Close progress dialog
            if self.progress_dialog:
                self.progress_dialog.destroy()
                self.progress_dialog = None
        
        # Start background loading
        threading.Thread(target=lambda: self.after(0, lambda: on_data_loaded(load_file_data())), daemon=True).start()

    def on_tree_select(self, event=None):
        sel = self.tree.selection()
        # Update selection count
        self.lbl_selection_info.configure(text=f"{len(sel)} song(s) selected")
        
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except:
            return
        if idx < 0 or idx >= len(self.mp3_files):
            return
        self.current_index = idx
        self.load_current()

    def load_current(self):
        if self.current_index is None or not self.mp3_files:
            return
        path = self.mp3_files[self.current_index]
        self.lbl_file_info.configure(text=f"{self.current_index+1}/{len(self.mp3_files)}  —  {os.path.basename(path)}")
        
        # Load JSON from cache
        self.current_json = self.get_file_data(path)
        
        # show JSON
        self.json_text.delete("1.0", "end")
        if self.current_json:
            try:
                self.json_text.insert("1.0", json.dumps(self.current_json, indent=2, ensure_ascii=False))
            except Exception:
                self.json_text.insert("1.0", str(self.current_json))
        else:
            self.json_text.insert("1.0", "No JSON found in comments")
        
        # Load cover in background
        def load_cover():
            img, _ = read_cover_from_mp3(path)
            return img
        
        def on_cover_loaded(img):
            self.current_cover_bytes = None
            if img:
                # Get display dimensions and resize proportionally
                display_width = 200
                display_height = 200
                
                # Calculate aspect ratio preserving dimensions
                img_ratio = img.width / img.height
                display_ratio = display_width / display_height
                
                if img_ratio > display_ratio:
                    # Image is wider than display area
                    new_width = display_width
                    new_height = int(display_width / img_ratio)
                else:
                    # Image is taller than display area
                    new_height = display_height
                    new_width = int(display_height * img_ratio)
                
                # Resize image
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img_resized)
                
                self.cover_display.configure(image=photo, text="")
                self.cover_display.image = photo
                
                # store bytes for potential writing (use original image)
                try:
                    b = BytesIO()
                    img.save(b, format="PNG")
                    self.current_cover_bytes = b.getvalue()
                except Exception:
                    self.current_cover_bytes = None
            else:
                self.cover_display.configure(image=None, text="No cover")
                self.cover_display.image = None
                self.current_cover_bytes = None

            # update output preview
            self.update_preview()
        
        # Start background cover loading
        threading.Thread(target=lambda: self.after(0, lambda: on_cover_loaded(load_cover())), daemon=True).start()

    def prev_file(self):
        """Navigate to previous file in the visible list"""
        if not self.visible_file_indices:
            return
            
        current_visible_index = None
        if self.current_index is not None:
            try:
                current_visible_index = self.visible_file_indices.index(self.current_index)
            except ValueError:
                current_visible_index = None
        
        if current_visible_index is None or current_visible_index <= 0:
            return
            
        # Get previous file index from visible list
        prev_index = self.visible_file_indices[current_visible_index - 1]
        self.tree.selection_set(str(prev_index))
        self.current_index = prev_index
        self.load_current()

    def next_file(self):
        """Navigate to next file in the visible list"""
        if not self.visible_file_indices:
            return
            
        current_visible_index = None
        if self.current_index is not None:
            try:
                current_visible_index = self.visible_file_indices.index(self.current_index)
            except ValueError:
                current_visible_index = None
        
        if current_visible_index is None or current_visible_index >= len(self.visible_file_indices) - 1:
            return
            
        # Get next file index from visible list
        next_index = self.visible_file_indices[current_visible_index + 1]
        self.tree.selection_set(str(next_index))
        self.current_index = next_index
        self.load_current()

    def refresh_tree(self):
        q = self.search_var.get().strip().lower()
        if not q:
            # If no search query, repopulate with all files
            self.populate_tree()
            return
            
        # Filter existing data instead of reloading
        for it in self.tree.get_children():
            self.tree.delete(it)
            
        # Use cached data for filtering and track visible indices
        self.visible_file_indices = []
        file_data = []
        for i, p in enumerate(self.mp3_files):
            jsond = self.get_file_data(p)
            title = jsond.get("Title") or os.path.splitext(os.path.basename(p))[0]
            artist = jsond.get("Artist") or ""
            coverartist = jsond.get("CoverArtist") or ""
            version = jsond.get("Version") or ""
            disc = jsond.get("Discnumber") or ""
            track = jsond.get("Track") or ""
            date = jsond.get("Date") or ""
            comment = jsond.get("Comment") or ""
            filename = os.path.basename(p)
            
            row_text = " ".join([title, artist, coverartist, version, disc, track, date, comment, filename]).lower()
            if q not in row_text:
                continue
            file_data.append((i, title, artist, coverartist, version, disc, track, date, comment, filename))
            self.visible_file_indices.append(i)
        
        # Sort filtered data
        sort_by = self.sort_var.get()
        sort_order = self.sort_order_var.get()
        
        if sort_by in ["title", "artist", "coverartist", "comment", "file"]:
            file_data.sort(key=lambda x: x[["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"].index(sort_by) + 1].lower(), 
                          reverse=(sort_order == "desc"))
        elif sort_by in ["version", "disc", "track", "date"]:
            file_data.sort(key=lambda x: x[["title", "artist", "coverartist", "version", "disc", "track", "date", "comment", "file"].index(sort_by) + 1], 
                          reverse=(sort_order == "desc"))
        
        # Populate tree with filtered and sorted data
        for orig_idx, title, artist, coverartist, version, disc, track, date, comment, filename in file_data:
            self.tree.insert("", "end", iid=str(orig_idx), 
                           values=(title, artist, coverartist, version, disc, track, date, comment, filename))

    def on_select_all(self):
        sel = self.select_all_var.get()
        if sel:
            # select all visible
            self.tree.selection_set(self.tree.get_children())
        else:
            self.tree.selection_remove(self.tree.get_children())
        # Update selection count
        self.lbl_selection_info.configure(text=f"{len(self.tree.selection())} song(s) selected")

    # -------------------------
    # Rule evaluation & preview
    # -------------------------
    def update_preview(self):
        if not self.current_json:
            self.lbl_out_title.configure(text="")
            self.lbl_out_artist.configure(text="")
            self.lbl_out_album.configure(text="")
            self.lbl_out_disc.configure(text="")
            self.lbl_out_track.configure(text="")
            self.lbl_out_versions.configure(text="")
            return

        fv = {
            "Date": self.current_json.get("Date", ""),
            "Title": self.current_json.get("Title", ""),
            "Artist": self.current_json.get("Artist", ""),
            "CoverArtist": self.current_json.get("CoverArtist", ""),
            "Version": self.current_json.get("Version", "0"),
            "Discnumber": self.current_json.get("Discnumber", ""),
            "Track": self.current_json.get("Track", ""),
            "Comment": self.current_json.get("Comment", "")
        }

        new_title = self._apply_rules_list(self.collect_rules_for("title"), fv)
        new_artist = self._apply_rules_list(self.collect_rules_for("artist"), fv)
        new_album = self._apply_rules_list(self.collect_rules_for("album"), fv)

        self.lbl_out_title.configure(text=new_title)
        self.lbl_out_artist.configure(text=new_artist)
        self.lbl_out_album.configure(text=new_album)
        self.lbl_out_disc.configure(text=fv.get("Discnumber", ""))
        self.lbl_out_track.configure(text=fv.get("Track", ""))
        
        # Show all versions for current song (considering title + artist + coverartist)
        current_title = fv.get("Title", "")
        current_artist = fv.get("Artist", "")
        current_coverartist = fv.get("CoverArtist", "")
        
        # Create a unique key that considers all three fields
        song_key = f"{current_title}|{current_artist}|{current_coverartist}"
        
        if song_key and song_key in self.song_versions:
            versions = self.song_versions[song_key]
            versions_text = ", ".join(sorted(set(versions)))  # Remove duplicates and sort
            self.lbl_out_versions.configure(text=versions_text)
        else:
            self.lbl_out_versions.configure(text="")

    def collect_rules_for(self, key):
        return self.collect_rules_for_tab(key)

    def collect_rules_for_tab(self, key):
        """key in 'title','artist','album'"""
        container = self.rule_containers.get(key)
        if not container:
            return []
        rules = []
        for w in container.winfo_children():
            if isinstance(w, RuleRow):
                rules.append(w.get_rule())
        return rules

    def _apply_rules_list(self, rules, fv):
        # rules is list in order; return first matching THEN template applied; if none, default original value
        for r in rules:
            if self._eval_rule(r, fv):
                return self._apply_template(r.get("then_template", ""), fv)
        # default: return original field if exists
        # guess which field tab asked by checking caller - not passed here, so try best: template keys may include one
        # fallback: return Title/Artist/Album by priority - caller uses correct collection
        # We'll return blank if nothing
        # Simple heuristic: if rules belong to title tab, try Title; else similar
        # We'll check caller by checking if any rule list contains 'Title' field as if_field frequently
        # But safe fallback: return fv.get('Title'/'Artist'/'Album')
        # Upstream passes correct rule list for target, so use that assumption: if rules target title but none matched -> original Title
        if rules and len(rules) > 0:
            # determine which output they intend by checking rule container keys - but simpler:
            sample = rules[0].get("then_template", "")
            # naive: if template contains {Title} -> return original Title
            if "{Title}" in sample:
                return fv.get("Title", "")
            if "{Artist}" in sample and "{Title}" not in sample:
                return fv.get("Artist", "")
        # final fallback: empty string
        return fv.get("Title", "") or fv.get("Artist", "") or fv.get("Album", "") or ""

    def _eval_rule(self, rule, fv):
        field = rule.get("if_field", "")
        op = rule.get("if_operator", "")
        val = rule.get("if_value", "")
        actual = str(fv.get(field, ""))

        if op == "is":
            return actual == val
        if op == "contains":
            return val in actual
        if op == "starts with":
            return actual.startswith(val)
        if op == "ends with":
            return actual.endswith(val)
        if op == "is empty":
            return actual == ""
        if op == "is not empty":
            return actual != ""
        if op == "is latest version":
            title = fv.get("Title", "")
            version = fv.get("Version", "0")
            return self.is_latest_version(title, version)
        if op == "is not latest version":
            title = fv.get("Title", "")
            version = fv.get("Version", "0")
            return not self.is_latest_version(title, version)
        return False

    def _apply_template(self, template, fv):
        # simple replacement of {Field}
        result = template
        for k, v in fv.items():
            result = result.replace("{" + k + "}", str(v))
        return result

    # -------------------------
    # Version scanning
    # -------------------------
    def scan_versions(self):
        if not self.mp3_files:
            messagebox.showwarning("No files", "Load a folder first")
            return
        
        self.btn_scan_versions.configure(state="disabled", text="Scanning...")
        
        def scan_in_background():
            song_versions = {}
            total = len(self.mp3_files)
            completed = 0
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.get_file_data, p): p for p in self.mp3_files}
                for future in as_completed(futures):
                    p = futures[future]
                    try:
                        j = future.result()
                        if not j:
                            continue
                        title = j.get("Title", "")
                        artist = j.get("Artist", "")
                        coverartist = j.get("CoverArtist", "")
                        version = j.get("Version", "0")
                        
                        # Create a unique key that considers title, artist, AND coverartist
                        song_key = f"{title}|{artist}|{coverartist}"
                        
                        if song_key not in song_versions:
                            song_versions[song_key] = []
                        song_versions[song_key].append(version)
                    except Exception as e:
                        print(f"Error scanning {p}: {e}")
                    finally:
                        completed += 1
                        # Update progress if we have a dialog
                        if hasattr(self, 'progress_dialog') and self.progress_dialog:
                            self.progress_dialog.update_progress(completed, total, f"Scanning versions... {completed}/{total}")
            
            # Compute latest versions
            latest_versions = {}
            for song_key, versions in song_versions.items():
                parsed = []
                for v in versions:
                    nums = re.findall(r"\d+", str(v))
                    if nums:
                        parsed.append([int(x) for x in nums])
                    else:
                        parsed.append([0])
                # find max by lexicographic comparison
                max_idx = 0
                for i, p in enumerate(parsed):
                    if p > parsed[max_idx]:
                        max_idx = i
                latest_versions[song_key] = versions[max_idx]
            
            return song_versions, latest_versions
        
        def on_scan_complete(result):
            self.song_versions, self.latest_versions = result
            self.btn_scan_versions.configure(state="normal", text="Scan Versions")
            messagebox.showinfo("Scan Complete", f"Scanned {len(self.song_versions)} unique songs.")
            # Refresh preview to show versions
            self.update_preview()
        
        # Start background scanning
        threading.Thread(target=lambda: self.after(0, lambda: on_scan_complete(scan_in_background())), daemon=True).start()

    def is_latest_version(self, title, version):
        if not self.latest_versions:
            return True
        
        # Find the song key for this title (we need to search since we don't have artist/coverartist here)
        for song_key, latest_version in self.latest_versions.items():
            if title in song_key:  # Simple matching - could be improved
                return latest_version == version
        return True

    # -------------------------
    # Apply metadata to files
    # -------------------------
    def apply_to_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select rows in the song list first")
            return
        paths = [self.mp3_files[int(iid)] for iid in sel]
        
        # Create progress dialog
        self.progress_dialog = ProgressDialog(self, "Applying Metadata")
        
        def apply_in_background():
            success_count = 0
            total = len(paths)
            
            for i, p in enumerate(paths):
                if self.progress_dialog and self.progress_dialog.cancelled:
                    break
                    
                try:
                    j = self.get_file_data(p)
                    if not j:
                        continue
                    fv = {
                        "Date": j.get("Date", ""),
                        "Title": j.get("Title", ""),
                        "Artist": j.get("Artist", ""),
                        "CoverArtist": j.get("CoverArtist", ""),
                        "Version": j.get("Version", "0"),
                        "Discnumber": j.get("Discnumber", ""),
                        "Track": j.get("Track", ""),
                        "Comment": j.get("Comment", "")
                    }
                    new_title = self._apply_rules_list(self.collect_rules_for_tab("title"), fv)
                    new_artist = self._apply_rules_list(self.collect_rules_for_tab("artist"), fv)
                    new_album = self._apply_rules_list(self.collect_rules_for_tab("album"), fv)

                    # write tags
                    cover_bytes = None
                    cover_mime = "image/jpeg"

                    if write_id3_tags(p,
                                   title=new_title,
                                   artist=new_artist,
                                   album=new_album,
                                   track=fv.get("Track", None),
                                   disc=fv.get("Discnumber", None),
                                   date=fv.get("Date", None),
                                   cover_bytes=cover_bytes,
                                   cover_mime=cover_mime):
                        success_count += 1
                        
                except Exception as e:
                    print(f"Error applying to {p}: {e}")
                
                # Update progress
                if self.progress_dialog:
                    self.progress_dialog.update_progress(i + 1, total, f"Applying to {i + 1}/{total} files...")
                    
            return success_count
        
        def on_apply_complete(success_count):
            if self.progress_dialog:
                self.progress_dialog.destroy()
                self.progress_dialog = None
                
            self.lbl_file_info.configure(text=f"Applied to {success_count}/{len(paths)} files")
            messagebox.showinfo("Done", f"Applied to {success_count} files")
        
        # Start background application
        threading.Thread(target=lambda: self.after(0, lambda: on_apply_complete(apply_in_background())), daemon=True).start()

    def apply_to_all(self):
        if not self.mp3_files:
            messagebox.showwarning("No files", "Load a folder first")
            return
        res = messagebox.askyesno("Confirm", f"Apply to all {len(self.mp3_files)} files?")
        if not res:
            return
        
        # Select all files for processing
        self.tree.selection_set(self.tree.get_children())
        self.apply_to_selected()

    # -------------------------
    # Preset save/load
    # -------------------------
    def save_preset(self):
        name = simpledialog.askstring("Preset name", "Preset name:")
        if not name:
            return
        preset = {
            "title": self.collect_rules_for_tab("title"),
            "artist": self.collect_rules_for_tab("artist"),
            "album": self.collect_rules_for_tab("album")
        }
        # load existing
        try:
            pf = "metadata_presets.json"
            data = {}
            if os.path.exists(pf):
                data = json.load(open(pf, "r", encoding="utf-8"))
            data[name] = preset
            json.dump(data, open(pf, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            # update combobox list
            self._reload_presets()
            messagebox.showinfo("Saved", f"Preset '{name}' saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save preset: {e}")

    def _reload_presets(self):
        pf = "metadata_presets.json"
        vals = []
        if os.path.exists(pf):
            try:
                data = json.load(open(pf, "r", encoding="utf-8"))
                vals = list(data.keys())
            except Exception:
                vals = []
        self.preset_combo['values'] = vals

    def delete_preset(self):
        name = self.preset_var.get()
        if not name:
            return
        pf = "metadata_presets.json"
        if os.path.exists(pf):
            data = json.load(open(pf, "r", encoding="utf-8"))
            if name in data:
                confirm = messagebox.askyesno("Delete", f"Delete preset '{name}'?")
                if confirm:
                    del data[name]
                    json.dump(data, open(pf, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
                    self._reload_presets()
                    messagebox.showinfo("Deleted", f"Preset '{name}' deleted")

    def on_preset_selected(self, event=None):
        name = self.preset_var.get()
        if not name:
            return
        pf = "metadata_presets.json"
        if not os.path.exists(pf):
            return
        data = json.load(open(pf, "r", encoding="utf-8"))
        preset = data.get(name)
        if not preset:
            return
        # clear existing rule containers and load from preset
        for key in ("title", "artist", "album"):
            cont = self.rule_containers.get(key)
            # destroy existing RuleRow children
            for w in cont.winfo_children():
                w.destroy()
            rules = preset.get(key, [])
            for r in rules:
                row = RuleRow(cont, self.rule_fields, self.rule_ops, move_callback=self.move_rule, delete_callback=self.delete_rule)
                row.pack(fill="x", padx=6, pady=6)
                row.field_var.set(r.get("if_field", self.rule_fields[0]))
                row.op_var.set(r.get("if_operator", self.rule_ops[0]))
                row.value_entry.insert(0, r.get("if_value", ""))
                row.template_entry.insert(0, r.get("then_template", ""))
        self.update_preview()

    # -------------------------
    # Main loop helpers
    # -------------------------
    def run(self):
        # load presets combobox
        self._reload_presets()
        self.mainloop()


# -------------------------------
# Run
# -------------------------------
def main():
    app = DFApp()
    app.run()


if __name__ == "__main__":
    main()