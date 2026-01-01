from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from df_metadata_customizer.database_reformatter import DFApp

class AppComponent(ctk.CTkFrame):
    """Base class for UI components that are part of the DFApp."""

    def __init__(self, parent: ctk.CTkBaseClass, app: "DFApp", **kwargs: dict) -> None:
        """Set up the AppComponent."""
        super().__init__(parent, **kwargs)
        self.app = app
        self.initialize_state()
        self.setup_ui()

    def initialize_state(self) -> None:
        """Override this method to initialize component state before UI setup."""

    def setup_ui(self) -> None:
        """Override this method to build the UI for the component."""
