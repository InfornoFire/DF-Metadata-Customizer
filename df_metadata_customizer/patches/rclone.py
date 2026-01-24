"""Patches for rclone-python==0.1.23."""

from collections.abc import Callable
import subprocess
from typing import Dict, List, Optional, Tuple
from rclone_python import utils, logs

process: subprocess.Popen | None = None

# Patch for rclone_python.utils.rclone_progress
# Grabs rclone process to allow termination from outside
def rclone_progress(
    command: str,
    pbar_title: str,
    show_progress=True,
    listener: Callable[[Dict], None] = None,
    pbar: Optional[utils.Progress] = None,
) -> Tuple[subprocess.Popen, List[str]]:
    global process  # Patch: Store process globally

    total_progress_id = None
    subprocesses = {}
    errors = []

    # Set the config path if defined by the user,
    # otherwise the default rclone config path is used:
    config = utils.Config()
    if config.config_path is not None:
        command += f' --config="{config.config_path}"'

    if show_progress:
        if pbar is None:
            pbar = utils.create_progress_bar()
        pbar.start()
        total_progress_id = pbar.add_task(pbar_title, total=None)

    process = subprocess.Popen(
        args=command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False  # Patch: Disable shell=True
    )

    # rclone prints stats to stderr. each line is one update
    for line in iter(process.stderr.readline, b""):
        line = line.decode()

        valid, update_dict = utils.extract_rclone_progress(line)

        if valid:
            if show_progress:
                utils.update_tasks(pbar, total_progress_id, update_dict, subprocesses)

            # call the listener
            if listener:
                listener(update_dict)

            logs.logger.debug(line)

        else:
            if update_dict is not None:
                obj = update_dict.get("object", "")
                msg = update_dict.get("msg", "<Error message missing>")
                errors.append((obj + ": " if obj else "") + msg)
                logs.logger.warning(f"Rclone omitted an error: {update_dict}")

    if show_progress:
        if process.wait() == 0:
            utils.complete_task(total_progress_id, pbar)
            for _, task_id in subprocesses.items():
                # hide all subprocesses
                pbar.update(task_id=task_id, visible=False)
        pbar.stop()

    return process, errors

utils.rclone_progress = rclone_progress
