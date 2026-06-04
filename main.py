import os
import sys
import shutil
import subprocess
import tempfile
import threading
import time
import ctypes
import importlib
import json
import re
import urllib.error
import urllib.request
from ctypes import wintypes as wt
from pathlib import Path
import tkinter as tk
from tkinter import messagebox as mb, ttk

APP_TITLE = "PC Optimizer Panel"
GITHUB_REPO = "Glorp01/PC-Optimizer"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
WINDOWS_INSTALLER_ASSET = "PCOptimizer-Windows-Setup.exe"
APP_EXECUTABLE_NAME = "PCOptimizer.exe"
DEFAULT_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Programs" / "PC Optimizer"
BG = "#0b0b0b"
FG = "#d0d0d0"
ACCENT = "#16db65"  # terminal-ish green
FONT = ("Consolas", 10)
HEADER_FONT = ("Consolas", 12, "bold")
IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

APP_VERSION = "0.0.0-dev"
try:
    APP_VERSION = getattr(importlib.import_module("_build_info"), "APP_VERSION", APP_VERSION)
except Exception:
    pass


def run_hidden(args, **kwargs):
    """Run console tools from the GUI without flashing a terminal window."""
    if IS_WINDOWS and CREATE_NO_WINDOW:
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.run(args, **kwargs)


def popen_hidden(args, **kwargs):
    """Launch a helper process without flashing a console window."""
    if IS_WINDOWS and CREATE_NO_WINDOW:
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.Popen(args, **kwargs)


def github_request_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PC-Optimizer-Updater",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def version_parts(version: str):
    match = re.search(r"(\d+(?:\.\d+)*)", version or "")
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(latest: str, current: str) -> bool:
    latest_parts = version_parts(latest)
    current_parts = version_parts(current)
    max_len = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (max_len - len(latest_parts))
    current_parts += (0,) * (max_len - len(current_parts))
    return latest_parts > current_parts


def release_asset(release, asset_name: str):
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            return asset
    return None


def powershell_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def current_install_dir() -> Path:
    if IS_WINDOWS and getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent
        except OSError:
            pass
    return DEFAULT_INSTALL_DIR


def humanize(n_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n_bytes)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024


def format_timestamp(timestamp: float) -> str:
    if not timestamp:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
    except Exception:
        return ""


def list_storage_roots():
    roots = []
    if IS_WINDOWS:
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for idx, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                if bitmask & (1 << idx):
                    root = Path(f"{letter}:\\")
                    try:
                        if root.exists():
                            roots.append(root)
                    except OSError:
                        pass
        except Exception:
            roots.append(Path("C:\\"))
    elif sys.platform == "darwin":
        roots.append(Path("/"))
        volumes = Path("/Volumes")
        try:
            for volume in volumes.iterdir():
                if volume.is_dir():
                    roots.append(volume)
        except OSError:
            pass
    else:
        roots.append(Path("/"))
    return roots


def open_path(path: Path, select: bool = False) -> None:
    if IS_WINDOWS:
        if select:
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        else:
            subprocess.run(["explorer", str(path)], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False
    except OSError:
        return False


def protected_delete_reason(path: Path) -> str:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path

    if resolved.parent == resolved:
        return "Drive roots cannot be deleted from Storage Manager."

    if IS_WINDOWS:
        for root in list_storage_roots():
            if str(resolved).casefold() == str(root.resolve(strict=False)).casefold():
                return "Drive roots cannot be deleted from Storage Manager."

        protected_envs = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)")
        for env_name in protected_envs:
            base = os.environ.get(env_name)
            if not base:
                continue
            protected = Path(base)
            if is_relative_to(resolved, protected):
                return f"{protected} is protected. Open it and use the built-in cleanup actions instead."

    return ""


def move_to_recycle_bin(path: Path) -> None:
    if not IS_WINDOWS:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wt.HWND),
            ("wFunc", wt.UINT),
            ("pFrom", wt.LPCWSTR),
            ("pTo", wt.LPCWSTR),
            ("fFlags", wt.WORD),
            ("fAnyOperationsAborted", wt.BOOL),
            ("hNameMappings", wt.LPVOID),
            ("lpszProgressTitle", wt.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_NOERRORUI = 0x0400

    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = FO_DELETE
    operation.pFrom = str(path) + "\0\0"
    operation.pTo = None
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"Recycle Bin operation failed with code {result}")
    if operation.fAnyOperationsAborted:
        raise OSError("Recycle Bin operation was cancelled")


