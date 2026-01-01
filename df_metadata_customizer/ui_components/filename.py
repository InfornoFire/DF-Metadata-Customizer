import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from df_metadata_customizer.ui_components.app_component import AppComponent


class FilenameComponent(AppComponent):
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(self, text="Filename:").grid(row=0, column=0, sticky="e", padx=(6, 6), pady=(6, 2))
        self.filename_var = tk.StringVar()
        self.filename_entry = ctk.CTkEntry(self, textvariable=self.filename_var)
        self.filename_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(6, 2))
        self.filename_entry.bind("<KeyRelease>", self.on_filename_changed)

        self.filename_save_btn = ctk.CTkButton(
            self,
            text="Rename File",
            width=100,
            command=self.app.rename_current_file,
            state="disabled",
        )
        self.filename_save_btn.grid(row=0, column=2, padx=(0, 6), pady=(6, 2))

    def on_filename_changed(self, _event: tk.Event | None = None) -> None:
        """Enable/disable rename button based on filename changes."""
        if self.app.current_index is None:
            self.filename_save_btn.configure(state="disabled")
            return

        current_path = self.app.mp3_files[self.app.current_index]
        current_filename = Path(current_path).name
        new_filename = self.filename_var.get().strip()

        # Enable button only if filename has changed and is not empty
        if new_filename and new_filename != current_filename:
            self.filename_save_btn.configure(state="normal")
        else:
            self.filename_save_btn.configure(state="disabled")
