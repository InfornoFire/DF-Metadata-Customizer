"""Tree View Component."""

from tkinter import ttk
from typing import override

from df_metadata_customizer.components.app_component import AppComponent
from df_metadata_customizer.song_metadata import MetadataFields


class TreeComponent(AppComponent):
    """Tree view component for song list."""

    @override
    def initialize_state(self) -> None:
        self.dragged_column = None
        self.highlighted_column = None

    @override
    def setup_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Extended columns to show all JSON elements
        self.tree = ttk.Treeview(
            self,
            columns=self.app.COLUMN_ORDER,
            show="headings",
            selectmode="extended",
        )

        # Configure treeview style - will be updated by theme
        self.style = ttk.Style()
        self.update_theme()

        # Configure columns
        column_configs = {
            MetadataFields.UI_TITLE: ("Title", 280, "w"),
            MetadataFields.UI_ARTIST: ("Artist", 275, "w"),
            MetadataFields.UI_COVER_ARTIST: ("Cover Artist", 95, "w"),
            MetadataFields.UI_VERSION: ("Version", 65, "center"),
            MetadataFields.UI_DISC: ("Disc", 35, "center"),
            MetadataFields.UI_TRACK: ("Track", 55, "center"),
            MetadataFields.UI_DATE: ("Date", 85, "center"),
            MetadataFields.UI_COMMENT: ("Comment", 80, "w"),
            MetadataFields.UI_SPECIAL: ("Special", 60, "center"),
            MetadataFields.UI_FILE: ("File", 120, "w"),
        }

        for col in self.app.COLUMN_ORDER:
            heading, width, anchor = column_configs[col]
            self.tree.heading(col, text=heading)
            # Disable automatic stretching so horizontal scrollbar appears
            self.tree.column(col, width=width, anchor=anchor, stretch=False)

        # Enable column reordering
        self.tree.bind("<Button-1>", self.app.on_tree_click)

        self.tree.bind("<<TreeviewSelect>>", self.app.on_tree_select)
        # Double-click to play song
        self.tree.bind("<Double-1>", self.app.on_tree_double_click)

        # Vertical scrollbar
        self.tree_scroll_v = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.tree_scroll_v.set)

        # Horizontal scrollbar
        self.tree_scroll_h = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=self.tree_scroll_h.set)

        # Grid the tree and scrollbars
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_v.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_h.grid(row=1, column=0, sticky="ew")

    @override
    def update_theme(self) -> None:
        try:
            dark = self.app.is_dark_mode
            self.style.theme_use("default")
            self.style.configure(
                "Treeview",
                background="#2b2b2b" if dark else "white",
                foreground="white" if dark else "black",
                fieldbackground="#2b2b2b" if dark else "white",
                borderwidth=0,
            )
            self.style.configure(
                "Treeview.Heading",
                background="#3b3b3b" if dark else "#f0f0f0",
                foreground="white" if dark else "black",
                relief="flat",
            )
            self.style.map(
                "Treeview",
                background=[("selected", "#1f6aa5" if dark else "#0078d7")],
            )
            self.style.map(
                "Treeview.Heading",
                background=[("active", "#4b4b4b" if dark else "#e0e0e0")],
            )
        except Exception as e:
            print(f"Error updating treeview style: {e}")

    @override
    def register_events(self) -> None:
        self.app.bind("<<TreeComponent:RefreshTree>>", self.app.refresh_tree)