class StorageManager:
    def __init__(self, app: "PCOptimizerApp") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("Storage Manager")
        self.window.configure(bg=BG)
        self.window.geometry("920x560")
        self.window.minsize(820, 460)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        try:
            self.window.attributes("-alpha", 1.0)
            self.window.attributes("-topmost", True)
        except Exception:
            pass

        self.storage_roots = []
        self.current_path = None
        self.current_rows = []
        self.row_by_iid = {}
        self.scan_token = 0
        self.busy = False
        self.busy_action = ""
        self.sort_key = "size"
        self.sort_reverse = True

        self.drive_var = tk.StringVar()
        self.path_var = tk.StringVar(value="No folder selected")
        self.summary_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Select a storage device, then scan.")

        self._configure_styles()
        self._build_ui()
        self.populate_storage_roots()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        try:
            style.configure(
                "Storage.Treeview",
                background="#0f0f0f",
                fieldbackground="#0f0f0f",
                foreground=FG,
                bordercolor="#222",
                rowheight=24,
                font=FONT,
            )
            style.configure(
                "Storage.Treeview.Heading",
                background="#111",
                foreground=FG,
                relief=tk.FLAT,
                font=FONT,
            )
            style.map(
                "Storage.Treeview",
                background=[("selected", "#145a32")],
                foreground=[("selected", "#ffffff")],
            )
        except Exception:
            pass

    def _build_ui(self) -> None:
        wrap = tk.Frame(self.window, bg=BG, highlightthickness=1, highlightbackground="#222")
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        header = tk.Label(
            wrap,
            text="> Storage Manager",
            bg=BG,
            fg=ACCENT,
            font=HEADER_FONT,
        )
        header.pack(anchor="w")

        controls = tk.Frame(wrap, bg=BG)
        controls.pack(fill=tk.X, pady=(8, 6))

        tk.Label(controls, text="Storage", bg=BG, fg=FG, font=FONT).pack(side=tk.LEFT)
        self.drive_combo = ttk.Combobox(
            controls,
            textvariable=self.drive_var,
            state="readonly",
            width=46,
            font=FONT,
        )
        self.drive_combo.pack(side=tk.LEFT, padx=(8, 8))

        self.btn_scan = tk.Button(
            controls,
            text="Scan",
            command=self.scan_selected_storage,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_scan.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(
            controls,
            text="Stop",
            command=self.cancel_scan,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_refresh_drives = tk.Button(
            controls,
            text="Refresh Drives",
            command=self.populate_storage_roots,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_refresh_drives.pack(side=tk.LEFT, padx=(8, 0))

        path_row = tk.Frame(wrap, bg=BG)
        path_row.pack(fill=tk.X, pady=(0, 6))

        self.btn_up = tk.Button(
            path_row,
            text="Up",
            command=self.scan_parent,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_up.pack(side=tk.LEFT)

        self.btn_rescan = tk.Button(
            path_row,
            text="Rescan",
            command=self.rescan_current,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_rescan.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_open = tk.Button(
            path_row,
            text="Open Selected",
            command=self.open_selected,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_open.pack(side=tk.LEFT, padx=(8, 0))

        delete_text = "Move to Recycle Bin" if IS_WINDOWS else "Delete Selected"
        self.btn_delete = tk.Button(
            path_row,
            text=delete_text,
            command=self.delete_selected,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
        )
        self.btn_delete.pack(side=tk.LEFT, padx=(8, 0))

        current_label = tk.Label(
            path_row,
            textvariable=self.path_var,
            bg=BG,
            fg="#a0a0a0",
            font=FONT,
            anchor="w",
        )
        current_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0))

        tree_frame = tk.Frame(wrap, bg=BG)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("size", "percent", "type", "modified", "path")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            style="Storage.Treeview",
        )
        self.tree.heading("#0", text="Name", command=lambda: self.sort_rows("name"))
        self.tree.heading("size", text="Size", command=lambda: self.sort_rows("size"))
        self.tree.heading("percent", text="Share", command=lambda: self.sort_rows("percent"))
        self.tree.heading("type", text="Type", command=lambda: self.sort_rows("type"))
        self.tree.heading("modified", text="Modified", command=lambda: self.sort_rows("modified"))
        self.tree.heading("path", text="Path", command=lambda: self.sort_rows("path"))

        self.tree.column("#0", width=250, minwidth=160, stretch=True)
        self.tree.column("size", width=110, minwidth=90, anchor=tk.E)
        self.tree.column("percent", width=80, minwidth=70, anchor=tk.E)
        self.tree.column("type", width=90, minwidth=70)
        self.tree.column("modified", width=140, minwidth=120)
        self.tree.column("path", width=280, minwidth=160, stretch=True)
        self.tree.tag_configure("folder", foreground=ACCENT)
        self.tree.tag_configure("file", foreground=FG)
        self.tree.bind("<Double-1>", self.on_double_click)

        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.scan_progress = ttk.Progressbar(
            wrap,
            mode="indeterminate",
            style="Dark.Horizontal.TProgressbar",
            maximum=100,
        )
        self.scan_progress.pack(fill=tk.X, pady=(6, 0))

        summary = tk.Label(
            wrap,
            textvariable=self.summary_var,
            bg=BG,
            fg="#a0a0a0",
            font=FONT,
            anchor="w",
        )
        summary.pack(fill=tk.X, pady=(6, 0))

        status = tk.Label(
            wrap,
            textvariable=self.status_var,
            bg=BG,
            fg="#808080",
            font=("Consolas", 9),
            anchor="w",
        )
        status.pack(fill=tk.X, pady=(3, 0))

    def populate_storage_roots(self) -> None:
        if self.busy:
            return

        self.storage_roots = []
        labels = []
        for root in list_storage_roots():
            try:
                usage = shutil.disk_usage(root)
                label = f"{root}  {humanize(usage.free)} free / {humanize(usage.total)} total"
            except OSError:
                usage = None
                label = f"{root}  unavailable"
            self.storage_roots.append({"path": root, "usage": usage})
            labels.append(label)

        self.drive_combo.configure(values=labels)
        if not labels:
            self.drive_var.set("")
            self.status_var.set("No storage devices were found.")
            return

        selected_index = 0
        if IS_WINDOWS:
            system_drive = (os.environ.get("SystemDrive") or "C:") + "\\"
            for idx, item in enumerate(self.storage_roots):
                if str(item["path"]).casefold() == system_drive.casefold():
                    selected_index = idx
                    break
        self.drive_combo.current(selected_index)
        self.status_var.set("Select Scan to list the largest items first.")

    def scan_selected_storage(self) -> None:
        index = self.drive_combo.current()
        if index < 0 or index >= len(self.storage_roots):
            self.status_var.set("Select a storage device first.")
            return
        self.scan_path(self.storage_roots[index]["path"])

    def scan_path(self, path: Path) -> None:
        if self.busy:
            return
        self.scan_token += 1
        token = self.scan_token
        self.current_path = Path(path)
        self.current_rows = []
        self.row_by_iid = {}
        self.path_var.set(str(self.current_path))
        self.summary_var.set("")
        self.status_var.set(f"Scanning {self.current_path}...")
        self.tree.delete(*self.tree.get_children())
        self.set_busy(True, "scan")

        worker = threading.Thread(target=self._scan_worker, args=(self.current_path, token), daemon=True)
        worker.start()

    def _scan_worker(self, path: Path, token: int) -> None:
        rows = []
        skipped = 0
        started = time.monotonic()
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if token != self.scan_token:
                        return
                    row, entry_skipped, cancelled = self._describe_entry(entry, token)
                    skipped += entry_skipped
                    if cancelled:
                        return
                    if row:
                        rows.append(row)
        except Exception as exc:
            self._post_ui(lambda exc=exc, token=token: self.scan_failed(exc, token))
            return

        elapsed = time.monotonic() - started
        self._post_ui(lambda: self.scan_finished(path, rows, skipped, elapsed, token))

    def _describe_entry(self, entry, token: int):
        skipped = 0
        try:
            entry_path = Path(entry.path)
            stat_info = entry.stat(follow_symlinks=False)
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError:
            return None, 1, False

        if is_dir:
            size, nested_skipped, cancelled = self._folder_size(entry_path, token)
            skipped += nested_skipped
            if cancelled:
                return None, skipped, True
            kind = "Folder"
        elif is_file:
            size = stat_info.st_size
            suffix = entry_path.suffix.upper().lstrip(".")
            kind = suffix or "File"
        else:
            size = stat_info.st_size
            kind = "Other"

        return (
            {
                "name": entry.name,
                "path": entry_path,
                "size": size,
                "kind": kind,
                "modified": stat_info.st_mtime,
                "is_dir": is_dir,
            },
            skipped,
            False,
        )

    def _folder_size(self, folder_path: Path, token: int):
        total = 0
        skipped = 0
        stack = [folder_path]
        last_status = time.monotonic()

        while stack:
            if token != self.scan_token:
                return total, skipped, True

            current = stack.pop()
            now = time.monotonic()
            if now - last_status > 0.45:
                self._post_status(f"Scanning {current}...", token)
                last_status = now

            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if token != self.scan_token:
                            return total, skipped, True
                        try:
                            if entry.is_symlink():
                                total += entry.stat(follow_symlinks=False).st_size
                            elif entry.is_file(follow_symlinks=False):
                                total += entry.stat(follow_symlinks=False).st_size
                            elif entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                            else:
                                total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            skipped += 1
            except OSError:
                skipped += 1

        return total, skipped, False

    def scan_finished(self, path: Path, rows, skipped: int, elapsed: float, token: int) -> None:
        if token != self.scan_token:
            return

        self.current_path = path
        self.current_rows = rows
        self.sort_key = "size"
        self.sort_reverse = True
        self.render_rows()
        self.set_busy(False)

        listed_total = sum(row["size"] for row in rows)
        try:
            usage = shutil.disk_usage(path)
            used = usage.total - usage.free
            disk_text = f"Disk: {humanize(used)} used / {humanize(usage.total)} total | Free: {humanize(usage.free)}"
        except OSError:
            disk_text = "Disk usage unavailable"

        self.summary_var.set(
            f"{disk_text} | Listed: {humanize(listed_total)} | Items: {len(rows)} | Skipped: {skipped}"
        )
        self.status_var.set(f"Sorted largest first. Double-click a folder to drill in. Scan time: {elapsed:.1f}s")

    def scan_failed(self, exc: Exception, token=None) -> None:
        if token is not None and token != self.scan_token:
            return
        self.set_busy(False)
        self.status_var.set(f"Scan failed: {exc}")
        try:
            mb.showerror("Storage Manager", f"Scan failed:\n{exc}", parent=self.window)
        except Exception:
            pass

    def render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.row_by_iid = {}

        rows = sorted(self.current_rows, key=self.sort_value, reverse=self.sort_reverse)
        total = sum(row["size"] for row in rows)

        for idx, row in enumerate(rows):
            iid = f"row-{idx}"
            self.row_by_iid[iid] = row
            share = "0.0%" if total <= 0 else f"{(row['size'] / total) * 100:.1f}%"
            tag = "folder" if row["is_dir"] else "file"
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                text=row["name"],
                values=(
                    humanize(row["size"]),
                    share,
                    row["kind"],
                    format_timestamp(row["modified"]),
                    str(row["path"]),
                ),
                tags=(tag,),
            )

    def sort_value(self, row):
        if self.sort_key == "size":
            return row["size"]
        if self.sort_key == "percent":
            return row["size"]
        if self.sort_key == "type":
            return row["kind"].casefold()
        if self.sort_key == "modified":
            return row["modified"]
        if self.sort_key == "path":
            return str(row["path"]).casefold()
        return row["name"].casefold()

    def sort_rows(self, key: str) -> None:
        if key == self.sort_key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = key
            self.sort_reverse = key in ("size", "percent", "modified")
        self.render_rows()

    def selected_row(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.row_by_iid.get(selection[0])

    def on_double_click(self, _event) -> None:
        row = self.selected_row()
        if row and row["is_dir"]:
            self.scan_path(row["path"])

    def scan_parent(self) -> None:
        if self.busy or not self.current_path:
            return
        parent = self.current_path.parent
        if parent == self.current_path:
            return
        self.scan_path(parent)

    def rescan_current(self) -> None:
        if self.busy:
            return
        if self.current_path:
            self.scan_path(self.current_path)
        else:
            self.scan_selected_storage()

    def cancel_scan(self) -> None:
        if not self.busy or self.busy_action != "scan":
            return
        self.scan_token += 1
        self.set_busy(False)
        self.status_var.set("Scan stopped.")

    def open_selected(self) -> None:
        row = self.selected_row()
        path = row["path"] if row else self.current_path
        if not path:
            return
        try:
            open_path(path, select=bool(row and not row["is_dir"]))
        except Exception as exc:
            self.status_var.set(f"Could not open path: {exc}")

    def delete_selected(self) -> None:
        if self.busy:
            return

        row = self.selected_row()
        if not row:
            self.status_var.set("Select an item first.")
            return

        path = row["path"]
        reason = protected_delete_reason(path)
        if reason:
            mb.showwarning("Storage Manager", reason, parent=self.window)
            return

        if not path.exists():
            self.status_var.set("Selected item no longer exists.")
            return

        action = "move this item to the Recycle Bin" if IS_WINDOWS else "permanently delete this item"
        if not mb.askyesno(
            "Storage Manager",
            f"Do you want to {action}?\n\n{path}\n\nEstimated size: {humanize(row['size'])}",
            icon=mb.WARNING,
            parent=self.window,
        ):
            return

        self.set_busy(True, "delete")
        self.status_var.set(f"Deleting {path}...")
        worker = threading.Thread(target=self._delete_worker, args=(path,), daemon=True)
        worker.start()

    def _delete_worker(self, path: Path) -> None:
        try:
            move_to_recycle_bin(path)
        except Exception as exc:
            self._post_ui(lambda exc=exc: self.delete_failed(exc))
            return

        self._post_ui(lambda: self.delete_finished(path))

    def delete_finished(self, path: Path) -> None:
        self.set_busy(False)
        action = "Moved to Recycle Bin" if IS_WINDOWS else "Deleted"
        self.status_var.set(f"{action}: {path}")
        self.app.write(f"> {action}: {path}")
        if self.current_path and self.current_path.exists():
            self.scan_path(self.current_path)

    def delete_failed(self, exc: Exception) -> None:
        self.set_busy(False)
        self.status_var.set(f"Delete failed: {exc}")
        try:
            mb.showerror("Storage Manager", f"Delete failed:\n{exc}", parent=self.window)
        except Exception:
            pass

    def set_busy(self, busy: bool, action: str = "") -> None:
        self.busy = busy
        self.busy_action = action if busy else ""
        state = tk.DISABLED if busy else tk.NORMAL
        combo_state = tk.DISABLED if busy else "readonly"
        self.drive_combo.configure(state=combo_state)
        self.btn_scan.configure(state=state)
        self.btn_stop.configure(state=tk.NORMAL if busy and action == "scan" else tk.DISABLED)
        self.btn_refresh_drives.configure(state=state)
        self.btn_up.configure(state=state)
        self.btn_rescan.configure(state=state)
        self.btn_open.configure(state=state)
        self.btn_delete.configure(state=state)
        try:
            if busy:
                self.scan_progress.start(12)
            else:
                self.scan_progress.stop()
                self.scan_progress.configure(value=0)
        except Exception:
            pass

    def _post_status(self, message: str, token=None) -> None:
        def update_status() -> None:
            if token is not None and token != self.scan_token:
                return
            self.status_var.set(message)

        self._post_ui(update_status)

    def _post_ui(self, callback) -> None:
        try:
            self.window.after(0, callback)
        except tk.TclError:
            pass

    def close(self) -> None:
        self.scan_token += 1
        if getattr(self.app, "storage_manager", None) is self:
            self.app.storage_manager = None
        try:
            self.scan_progress.stop()
        except Exception:
            pass
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class PCOptimizerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.storage_manager = None
        self.update_state = "unknown"
        self.update_check_running = False
        self.latest_update_release = None
        self.latest_update_asset = None
        self.latest_update_tag = ""
        root.title(APP_TITLE)
        root.configure(bg=BG)
        try:
            # Keep the panel opaque so desktop/terminal windows do not bleed through.
            root.attributes('-alpha', 1.0)
            root.attributes('-topmost', True)
        except Exception:
            pass
        root.geometry("780x460")
        root.minsize(740, 410)

        # TTK style for progress bar on dark background
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        try:
            style.configure(
                "Dark.Horizontal.TProgressbar",
                troughcolor=BG,
                background=ACCENT,
                bordercolor=BG,
                lightcolor=ACCENT,
                darkcolor=ACCENT,
            )
        except Exception:
            pass

        # Wrapper frame for a subtle border
        self.wrap = tk.Frame(root, bg=BG, highlightthickness=1, highlightbackground="#222")
        self.wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Header
        self.header = tk.Label(
            self.wrap,
            text="> PC Optimizer",
            bg=BG,
            fg=ACCENT,
            font=HEADER_FONT,
        )
        self.header.pack(anchor="w")

        # Controls
        btn_frame = tk.Frame(self.wrap, bg=BG)
        btn_frame.pack(fill=tk.X, pady=(8, 8))

        self.btn_optimize = tk.Button(
            btn_frame,
            text="Optimize & Clean",
            command=self.start_optimize_clean,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_optimize.pack(side=tk.LEFT)

        self.btn_boost = tk.Button(
            btn_frame,
            text="Boost Performance",
            command=self.start_performance_boost,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_boost.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_open_temp = tk.Button(
            btn_frame,
            text="Open Temp Folder",
            command=self.open_temp_folder,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_open_temp.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_storage = tk.Button(
            btn_frame,
            text="Storage Manager",
            command=self.open_storage_manager,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_storage.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_update = tk.Button(
            btn_frame,
            text="Update App",
            command=self.start_update_check,
            bg="#151515",
            fg="#858585",
            activebackground="#1a1a1a",
            activeforeground="#a0a0a0",
            disabledforeground="#555",
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_update.pack(side=tk.LEFT, padx=(8, 0))

        # Second row for advanced actions
        adv_frame = tk.Frame(self.wrap, bg=BG)
        adv_frame.pack(fill=tk.X, pady=(0, 8))

        self.btn_aggressive = tk.Button(
            adv_frame,
            text="Aggressive Clean",
            command=self.start_aggressive_cleanup,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_aggressive.pack(side=tk.LEFT)

        self.btn_revert = tk.Button(
            adv_frame,
            text="Revert Boost",
            command=self.start_revert_boost,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_revert.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_clear_ram = tk.Button(
            adv_frame,
            text="Clear RAM Cache",
            command=self.start_clear_ram,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_clear_ram.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_component_cleanup = tk.Button(
            adv_frame,
            text="Component Cleanup",
            command=self.start_component_cleanup,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_component_cleanup.pack(side=tk.LEFT, padx=(8, 0))

        # Log area with terminal look
        self.log = tk.Text(
            self.wrap,
            bg="#0f0f0f",
            fg=FG,
            insertbackground=ACCENT,
            font=FONT,
            height=12,
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        # Progress bar for long operations
        self.progress = ttk.Progressbar(
            self.wrap,
            mode="indeterminate",
            style="Dark.Horizontal.TProgressbar",
            maximum=100,
        )
        self.progress.pack(fill=tk.X, pady=(4, 0))
        self.progress_running = False

        # Footer
        self.footer = tk.Label(
            self.wrap,
            text=f"Version: {APP_VERSION} | Tip: Tasks may take a moment; watch the log.",
            bg=BG,
            fg="#808080",
            font=("Consolas", 9),
        )
        self.footer.pack(anchor="w", pady=(6, 0))

        if not IS_WINDOWS:
            self.write("> This app is Windows-focused. Cleanup and boost actions are disabled on this OS.")
        else:
            self.root.after(1000, self.start_silent_update_check)

    # UI helpers
    def write(self, msg: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def start_progress(self) -> None:
        if not self.progress_running:
            self.progress_running = True
            try:
                self.progress.start(12)
            except Exception:
                pass

    def stop_progress(self) -> None:
        if self.progress_running:
            try:
                self.progress.stop()
                self.progress.configure(value=0)
            except Exception:
                pass
            self.progress_running = False

    def set_buttons_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_optimize.configure(state=state)
        self.btn_boost.configure(state=state)
        self.btn_open_temp.configure(state=state)
        self.btn_storage.configure(state=state)
        self.btn_update.configure(state=state)
        self.btn_aggressive.configure(state=state)
        self.btn_revert.configure(state=state)
        self.btn_clear_ram.configure(state=state)
        self.btn_component_cleanup.configure(state=state)

    def require_windows(self, action_name: str) -> bool:
        if IS_WINDOWS:
            return True
        msg = f"{action_name} is available on Windows only."
        self.write(f"[!] {msg}")
        try:
            mb.showwarning("Windows only", msg)
        except Exception:
            pass
        return False

    # Actions
    def start_optimize_clean(self) -> None:
        threading.Thread(target=self.optimize_clean, daemon=True).start()

    def start_performance_boost(self) -> None:
        threading.Thread(target=self.performance_boost, daemon=True).start()

    def start_revert_boost(self) -> None:
        threading.Thread(target=self.revert_boost, daemon=True).start()

    def start_aggressive_cleanup(self) -> None:
        threading.Thread(target=self.aggressive_cleanup, daemon=True).start()

    def start_clear_ram(self) -> None:
        threading.Thread(target=self.clear_ram_cache, daemon=True).start()

    def start_component_cleanup(self) -> None:
        threading.Thread(target=self.component_cleanup, daemon=True).start()

    def start_update_check(self) -> None:
        if not self.require_windows("Update App"):
            return

        if self.update_check_running:
            return

        if self.update_state == "available" and self.latest_update_release and self.latest_update_asset:
            self.prompt_update_install(self.latest_update_release, self.latest_update_asset, self.latest_update_tag)
            return

        threading.Thread(target=self.check_for_updates, args=(True,), daemon=True).start()

    def start_silent_update_check(self) -> None:
        if self.update_check_running:
            return
        threading.Thread(target=self.check_for_updates, args=(False,), daemon=True).start()

    def set_update_button_state(self, state: str, latest_tag: str = "") -> None:
        self.update_state = state
        label_latest = latest_tag or self.latest_update_tag
        if state == "checking":
            config = {
                "text": "Checking...",
                "bg": "#151515",
                "fg": "#858585",
                "activebackground": "#1a1a1a",
                "activeforeground": "#a0a0a0",
            }
        elif state == "current":
            config = {
                "text": "Up to Date",
                "bg": "#101010",
                "fg": "#5f5f5f",
                "activebackground": "#151515",
                "activeforeground": "#777",
            }
        elif state == "available":
            config = {
                "text": f"Update {label_latest}" if label_latest else "Update App",
                "bg": "#12361f",
                "fg": ACCENT,
                "activebackground": "#174c2c",
                "activeforeground": "#ffffff",
            }
        else:
            config = {
                "text": "Update App",
                "bg": "#111",
                "fg": FG,
                "activebackground": "#1a1a1a",
                "activeforeground": FG,
            }

        def apply_config() -> None:
            try:
                self.btn_update.configure(**config)
            except tk.TclError:
                pass

        try:
            self.root.after(0, apply_config)
        except tk.TclError:
            pass

    def check_for_updates(self, show_dialog: bool = True) -> None:
        self.update_check_running = True
        self.set_update_button_state("checking")
        if show_dialog:
            self.set_buttons_enabled(False)
            self.start_progress()
        try:
            if show_dialog:
                self.write(f"> Checking for updates... Current version: {APP_VERSION}")
            release = github_request_json(LATEST_RELEASE_API)
            latest_tag = release.get("tag_name") or ""
            asset = release_asset(release, WINDOWS_INSTALLER_ASSET)
            if not latest_tag or not asset:
                self.set_update_button_state("unknown")
                if show_dialog:
                    self.write("[!] Could not find a Windows installer on the latest GitHub release.")
                    self.show_message(
                        "Update App",
                        "The latest GitHub release does not include the Windows installer.",
                        "warning",
                    )
                return

            self.latest_update_release = release
            self.latest_update_asset = asset
            self.latest_update_tag = latest_tag

            if not is_newer_version(latest_tag, APP_VERSION):
                self.set_update_button_state("current", latest_tag)
                if show_dialog:
                    self.write(f"> You are already on the latest release: {latest_tag}")
                    self.show_message("Update App", f"PC Optimizer is up to date.\n\nInstalled: {APP_VERSION}\nLatest: {latest_tag}")
                return

            self.set_update_button_state("available", latest_tag)
            if show_dialog:
                self.root.after(0, lambda: self.prompt_update_install(release, asset, latest_tag))
            else:
                self.write(f"> Update available: {latest_tag}")
        except urllib.error.URLError as e:
            self.set_update_button_state("unknown")
            if show_dialog:
                self.write(f"[!] Update check failed: {e}")
                self.show_message("Update App", f"Could not reach GitHub:\n{e}", "error")
        except Exception as e:
            self.set_update_button_state("unknown")
            if show_dialog:
                self.write(f"[!] Update check failed: {e}")
                self.show_message("Update App", f"Update check failed:\n{e}", "error")
        finally:
            self.update_check_running = False
            if show_dialog:
                self.stop_progress()
                self.set_buttons_enabled(True)

    def prompt_update_install(self, release, asset, latest_tag: str) -> None:
        notes_url = release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")
        if not mb.askyesno(
            "Update App",
            (
                f"A new PC Optimizer update is available.\n\n"
                f"Installed: {APP_VERSION}\n"
                f"Latest: {latest_tag}\n\n"
                "Download and apply the update in the background now?\n"
                "PC Optimizer will close and relaunch when the update finishes."
            ),
        ):
            self.write(f"> Update skipped. Release page: {notes_url}")
            return

        self.set_buttons_enabled(False)
        self.start_progress()
        threading.Thread(target=self.download_and_launch_update, args=(asset, latest_tag), daemon=True).start()

    def download_and_launch_update(self, asset, latest_tag: str) -> None:
        try:
            download_url = asset.get("browser_download_url")
            if not download_url:
                raise RuntimeError("The release asset does not include a download URL.")

            update_dir = Path(tempfile.gettempdir()) / "PCOptimizerUpdate"
            update_dir.mkdir(parents=True, exist_ok=True)
            installer_path = update_dir / WINDOWS_INSTALLER_ASSET

            self.write(f"- Downloading {WINDOWS_INSTALLER_ASSET} from {latest_tag}...")
            self.download_update_installer(download_url, installer_path)

            update_script = self.write_update_script(update_dir, installer_path)
            self.write("> Applying update in the background. PC Optimizer will close and relaunch when finished.")
            popen_hidden(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(update_script),
                ],
                cwd=str(update_dir),
            )
            self.root.after(600, self.root.destroy)
        except Exception as e:
            self.write(f"[!] Update install failed: {e}")
            self.show_message("Update App", f"Update install failed:\n{e}", "error")
            self.root.after(0, lambda: self.set_buttons_enabled(True))
            self.root.after(0, self.stop_progress)

    def write_update_script(self, update_dir: Path, installer_path: Path) -> Path:
        script_path = update_dir / "apply_pc_optimizer_update.ps1"
        install_dir = current_install_dir()
        app_exe = install_dir / APP_EXECUTABLE_NAME
        log_path = update_dir / "installer.log"
        current_pid = os.getpid()

        script = f"""$ErrorActionPreference = "Stop"
$AppPid = {current_pid}
$Installer = {powershell_quote(installer_path)}
$InstallDir = {powershell_quote(install_dir)}
$AppExe = {powershell_quote(app_exe)}
$LogPath = {powershell_quote(log_path)}

try {{
    Wait-Process -Id $AppPid -Timeout 90 -ErrorAction SilentlyContinue
}} catch {{
}}

$arguments = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    ('/DIR="' + $InstallDir + '"'),
    ('/LOG="' + $LogPath + '"')
)

$process = Start-Process -FilePath $Installer -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -eq 0 -and (Test-Path -LiteralPath $AppExe)) {{
    Start-Process -FilePath $AppExe -WorkingDirectory $InstallDir
}}
"""
        script_path.write_text(script, encoding="utf-8")
        return script_path

    def download_update_installer(self, download_url: str, destination: Path) -> None:
        request = urllib.request.Request(
            download_url,
            headers={"User-Agent": "PC-Optimizer-Updater"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            next_log = 5 * 1024 * 1024
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_log:
                        if total:
                            self.write(f"  downloaded {humanize(downloaded)} / {humanize(total)}")
                        else:
                            self.write(f"  downloaded {humanize(downloaded)}")
                        next_log += 5 * 1024 * 1024

    def show_message(self, title: str, message: str, level: str = "info") -> None:
        def show() -> None:
            try:
                if level == "error":
                    mb.showerror(title, message)
                elif level == "warning":
                    mb.showwarning(title, message)
                else:
                    mb.showinfo(title, message)
            except Exception:
                pass

        self.root.after(0, show)

    def open_storage_manager(self) -> None:
        if self.storage_manager:
            try:
                if self.storage_manager.window.winfo_exists():
                    self.storage_manager.window.lift()
                    self.storage_manager.window.focus_force()
                    return
            except tk.TclError:
                self.storage_manager = None
        self.storage_manager = StorageManager(self)

    def open_temp_folder(self) -> None:
        try:
            temp_dir = Path(tempfile.gettempdir())
            if IS_WINDOWS:
                subprocess.run(["explorer", str(temp_dir)], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(temp_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(temp_dir)], check=False)
        except Exception as e:
            self.write(f"[!] Could not open temp folder: {e}")

    # Core tasks
    def optimize_clean(self) -> None:
        if not self.require_windows("Optimize & Clean"):
            return
        self.set_buttons_enabled(False)
        self.start_progress()
        freed_total = 0
        try:
            self.write("> Starting Optimize & Clean...")

            # 1) User temp directory
            try:
                user_temp = Path(tempfile.gettempdir())
                self.write(f"- Cleaning user temp: {user_temp}")
                freed_total += self.safe_delete_in_dir(user_temp)
            except Exception as e:
                self.write(f"[!] Temp clean failed: {e}")

            # 2) Windows temp directory (best-effort, may need admin for some entries)
            try:
                win_temp = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Temp"
                self.write(f"- Cleaning Windows temp: {win_temp}")
                freed_total += self.safe_delete_in_dir(win_temp)
            except Exception as e:
                self.write(f"[!] Windows temp clean partial/failed: {e}")

            # 3) Recent items
            try:
                recent = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"
                if recent.exists():
                    self.write(f"- Clearing Recent items: {recent}")
                    freed_total += self.safe_delete_in_dir(recent)
            except Exception as e:
                self.write(f"[!] Recent items clean failed: {e}")

            # 4) Recycle Bin (PowerShell)
            try:
                self.write("- Emptying Recycle Bin...")
                run_hidden(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except Exception as e:
                self.write(f"[!] Recycle Bin clean failed: {e}")

            self.write(f"> Optimize & Clean complete. Freed approx: {humanize(freed_total)}")
            try:
                mb.showinfo("Optimize & Clean", f"Freed approx: {humanize(freed_total)} (best-effort)")
            except Exception:
                pass
        finally:
            self.stop_progress()
            self.set_buttons_enabled(True)

    def performance_boost(self) -> None:
        if not self.require_windows("Boost Performance"):
            return
        self.set_buttons_enabled(False)
        self.write("> Applying Performance Boost...")

        # Prefer Ultimate Performance if available, else High performance
        ultimate = "e9a42b02-d5df-448d-aa00-03f14749eb61"
        high = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

        set_ok = False
        for guid, name in ((ultimate, "Ultimate Performance"), (high, "High performance")):
            try:
                self.write(f"- Setting power plan: {name}")
                res = run_hidden(["powercfg", "/S", guid], capture_output=True, text=True)
                if res.returncode == 0:
                    self.write(f"  ✔ Active plan set: {name}")
                    set_ok = True
                    break
                else:
                    self.write(f"  … Could not set {name}: {res.stderr.strip() or res.stdout.strip()}")
            except Exception as e:
                self.write(f"  … Error setting {name}: {e}")

        # Nudge CPU max performance on AC power for current scheme
        try:
            self.write("- Maximizing processor performance on AC power")
            run_hidden(
                [
                    "powercfg",
                    "-setacvalueindex",
                    "SCHEME_CURRENT",
                    "SUB_PROCESSOR",
                    "PROCTHROTTLEMAX",
                    "100",
                ],
                check=False,
            )
            run_hidden(["powercfg", "-setactive", "SCHEME_CURRENT"], check=False)
        except Exception as e:
            self.write(f"  … CPU performance tweak failed: {e}")

        if set_ok:
            self.write("> Performance Boost applied. You can revert later in Power Options.")
        else:
            self.write("> Performance Boost partially applied. Try enabling High performance in Power Options.")

        self.set_buttons_enabled(True)

    def revert_boost(self) -> None:
        if not self.require_windows("Revert Boost"):
            return
        self.set_buttons_enabled(False)
        self.write("> Reverting to Balanced power plan...")
        balanced = "381b4222-f694-41f0-9685-ff5bb260df2e"
        try:
            res = run_hidden(["powercfg", "/S", balanced], capture_output=True, text=True)
            if res.returncode == 0:
                self.write("  ✔ Active plan set: Balanced")
            else:
                self.write(f"  … Could not set Balanced: {res.stderr.strip() or res.stdout.strip()}")
        except Exception as e:
            self.write(f"  … Error setting Balanced: {e}")

        # Optionally reset CPU max on AC to default (not strictly necessary)
        try:
            run_hidden(["powercfg", "-setactive", "SCHEME_CURRENT"], check=False)
        except Exception:
            pass

        self.write("> Revert complete. Adjust further in Power Options if desired.")
        self.set_buttons_enabled(True)

    def aggressive_cleanup(self) -> None:
        if not self.require_windows("Aggressive Clean"):
            return
        if not mb.askyesno(
            title="Aggressive Clean",
            message=(
                "This will attempt to clear Windows Update cache, Delivery Optimization cache, and Prefetch.\n"
                "Some steps may require admin rights and will be best-effort. Proceed?"
            ),
            icon=mb.WARNING,
        ):
            return

        self.set_buttons_enabled(False)
        self.start_progress()
        freed_total = 0
        try:
            self.write("> Starting Aggressive Clean...")

            # Windows Update cache: stop service, delete Download content, start service
            try:
                self.write("- Stopping Windows Update service (wuauserv)...")
                run_hidden([
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue"
                ], check=False)

                win_sd = Path(os.environ.get("SystemRoot", "C:/Windows")) / "SoftwareDistribution" / "Download"
                self.write(f"- Clearing Windows Update cache: {win_sd}")
                freed_total += self.safe_delete_in_dir(win_sd)

                self.write("- Starting Windows Update service (wuauserv)...")
                run_hidden([
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Start-Service -Name wuauserv -ErrorAction SilentlyContinue"
                ], check=False)
            except Exception as e:
                self.write(f"[!] Windows Update cache clean failed: {e}")

            # Delivery Optimization cache
            try:
                do_cache = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft" / "Windows" / "DeliveryOptimization" / "Cache"
                self.write(f"- Clearing Delivery Optimization cache: {do_cache}")
                freed_total += self.safe_delete_in_dir(do_cache)
            except Exception as e:
                self.write(f"[!] Delivery Optimization clean failed: {e}")

            # Thumbnail cache
            try:
                thumbs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Explorer"
                self.write(f"- Clearing Thumbnail cache: {thumbs}")
                freed_total += self.safe_delete_in_dir(thumbs)
            except Exception as e:
                self.write(f"[!] Thumbnail cache clean failed: {e}")

            # Windows Error Reporting archives/queue
            try:
                wer_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "WER"
                for sub in ["ReportArchive", "ReportQueue"]:
                    p = wer_root / sub
                    self.write(f"- Clearing WER {sub}: {p}")
                    freed_total += self.safe_delete_in_dir(p)
            except Exception as e:
                self.write(f"[!] WER clean failed: {e}")

            # Prefetch (optional)
            try:
                prefetch = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Prefetch"
                self.write(f"- Clearing Prefetch (optional): {prefetch}")
                freed_total += self.safe_delete_in_dir(prefetch)
            except Exception as e:
                self.write(f"[!] Prefetch clean failed: {e}")

            self.write(f"> Aggressive Clean complete. Freed approx: {humanize(freed_total)}")
            try:
                mb.showinfo("Aggressive Clean", f"Freed approx: {humanize(freed_total)} (best-effort)")
            except Exception:
                pass
        finally:
            self.stop_progress()
            self.set_buttons_enabled(True)

    def clear_ram_cache(self) -> None:
        if not self.require_windows("Clear RAM Cache"):
            return
        self.set_buttons_enabled(False)
        self.start_progress()
        self.write("> Clearing RAM working sets (best-effort)...")

        # Use Windows API EmptyWorkingSet across processes. This trims cached pages; may skip protected/system processes.
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_VM_OPERATION = 0x0008
        access = PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA | PROCESS_VM_OPERATION

        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")

        psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
        psapi.EnumProcesses.restype = wt.BOOL
        psapi.EmptyWorkingSet.argtypes = [wt.HANDLE]
        psapi.EmptyWorkingSet.restype = wt.BOOL
        kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        kernel32.OpenProcess.restype = wt.HANDLE
        kernel32.CloseHandle.argtypes = [wt.HANDLE]
        kernel32.CloseHandle.restype = wt.BOOL

        trimmed = 0
        try:
            arr = (wt.DWORD * 4096)()
            needed = wt.DWORD()
            if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
                raise OSError("EnumProcesses failed")
            count = int(needed.value // ctypes.sizeof(wt.DWORD))
            for i in range(count):
                pid = arr[i]
                if pid == 0:
                    continue
                h_proc = kernel32.OpenProcess(access, False, pid)
                if not h_proc:
                    continue
                try:
                    if psapi.EmptyWorkingSet(h_proc):
                        trimmed += 1
                except Exception:
                    pass
                finally:
                    kernel32.CloseHandle(h_proc)
            self.write(f"  ✔ Trimmed working sets for ~{trimmed} processes (best-effort).")
        except Exception as e:
            self.write(f"[!] RAM clear failed: {e}")
        finally:
            self.stop_progress()
            self.set_buttons_enabled(True)

        self.write("> RAM clear request finished. Actual impact varies by system.")
        try:
            mb.showinfo("Clear RAM Cache", f"Requested working set trim. Processes trimmed: ~{trimmed} (best-effort).")
        except Exception:
            pass

    def component_cleanup(self) -> None:
        if not self.require_windows("Component Cleanup"):
            return
        if not mb.askyesno(
            title="Component Cleanup",
            message=(
                "Run DISM component store cleanup (removes superseded updates).\n"
                "Can take several minutes and may require admin. Proceed?"
            ),
            icon=mb.WARNING,
        ):
            return

        self.set_buttons_enabled(False)
        self.start_progress()
        status_msg = ""
        try:
            self.write("> Starting Component Store Cleanup (DISM)...")
            try:
                res = run_hidden(
                    [
                        "dism",
                        "/Online",
                        "/Cleanup-Image",
                        "/StartComponentCleanup",
                    ],
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    status_msg = "Component cleanup completed (see DISM log for details)."
                    self.write(f"  ✔ {status_msg}")
                else:
                    status_msg = res.stderr.strip() or res.stdout.strip() or "DISM cleanup failed"
                    self.write(f"[!] DISM cleanup failed: {status_msg}")
            except Exception as e:
                status_msg = f"DISM cleanup error: {e}"
                self.write(f"[!] {status_msg}")
            self.write("> Component cleanup finished (may have freed WinSxS space).")
            try:
                mb.showinfo("Component Cleanup", status_msg or "Completed")
            except Exception:
                pass
        finally:
            self.stop_progress()
            self.set_buttons_enabled(True)

    # Filesystem helpers
    def safe_delete_in_dir(self, directory: Path) -> int:
        if not directory.exists() or not directory.is_dir():
            return 0
        freed = 0
        for p in directory.iterdir():
            try:
                freed += self.entry_size(p)
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    try:
                        p.unlink()
                    except PermissionError:
                        # Some files may be locked; skip quietly
                        pass
            except Exception:
                # Skip entries causing errors
                pass
        return freed

    def entry_size(self, p: Path) -> int:
        try:
            if p.is_file():
                return p.stat().st_size
            if p.is_dir():
                total = 0
                for root, _, files in os.walk(p, topdown=False):
                    for f in files:
                        fp = Path(root) / f
                        try:
                            total += fp.stat().st_size
                        except Exception:
                            pass
                return total
        except Exception:
            return 0
        return 0


def main() -> None:
    root = tk.Tk()
    # Terminal-esque style
    try:
        root.option_add("*Font", FONT)
        root.option_add("*Button.font", FONT)
        root.option_add("*Label.font", FONT)
    except Exception:
        pass
    app = PCOptimizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
