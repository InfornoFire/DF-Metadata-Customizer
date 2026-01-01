import tkinter as tk

import customtkinter as ctk

from df_metadata_customizer.ui_components.app_component import AppComponent


class SongControlsComponent(AppComponent):
    def initialize_state(self) -> None:
        self.search_var = tk.StringVar()
        self.select_all_var = tk.BooleanVar(value=False)

    def setup_ui(self) -> None:
        self.configure(fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)  # Give more weight to search

        self.btn_select_folder = ctk.CTkButton(
            self,
            text="Select Folder",
            command=self.app.select_folder,
        )
        self.btn_select_folder.grid(row=0, column=0, padx=(0, 8))

        self.entry_search = ctk.CTkEntry(
            self,
            placeholder_text="Search title / artist / coverartist / disc / track / special / version=latest",
            textvariable=self.search_var,
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", self.app.on_search_keyrelease)

        self.chk_select_all = ctk.CTkCheckBox(
            self,
            text="Select All",
            variable=self.select_all_var,
            command=self.app.on_select_all,
        )
        self.chk_select_all.grid(row=0, column=2, padx=(0, 0))
