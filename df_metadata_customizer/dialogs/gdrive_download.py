"""GDrive Download Dialog."""

import contextlib
import json
import logging
import os
import re
import subprocess
import threading
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import customtkinter as ctk
from rclone_python import rclone

import df_metadata_customizer.patches.rclone as rclone_patch
from df_metadata_customizer.dialogs.app_dialog import AppDialog
from df_metadata_customizer.dialogs.progress import ProgressCancelledException, ProgressDialog

if TYPE_CHECKING:
    from df_metadata_customizer.database_reformatter import DFApp

logger = logging.getLogger(__name__)

DEFAULT_GDRIVE_ROOT_IDS = {
    "Unofficial Neuro Karaoke Archive": "1B1VaWp-mCKk15_7XpFnImsTdBJPOGx7a",
}


def _fmt_binary(s: float) -> str:
    """Convert a size in bytes to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024:
            return f"{s:.2f} {unit}"
        s /= 1024
    return f"{s:.2f} PB"

class GDriveDownloadDialog(AppDialog):
    """Dialog to download from GDrive using rclone."""

    def __init__(self, parent: "DFApp") -> None:
        """Initialize the GDrive download dialog."""
        super().__init__(parent, "GDrive Download", geometry="550x400")
        self.app = parent

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(4, weight=1)

        # 1. Rclone Status
        self.rclone_label = ctk.CTkLabel(self.main_frame, text="Rclone Status:", anchor="w")
        self.rclone_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.installed = rclone.is_installed()
        status_text = "✅ Installed" if self.installed else "❌ Not Installed"
        status_color = "green" if self.installed else "red"

        self.status_indicator = ctk.CTkLabel(
            self.main_frame,
            text=status_text,
            text_color=status_color,
            anchor="w",
        )
        self.status_indicator.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        # 2. Rclone Config Selection
        self.config_label = ctk.CTkLabel(self.main_frame, text="Rclone Config:", anchor="w")
        self.config_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")

        self.configs = ["Default (provided)"]
        if self.installed:
            try:
                remotes = rclone.get_remotes()
                if remotes:
                    self.configs.extend(remotes)
            except Exception:
                logger.exception("Failed to get rclone remotes")

        self.config_var = ctk.StringVar(value=self.configs[0])
        self.config_menu = ctk.CTkOptionMenu(
            self.main_frame,
            values=self.configs,
            variable=self.config_var,
            state="normal" if self.installed else "disabled",
        )
        self.config_menu.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # 3. GDrive Root ID Preset
        self.archive_label = ctk.CTkLabel(self.main_frame, text="Archive:", anchor="w")
        self.archive_label.grid(row=2, column=0, padx=10, pady=10, sticky="w")

        self.preset_menu = ctk.CTkOptionMenu(
            self.main_frame,
            values=list(DEFAULT_GDRIVE_ROOT_IDS.keys()),
            command=self._on_preset_select,
            state="normal" if self.installed else "disabled",
        )
        self.preset_menu.set("Select an archive...")
        self.preset_menu.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # 4. GDrive ID Entry (Url or ID)
        self.id_label = ctk.CTkLabel(self.main_frame, text="GDrive ID / URL:", anchor="w")
        self.id_label.grid(row=3, column=0, padx=10, pady=10, sticky="w")

        self.id_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Paste ID or URL here",
            state="normal" if self.installed else "disabled",
        )
        self.id_entry.grid(row=3, column=1, padx=10, pady=10, sticky="ew")

        # 5. Buttons
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.grid(row=4, column=0, columnspan=2, pady=20, sticky="sew")

        self.btn_download = ctk.CTkButton(
            self.btn_frame,
            text="Download to...",
            command=self._start_download,
            state="normal" if self.installed else "disabled",
        )
        self.btn_download.pack(side="left", padx=10, expand=True)

        self.btn_cancel = ctk.CTkButton(
            self.btn_frame,
            text="Cancel",
            command=self.destroy,
            fg_color="transparent",
            border_width=1,
        )
        self.btn_cancel.pack(side="right", padx=10, expand=True)

    def _on_preset_select(self, choice: str) -> None:
        """Handle preset selection."""
        if choice in DEFAULT_GDRIVE_ROOT_IDS:
            self.id_entry.delete(0, "end")
            self.id_entry.insert(0, DEFAULT_GDRIVE_ROOT_IDS[choice])

    def _extract_id(self, text: str) -> str | None:
        """Extract GDrive ID from text (URL or ID)."""
        text = text.strip()
        if not text:
            return None

        # Check if it looks like an ID directly
        if re.match(r"^[a-zA-Z0-9_-]{25,}$", text):
            return text

        # Parse URL
        try:
            parsed = urlparse(text)
            # https://drive.google.com/drive/folders/ID
            if "drive.google.com" in parsed.netloc:
                path_parts = parsed.path.split("/")
                if "folders" in path_parts:
                    idx = path_parts.index("folders")
                    if idx + 1 < len(path_parts):
                        return path_parts[idx + 1]

                # https://drive.google.com/open?id=ID
                query = parse_qs(parsed.query)
                if "id" in query:
                    return query["id"][0]
        except Exception:
            pass

        return None

    def _handle_default_config(self) -> tuple[str, list[str]] | None:
        """Handle default configuration authentication."""
        if not messagebox.askokcancel(
            "Authentication Required",
            "You are using the default configuration.\n"
            "A browser window will open to authenticate with Google Drive.\n\n"
            "Click OK to proceed.",
        ):
            return None

        try:
            # 1. Authorize and get token
            cmd = ["rclone", "authorize", "drive"]
            # startupinfo to hide console window on Windows
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # Run rclone authorize. It will open the browser.
            # We capture output to get the token.
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                startupinfo=startupinfo,
            )
            output = process.stdout

            # 2. Extract JSON token
            match = re.search(r"\{.*\}", output, re.DOTALL)
            if not match:
                msg = "Could not find token in authentication output."
                raise ValueError(msg)

            token_str = match.group(0)
            # Compact JSON to be safe for CLI args
            token_data = json.loads(token_str)
            compact_token = json.dumps(token_data, separators=(",", ":"))

            # 3. Configure usage without config file
            flag_config = "NUL" if os.name == "nt" else "/dev/null"
            remote = ":drive"

            # Use env var for token to avoid shell escaping issues with JSON on Windows
            extra_args = [f"--config={flag_config}"]
            env_vars = {"RCLONE_DRIVE_TOKEN": compact_token}

        except subprocess.CalledProcessError as e:
            logger.exception("Auth process failed")
            messagebox.showerror("Authentication Failed", f"Rclone error:\n{e.stderr}")
            return None
        except Exception as e:
            logger.exception("Auth failed")
            messagebox.showerror("Authentication Failed", str(e))
            return None

        return remote, extra_args, env_vars

    def _start_download(self) -> None:
        """Start the download process."""
        raw_id = self.id_entry.get()
        gdrive_id = self._extract_id(raw_id)

        if not gdrive_id:
            messagebox.showerror("Error", "Invalid GDrive ID or URL")
            return

        dest_dir = filedialog.askdirectory(title="Select Download Destination")
        if not dest_dir:
            return

        selected_config = self.config_var.get()
        remote = selected_config
        extra_args = []
        env_vars = {}

        if selected_config == "Default (provided)":
            result = self._handle_default_config()
            if not result:
                return
            remote, extra_args, env_vars = result

        self.withdraw()
        progress = ProgressDialog(self.app, title="Download Progress", geometry="800x200")

        def progress_listener(data: dict) -> None:
            if progress.cancelled:
                raise ProgressCancelledException

            total = data.get("total", 0)
            sent = data.get("sent", 0)

            name = ""
            tasks = data.get("tasks", [])
            if tasks:
                with contextlib.suppress(IndexError, KeyError):
                    name = tasks[0].get("name", "")

            msg = f"Downloading: {name}\n{_fmt_binary(sent)} / {_fmt_binary(total)}"

            # If total is 0 (unknown), fallback to progress (0.0-1.0)
            if total == 0:
                prog = data.get("progress", 0.0)
                progress.update_progress(prog * 100, 100, msg)
            else:
                progress.update_progress(sent, total, msg)

        def run_thread() -> None:
            try:
                # Set env vars temporarily
                original_env = {}
                for k, v in env_vars.items():
                    original_env[k] = os.environ.get(k)
                    os.environ[k] = v

                try:
                    rclone.copy(
                        f"{remote}{':' if not remote.endswith(':') else ''}",  # Must follow format "remote:"
                        dest_dir,
                        args=[f"--drive-root-folder-id={gdrive_id}", *extra_args],
                        listener=progress_listener,
                    )
                    self.app.after(0, lambda: messagebox.showinfo("Success", "Download complete!"))
                finally:
                    # Restore env vars
                    for k, v in original_env.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v

            except ProgressCancelledException:
                if rclone_patch.process:
                    with contextlib.suppress(Exception):
                        rclone_patch.process.kill()
                logger.info("Download cancelled by user")
                self.app.after(0, lambda: messagebox.showinfo("Cancelled", "Download cancelled by user."))
            except Exception as e:
                logger.exception("Download failed")
                exception = str(e)  # Cannot use e directly in lambda
                self.app.after(
                    0,
                    lambda: messagebox.showerror("Error", f"Download failed: {exception}"),
                )
            finally:
                self.app.after(0, progress.destroy)
                self.app.after(0, self.destroy)

        threading.Thread(target=run_thread, daemon=True).start()
