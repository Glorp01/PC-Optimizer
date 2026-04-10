import os
import shutil
import subprocess
import tempfile
import threading
import ctypes
from ctypes import wintypes as wt
from pathlib import Path
import tkinter as tk
from tkinter import messagebox as mb, ttk

APP_TITLE = "PC Optimizer Panel"
BG = "#0b0b0b"
FG = "#d0d0d0"
ACCENT = "#16db65"  # terminal-ish green
FONT = ("Consolas", 10)
HEADER_FONT = ("Consolas", 12, "bold")


def humanize(n_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n_bytes)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024


class PCOptimizerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.configure(bg=BG)
        try:
            # Transparent, always-on-top for a panel feel
            root.attributes('-alpha', 0.93)
            root.attributes('-topmost', True)
        except Exception:
            pass
        root.geometry("520x360")

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
            text="Tip: Tasks may take a moment; watch the log.",
            bg=BG,
            fg="#808080",
            font=("Consolas", 9),
        )
        self.footer.pack(anchor="w", pady=(6, 0))

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
        self.btn_aggressive.configure(state=state)
        self.btn_revert.configure(state=state)
        self.btn_clear_ram.configure(state=state)
        self.btn_component_cleanup.configure(state=state)

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

    def open_temp_folder(self) -> None:
        try:
            temp_dir = Path(tempfile.gettempdir())
            subprocess.run(["explorer", str(temp_dir)], check=False)
        except Exception as e:
            self.write(f"[!] Could not open temp folder: {e}")

    # Core tasks
    def optimize_clean(self) -> None:
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
                subprocess.run(
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
        self.set_buttons_enabled(False)
        self.write("> Applying Performance Boost...")

        # Prefer Ultimate Performance if available, else High performance
        ultimate = "e9a42b02-d5df-448d-aa00-03f14749eb61"
        high = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

        set_ok = False
        for guid, name in ((ultimate, "Ultimate Performance"), (high, "High performance")):
            try:
                self.write(f"- Setting power plan: {name}")
                res = subprocess.run(["powercfg", "/S", guid], capture_output=True, text=True)
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
            subprocess.run(
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
            subprocess.run(["powercfg", "-setactive", "SCHEME_CURRENT"], check=False)
        except Exception as e:
            self.write(f"  … CPU performance tweak failed: {e}")

        if set_ok:
            self.write("> Performance Boost applied. You can revert later in Power Options.")
        else:
            self.write("> Performance Boost partially applied. Try enabling High performance in Power Options.")

        self.set_buttons_enabled(True)

    def revert_boost(self) -> None:
        self.set_buttons_enabled(False)
        self.write("> Reverting to Balanced power plan...")
        balanced = "381b4222-f694-41f0-9685-ff5bb260df2e"
        try:
            res = subprocess.run(["powercfg", "/S", balanced], capture_output=True, text=True)
            if res.returncode == 0:
                self.write("  ✔ Active plan set: Balanced")
            else:
                self.write(f"  … Could not set Balanced: {res.stderr.strip() or res.stdout.strip()}")
        except Exception as e:
            self.write(f"  … Error setting Balanced: {e}")

        # Optionally reset CPU max on AC to default (not strictly necessary)
        try:
            subprocess.run(["powercfg", "-setactive", "SCHEME_CURRENT"], check=False)
        except Exception:
            pass

        self.write("> Revert complete. Adjust further in Power Options if desired.")
        self.set_buttons_enabled(True)

    def aggressive_cleanup(self) -> None:
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
                subprocess.run([
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue"
                ], check=False)

                win_sd = Path(os.environ.get("SystemRoot", "C:/Windows")) / "SoftwareDistribution" / "Download"
                self.write(f"- Clearing Windows Update cache: {win_sd}")
                freed_total += self.safe_delete_in_dir(win_sd)

                self.write("- Starting Windows Update service (wuauserv)...")
                subprocess.run([
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
                res = subprocess.run(
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
