import customtkinter as ctk

from df_metadata_customizer.dialogs import StatisticsDialog
from df_metadata_customizer.ui_components.app_component import AppComponent


class StatisticsComponent(AppComponent):
    def setup_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        self.statistics_btn = ctk.CTkButton(
            self,
            text="📊 Show Statistics 📊",
            command=self.show_statistics_popup,
            fg_color="#444",
            hover_color="#555",
            height=28,
        )
        self.statistics_btn.grid(row=0, column=0, sticky="w")

        self.status_label = ctk.CTkLabel(self, text="All songs: 0 | Unique (T,A): 0", anchor="w")
        self.status_label.grid(row=0, column=1, sticky="e")

        self.stats = {
            "all_songs": 0,
            "unique_ta": 0,
            "unique_tac": 0,
            "neuro_solos_unique": 0,
            "neuro_solos_total": 0,
            "evil_solos_unique": 0,
            "evil_solos_total": 0,
            "duets_unique": 0,
            "duets_total": 0,
            "other_unique": 0,
            "other_total": 0,
        }

    def calculate_statistics(self) -> None:
        """Calculate comprehensive statistics about the loaded songs."""
        if not self.app.mp3_files:
            self.stats = dict.fromkeys(self.stats, 0)
            self._update_status_display()
            print("No files loaded, stats reset to 0")
            return

        # Delegate calculation to FileManager
        self.stats = self.app.file_manager.calculate_statistics()

        print("Statistics calculated:")
        for key, value in self.stats.items():
            print(f"  {key}: {value}")

        # Update the status display
        self._update_status_display()

    def _update_status_display(self) -> None:
        """Update the main status display."""
        self.status_label.configure(
            text=f"All songs: {self.stats.get('all_songs', 0)} | Unique (T,A): {self.stats.get('unique_ta', 0)}",
        )

    def show_statistics_popup(self) -> None:
        """Show statistics in a popup window."""
        if hasattr(self, "_status_popup") and self._status_popup.winfo_exists():
            self._status_popup.focus_set()
            return

        self._status_popup = StatisticsDialog(self.app, self.stats)
