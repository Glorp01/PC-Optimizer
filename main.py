import os
import sys
import shutil
import subprocess
import tempfile
import threading
import time
import ctypes
import csv
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
OPENAI_RESPONSES_API = "https://api.openai.com/v1/responses"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "PC_OPTIMIZER_AI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
BG = "#0b0b0b"
FG = "#d0d0d0"
ACCENT = "#16db65"  # terminal-ish green
FONT = ("Consolas", 10)
HEADER_FONT = ("Consolas", 12, "bold")
IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GIB = 1024 ** 3
MIB = 1024 ** 2
SCAN_ENTRY_LIMIT = 25000

ASSISTANT_ACTIONS = {
    "optimize_clean": {
        "label": "Optimize & Clean",
        "description": "clear temp files, Recent items, and the Recycle Bin",
    },
    "performance_boost": {
        "label": "Boost Performance",
        "description": "switch to a performance-focused power plan and set AC CPU max performance to 100%",
    },
    "aggressive_cleanup": {
        "label": "Aggressive Clean",
        "description": "clear Windows Update, Delivery Optimization, thumbnails, WER, and Prefetch caches",
    },
    "clear_ram": {
        "label": "Clear RAM Cache",
        "description": "trim process working sets as a best-effort memory refresh",
    },
    "component_cleanup": {
        "label": "Component Cleanup",
        "description": "run DISM component store cleanup for superseded Windows components",
    },
    "storage_manager": {
        "label": "Storage Manager",
        "description": "open the storage scanner so you can inspect and remove large files yourself",
    },
    "startup_settings": {
        "label": "Startup Apps Settings",
        "description": "open Windows Startup Apps settings so you can disable unneeded startup entries",
    },
}

APP_VERSION = "0.0.0-dev"
try:
    from _build_info import APP_VERSION as APP_VERSION
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


def sampled_directory_size(directory: Path, max_entries: int = SCAN_ENTRY_LIMIT):
    info = {
        "path": directory,
        "size": 0,
        "entries": 0,
        "exists": False,
        "limited": False,
        "errors": 0,
    }
    try:
        if not directory.exists() or not directory.is_dir():
            return info
        info["exists"] = True
    except OSError:
        info["errors"] += 1
        return info

    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    info["entries"] += 1
                    if info["entries"] >= max_entries:
                        info["limited"] = True
                        return info
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            info["size"] += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        info["errors"] += 1
        except OSError:
            info["errors"] += 1
    return info


def windows_memory_status():
    if not IS_WINDOWS:
        return {}

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wt.DWORD),
            ("dwMemoryLoad", wt.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {}
    except Exception:
        return {}

    return {
        "load_percent": int(status.dwMemoryLoad),
        "total": int(status.ullTotalPhys),
        "available": int(status.ullAvailPhys),
    }


def windows_uptime_seconds() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        get_tick_count = ctypes.windll.kernel32.GetTickCount64
        get_tick_count.restype = ctypes.c_ulonglong
        return int(get_tick_count() // 1000)
    except Exception:
        return 0


def active_power_plan():
    info = {"guid": "", "name": "", "raw": "", "error": ""}
    if not IS_WINDOWS:
        return info
    try:
        res = run_hidden(["powercfg", "/GETACTIVESCHEME"], capture_output=True, text=True)
        raw = (res.stdout or res.stderr or "").strip()
        info["raw"] = raw
        match = re.search(r"Power Scheme GUID:\s*([0-9a-fA-F-]+)\s*(?:\((.*?)\))?", raw)
        if match:
            info["guid"] = match.group(1)
            info["name"] = (match.group(2) or "").strip()
        elif raw:
            info["name"] = raw
    except Exception as exc:
        info["error"] = str(exc)
    return info


def startup_items():
    if not IS_WINDOWS:
        return []

    items = []
    try:
        import winreg
    except ImportError:
        winreg = None

    if winreg:
        locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "Current user Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "All users Run"),
        ]
        for hive, subkey, label in locations:
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as key:
                    value_count = winreg.QueryInfoKey(key)[1]
                    for index in range(value_count):
                        try:
                            name, value, _ = winreg.EnumValue(key, index)
                            items.append({"name": name, "command": str(value), "location": label})
                        except OSError:
                            pass
            except OSError:
                pass

    startup_folders = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("ProgramData")
    if appdata:
        startup_folders.append(
            (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup", "Current user Startup folder")
        )
    if programdata:
        startup_folders.append(
            (Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup", "All users Startup folder")
        )

    for folder, label in startup_folders:
        try:
            if not folder.exists():
                continue
            for child in folder.iterdir():
                items.append({"name": child.name, "command": str(child), "location": label})
        except OSError:
            pass

    return items


def top_memory_processes(limit: int = 6):
    if not IS_WINDOWS:
        return []
    try:
        res = run_hidden(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    except Exception:
        return []
    if res.returncode != 0:
        return []

    processes = []
    for row in csv.reader(res.stdout.splitlines()):
        if len(row) < 5:
            continue
        memory_kb = int(re.sub(r"\D", "", row[4]) or "0")
        processes.append({"name": row[0], "pid": row[1], "memory": memory_kb * 1024})
    processes.sort(key=lambda item: item["memory"], reverse=True)
    return processes[:limit]


def cpu_status():
    info = {"name": "", "load_percent": None, "cores": None, "logical_processors": None, "max_clock_mhz": None}
    if not IS_WINDOWS:
        return info
    try:
        res = run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Processor | "
                    "Select-Object -First 1 Name,LoadPercentage,NumberOfCores,"
                    "NumberOfLogicalProcessors,MaxClockSpeed | ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
        )
        raw = (res.stdout or "").strip()
        if res.returncode != 0 or not raw:
            return info
        data = json.loads(raw)
        info["name"] = str(data.get("Name") or "").strip()
        info["load_percent"] = data.get("LoadPercentage")
        info["cores"] = data.get("NumberOfCores")
        info["logical_processors"] = data.get("NumberOfLogicalProcessors")
        info["max_clock_mhz"] = data.get("MaxClockSpeed")
    except Exception:
        pass
    return info


def parse_nvidia_smi_value(value: str):
    value = (value or "").strip()
    if not value or value.upper() == "[N/A]":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def gpu_status():
    info = {"gpus": [], "overall_usage_percent": None, "source": "", "error": ""}
    if not IS_WINDOWS:
        return info

    try:
        res = run_hidden(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            for row in csv.reader(res.stdout.splitlines()):
                if len(row) < 7:
                    continue
                gpu = {
                    "name": row[0].strip(),
                    "usage_percent": parse_nvidia_smi_value(row[1]),
                    "memory_usage_percent": parse_nvidia_smi_value(row[2]),
                    "memory_used": (parse_nvidia_smi_value(row[3]) or 0) * MIB,
                    "memory_total": (parse_nvidia_smi_value(row[4]) or 0) * MIB,
                    "temperature_c": parse_nvidia_smi_value(row[5]),
                    "driver_version": row[6].strip(),
                    "source": "nvidia-smi",
                }
                info["gpus"].append(gpu)
            if info["gpus"]:
                usages = [gpu["usage_percent"] for gpu in info["gpus"] if gpu.get("usage_percent") is not None]
                if usages:
                    info["overall_usage_percent"] = max(usages)
                info["source"] = "nvidia-smi"
                return info
    except Exception:
        pass

    try:
        res = run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
        )
        raw = (res.stdout or "").strip()
        if res.returncode == 0 and raw:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                info["gpus"].append(
                    {
                        "name": str(item.get("Name") or "").strip(),
                        "usage_percent": None,
                        "memory_usage_percent": None,
                        "memory_used": None,
                        "memory_total": item.get("AdapterRAM"),
                        "temperature_c": None,
                        "driver_version": str(item.get("DriverVersion") or "").strip(),
                        "source": "Win32_VideoController",
                    }
                )
            if info["gpus"]:
                info["source"] = "Win32_VideoController"
    except Exception as exc:
        info["error"] = str(exc)

    try:
        res = run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$samples = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage' "
                    "-ErrorAction SilentlyContinue).CounterSamples; "
                    "$sum = ($samples | Where-Object { $_.InstanceName -match 'engtype_(3d|compute|copy|video)' } | "
                    "Measure-Object -Property CookedValue -Sum).Sum; "
                    "if ($null -ne $sum) { [math]::Round([math]::Min($sum, 100), 1) }"
                ),
            ],
            capture_output=True,
            text=True,
        )
        raw = (res.stdout or "").strip()
        if res.returncode == 0 and raw:
            info["overall_usage_percent"] = float(raw)
    except Exception:
        pass

    return info


def compact_scan_context(scan):
    if not scan:
        return {}
    metrics = scan.get("metrics", {})
    drive = metrics.get("drive") or {}
    memory = metrics.get("memory") or {}
    cpu = metrics.get("cpu") or {}
    gpu = metrics.get("gpu") or {}
    power = metrics.get("power_plan") or {}
    startup = metrics.get("startup_items") or []
    caches = sorted(metrics.get("caches") or [], key=lambda item: item.get("size", 0), reverse=True)

    return {
        "findings": [
            {
                "severity": finding.get("severity"),
                "title": finding.get("title"),
                "detail": finding.get("detail"),
                "fix": finding.get("fix"),
            }
            for finding in scan.get("findings", [])[:6]
        ],
        "recommended_actions": [
            ASSISTANT_ACTIONS[action]["label"]
            for action in scan.get("actions", [])
            if action in ASSISTANT_ACTIONS
        ],
        "drive": {
            "path": drive.get("path"),
            "free": humanize(drive.get("free", 0)) if drive else None,
            "total": humanize(drive.get("total", 0)) if drive else None,
            "free_percent": round(drive.get("free_percent", 0), 1) if drive else None,
        },
        "memory": {
            "load_percent": memory.get("load_percent"),
            "available": humanize(memory.get("available", 0)) if memory else None,
            "total": humanize(memory.get("total", 0)) if memory else None,
        },
        "cpu": cpu,
        "gpu": gpu,
        "power_plan": power.get("name") or power.get("raw"),
        "startup_count": len(startup),
        "largest_caches": [
            {
                "name": cache.get("name"),
                "size": humanize(cache.get("size", 0)),
                "limited": cache.get("limited"),
            }
            for cache in caches[:5]
        ],
        "uptime_seconds": metrics.get("uptime_seconds"),
    }


def extract_response_text(response_data) -> str:
    text = response_data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    pieces = []
    for output in response_data.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") in ("output_text", "text"):
                value = content.get("text")
                if isinstance(value, str):
                    pieces.append(value)
    return "\n".join(piece.strip() for piece in pieces if piece.strip()).strip()


def ask_openai_performance_assistant(prompt: str, scan, conversation):
    api_key = os.environ.get(OPENAI_API_KEY_ENV, "").strip()
    if not api_key:
        return ""

    model = os.environ.get(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    recent_history = conversation[-8:]
    context = compact_scan_context(scan)
    developer_prompt = (
        "You are the AI Performance Assistant inside PC Optimizer. "
        "Answer as a practical Windows PC optimization helper. "
        "Use the provided diagnostic context when available, and say when a metric was not scanned. "
        "Do not claim that a fix was applied. Any system-changing action requires explicit user approval in the app. "
        "Keep answers concise, specific, and focused on diagnosing or improving PC performance."
    )
    user_payload = {
        "user_question": prompt,
        "pc_diagnostics": context,
        "recent_conversation": recent_history,
    }
    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": json.dumps(user_payload, indent=2)},
        ],
        "max_output_tokens": 700,
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PC-Optimizer-AI",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        response_data = json.loads(response.read().decode("utf-8"))
    return extract_response_text(response_data)


def build_performance_scan():
    result = {
        "timestamp": time.time(),
        "metrics": {},
        "findings": [],
        "actions": [],
    }

    def add_action(action_key: str) -> None:
        if action_key and action_key in ASSISTANT_ACTIONS and action_key not in result["actions"]:
            result["actions"].append(action_key)

    def add_finding(severity: str, title: str, detail: str, fix: str = "", action_key: str = "") -> None:
        result["findings"].append(
            {
                "severity": severity,
                "title": title,
                "detail": detail,
                "fix": fix,
                "action": action_key,
            }
        )
        add_action(action_key)

    drive_root = Path(os.environ.get("SystemDrive", "C:") + "\\") if IS_WINDOWS else Path(os.path.abspath(os.sep))
    try:
        if not drive_root.exists():
            drive_root = Path(Path.cwd().anchor or os.path.abspath(os.sep))
        usage = shutil.disk_usage(str(drive_root))
        free_percent = (usage.free / usage.total * 100) if usage.total else 0
        result["metrics"]["drive"] = {
            "path": str(drive_root),
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "free_percent": free_percent,
        }
        if free_percent <= 10 or usage.free <= 15 * GIB:
            add_finding(
                "high",
                "Low free storage",
                f"{drive_root} has {humanize(usage.free)} free ({free_percent:.1f}%). Low free space can slow updates, paging, and app launches.",
                "Free space with Optimize & Clean, then inspect large folders in Storage Manager.",
                "storage_manager",
            )
            add_action("optimize_clean")
        elif free_percent <= 20 or usage.free <= 40 * GIB:
            add_finding(
                "medium",
                "Storage is getting tight",
                f"{drive_root} has {humanize(usage.free)} free ({free_percent:.1f}%). Keeping more headroom helps Windows cache and update reliably.",
                "Run a cleanup and review large folders if the drive keeps filling up.",
                "optimize_clean",
            )
    except Exception as exc:
        result["metrics"]["drive_error"] = str(exc)

    cache_specs = []
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
    programdata = os.environ.get("ProgramData")
    localappdata = os.environ.get("LOCALAPPDATA")
    appdata = os.environ.get("APPDATA")

    cache_specs.append(("User temp", Path(tempfile.gettempdir()), "basic"))
    cache_specs.append(("Windows temp", system_root / "Temp", "basic"))
    if appdata:
        cache_specs.append(("Recent items", Path(appdata) / "Microsoft" / "Windows" / "Recent", "basic"))
    cache_specs.append(("Windows Update cache", system_root / "SoftwareDistribution" / "Download", "deep"))
    cache_specs.append(("Prefetch cache", system_root / "Prefetch", "deep"))
    if programdata:
        cache_specs.append(("Delivery Optimization cache", Path(programdata) / "Microsoft" / "Windows" / "DeliveryOptimization" / "Cache", "deep"))
    if localappdata:
        explorer_cache = Path(localappdata) / "Microsoft" / "Windows" / "Explorer"
        cache_specs.append(("Thumbnail cache", explorer_cache, "deep"))
        cache_specs.append(("Windows Error Reporting", Path(localappdata) / "Microsoft" / "Windows" / "WER", "deep"))

    cache_metrics = []
    totals = {"basic": 0, "deep": 0}
    limited = []
    for name, path, group in cache_specs:
        info = sampled_directory_size(path)
        info["name"] = name
        info["group"] = group
        cache_metrics.append(info)
        totals[group] += info["size"]
        if info["limited"]:
            limited.append(name)
    result["metrics"]["caches"] = cache_metrics

    limited_note = ""
    if limited:
        limited_note = f" Some folders hit the scan limit, so actual size may be higher: {', '.join(limited)}."

    if totals["basic"] >= 1 * GIB:
        add_finding(
            "medium",
            "Large temp file buildup",
            f"Basic temp and recent-item caches are using about {humanize(totals['basic'])}.{limited_note}",
            "Run Optimize & Clean to clear ordinary temp files and the Recycle Bin.",
            "optimize_clean",
        )
    elif totals["basic"] >= 350 * MIB:
        add_finding(
            "low",
            "Temp files are worth cleaning",
            f"Basic temp and recent-item caches are using about {humanize(totals['basic'])}.{limited_note}",
            "Run Optimize & Clean during a maintenance pass.",
            "optimize_clean",
        )

    if totals["deep"] >= 2 * GIB:
        add_finding(
            "medium",
            "Windows cache folders are large",
            f"Windows Update, Delivery Optimization, thumbnails, WER, and Prefetch caches are using about {humanize(totals['deep'])}.{limited_note}",
            "Run Aggressive Clean if you want a deeper cache cleanup.",
            "aggressive_cleanup",
        )
    elif totals["deep"] >= 750 * MIB:
        add_finding(
            "low",
            "Windows caches have moderate buildup",
            f"Deep Windows cache folders are using about {humanize(totals['deep'])}.{limited_note}",
            "Aggressive Clean can clear these if you need extra space.",
            "aggressive_cleanup",
        )

    memory = windows_memory_status()
    result["metrics"]["memory"] = memory
    processes = top_memory_processes()
    result["metrics"]["top_memory_processes"] = processes
    if memory:
        top_summary = ", ".join(f"{p['name']} ({humanize(p['memory'])})" for p in processes[:3])
        process_note = f" Biggest visible memory users: {top_summary}." if top_summary else ""
        if memory["load_percent"] >= 85 or memory["available"] <= 2 * GIB:
            add_finding(
                "high",
                "Memory pressure is high",
                f"Physical memory is {memory['load_percent']}% used with {humanize(memory['available'])} available.{process_note}",
                "Close heavy apps first; Clear RAM Cache can request a best-effort working-set trim.",
                "clear_ram",
            )
        elif memory["load_percent"] >= 75 or memory["available"] <= 4 * GIB:
            add_finding(
                "medium",
                "Memory headroom is limited",
                f"Physical memory is {memory['load_percent']}% used with {humanize(memory['available'])} available.{process_note}",
                "Review high-memory apps and use Clear RAM Cache only as a temporary refresh.",
                "clear_ram",
            )

    cpu = cpu_status()
    result["metrics"]["cpu"] = cpu
    cpu_load = cpu.get("load_percent")
    if isinstance(cpu_load, (int, float)):
        cpu_name = cpu.get("name") or "CPU"
        if cpu_load >= 90:
            add_finding(
                "high",
                "CPU load is very high",
                f"{cpu_name} is currently around {cpu_load}% used. Sustained high CPU usage can cause lag, stutter, and slow app launches.",
                "Close or uninstall the app causing the load, check startup apps, and use Task Manager for a per-process CPU view.",
            )
        elif cpu_load >= 75:
            add_finding(
                "medium",
                "CPU load is elevated",
                f"{cpu_name} is currently around {cpu_load}% used.",
                "If the PC feels slow right now, identify the busy process in Task Manager before applying cleanup fixes.",
            )

    gpu = gpu_status()
    result["metrics"]["gpu"] = gpu
    gpu_usage = gpu.get("overall_usage_percent")
    if isinstance(gpu_usage, (int, float)) and gpu_usage >= 90:
        names = ", ".join(item.get("name", "GPU") for item in gpu.get("gpus", [])[:2]) or "GPU"
        add_finding(
            "medium",
            "GPU load is very high",
            f"{names} is currently around {gpu_usage}% used. High GPU usage is normal during games or rendering, but can lower desktop responsiveness.",
            "Close GPU-heavy games, recording software, or browser tabs if this usage is unexpected.",
        )

    power = active_power_plan()
    result["metrics"]["power_plan"] = power
    plan_name = (power.get("name") or power.get("raw") or "").strip()
    if IS_WINDOWS:
        normalized_plan = plan_name.casefold()
        if plan_name and not any(marker in normalized_plan for marker in ("high performance", "ultimate performance")):
            add_finding(
                "medium",
                "Power plan may be limiting performance",
                f"The active power plan appears to be: {plan_name}. Balanced or saver plans can reduce CPU responsiveness.",
                "Use Boost Performance while plugged in, then Revert Boost later if you prefer Balanced.",
                "performance_boost",
            )
        elif not plan_name:
            add_finding(
                "low",
                "Power plan could not be verified",
                "The scan could not read the active power plan.",
                "Try Boost Performance if you want the app to request a performance-focused power plan.",
                "performance_boost",
            )

    startup = startup_items()
    result["metrics"]["startup_items"] = startup
    if len(startup) >= 18:
        add_finding(
            "medium",
            "Many startup entries",
            f"{len(startup)} startup entries were found. Too many auto-starting apps can slow sign-in and consume memory.",
            "Open Startup Apps settings and disable items you do not need at login.",
            "startup_settings",
        )
    elif len(startup) >= 10:
        add_finding(
            "low",
            "Startup apps may be worth reviewing",
            f"{len(startup)} startup entries were found.",
            "Review Startup Apps settings if boot or sign-in feels slow.",
            "startup_settings",
        )

    uptime = windows_uptime_seconds()
    result["metrics"]["uptime_seconds"] = uptime
    if uptime >= 7 * 24 * 60 * 60:
        days = uptime // (24 * 60 * 60)
        add_finding(
            "low",
            "Long uptime",
            f"Windows has been running for about {days} days. Long sessions can leave drivers, updates, and background apps in a rough state.",
            "Restart when convenient before doing deeper troubleshooting.",
        )

    if not result["findings"]:
        add_finding(
            "info",
            "No obvious performance bottleneck found",
            "The quick scan did not find low disk space, large cache buildup, high memory pressure, or a limiting power plan.",
            "If the PC still feels slow, check a specific app or run Storage Manager for a deeper file-by-file look.",
        )

    return result


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


class AIAssistantWindow:
    def __init__(self, app: "PCOptimizerApp") -> None:
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("AI Performance Assistant")
        self.window.configure(bg=BG)
        self.window.geometry("760x540")
        self.window.minsize(620, 420)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.last_scan = None
        self.scanning = False
        self.responding = False
        self.online_ai_allowed = None
        self.conversation = []

        wrap = tk.Frame(self.window, bg=BG, highlightthickness=1, highlightbackground="#222")
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        header = tk.Label(wrap, text="> AI Performance Assistant", bg=BG, fg=ACCENT, font=HEADER_FONT)
        header.pack(anchor="w")

        self.chat = tk.Text(
            wrap,
            bg="#0f0f0f",
            fg=FG,
            insertbackground=ACCENT,
            font=FONT,
            relief=tk.FLAT,
            padx=8,
            pady=8,
            wrap=tk.WORD,
            height=18,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        self.chat.tag_configure("assistant", foreground=FG)
        self.chat.tag_configure("user", foreground="#9fd3ff")
        self.chat.tag_configure("system", foreground=ACCENT)
        self.chat.configure(state=tk.DISABLED)

        input_row = tk.Frame(wrap, bg=BG)
        input_row.pack(fill=tk.X)
        self.prompt_var = tk.StringVar()
        self.prompt_entry = tk.Entry(
            input_row,
            textvariable=self.prompt_var,
            bg="#111",
            fg=FG,
            insertbackground=ACCENT,
            relief=tk.FLAT,
            font=FONT,
        )
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7)
        self.prompt_entry.bind("<Return>", self.on_send)

        self.send_button = tk.Button(
            input_row,
            text="Ask",
            command=self.on_send,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=12,
            pady=6,
        )
        self.send_button.pack(side=tk.LEFT, padx=(8, 0))

        action_row = tk.Frame(wrap, bg=BG)
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.scan_button = tk.Button(
            action_row,
            text="Scan PC",
            command=self.confirm_scan,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.scan_button.pack(side=tk.LEFT)

        self.fix_button = tk.Button(
            action_row,
            text="Apply Recommended Fixes",
            command=self.on_apply_recommended,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            disabledforeground="#555",
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            state=tk.DISABLED,
        )
        self.fix_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        status = tk.Label(wrap, textvariable=self.status_var, bg=BG, fg="#808080", font=("Consolas", 9))
        status.pack(anchor="w", pady=(8, 0))

        self.append_assistant(
            "Ask me about CPU, GPU, RAM, storage, startup apps, game performance, or what to fix. I will ask before reading diagnostics or running any fix.",
            record=False,
        )
        self.prompt_entry.focus_set()

    def append_message(self, speaker: str, message: str, tag: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{speaker}: ", tag)
        self.chat.insert(tk.END, message.strip() + "\n\n", tag)
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def append_assistant(self, message: str, record: bool = True) -> None:
        self.append_message("AI", message, "assistant")
        if record:
            self.conversation.append({"role": "assistant", "content": message.strip()})

    def append_user(self, message: str, record: bool = True) -> None:
        self.append_message("You", message, "user")
        if record:
            self.conversation.append({"role": "user", "content": message.strip()})

    def append_system(self, message: str) -> None:
        self.append_message("System", message, "system")

    def set_scanning(self, scanning: bool) -> None:
        self.scanning = scanning
        state = tk.DISABLED if scanning else tk.NORMAL
        self.scan_button.configure(state=state)
        input_state = tk.DISABLED if scanning or self.responding else tk.NORMAL
        self.send_button.configure(state=input_state)
        self.prompt_entry.configure(state=input_state)
        self.status_var.set("Scanning..." if scanning else "Ready")
        self.update_fix_button()

    def set_responding(self, responding: bool) -> None:
        self.responding = responding
        state = tk.DISABLED if responding or self.scanning else tk.NORMAL
        self.send_button.configure(state=state)
        self.prompt_entry.configure(state=state)
        self.status_var.set("Thinking..." if responding else "Ready")
        self.update_fix_button()

    def update_fix_button(self) -> None:
        has_actions = bool(self.last_scan and self.last_scan.get("actions"))
        state = tk.NORMAL if has_actions and not self.scanning and not self.responding else tk.DISABLED
        self.fix_button.configure(state=state)

    def on_send(self, _event=None) -> None:
        prompt = self.prompt_var.get().strip()
        if not prompt:
            return
        self.prompt_var.set("")
        self.append_user(prompt)
        self.handle_prompt(prompt)

    def handle_prompt(self, prompt: str) -> None:
        lower = prompt.casefold()
        requested_actions = self.actions_from_prompt(lower)
        wants_action = any(word in lower for word in ("run", "apply", "fix", "clean", "clear", "enable", "switch", "start", "do it"))
        explicit_scan = any(word in lower for word in ("scan", "diagnose", "diagnostic", "check my pc"))

        if requested_actions and wants_action:
            self.confirm_and_apply_actions(requested_actions)
            return

        if "fix" in lower and self.last_scan:
            self.confirm_and_apply_actions(self.last_scan.get("actions", []))
            return

        if explicit_scan:
            self.confirm_scan()
            return

        if self.should_answer_locally_without_ai(lower):
            self.append_assistant(self.local_assistant_response(prompt))
            return

        if self.prompt_needs_scan(lower) and not self.last_scan:
            self.append_assistant("I need a read-only scan before I can answer that with your PC's actual numbers.", record=False)
            self.confirm_scan()
            return

        self.start_answer_worker(prompt)

    def actions_from_prompt(self, lower_prompt: str):
        actions = []

        def add(action_key: str) -> None:
            if action_key not in actions:
                actions.append(action_key)

        if any(word in lower_prompt for word in ("temp", "junk", "recycle", "recent", "basic clean", "optimize")):
            add("optimize_clean")
        if any(word in lower_prompt for word in ("aggressive", "deep clean", "windows update cache", "delivery optimization", "prefetch")):
            add("aggressive_cleanup")
        if any(word in lower_prompt for word in ("boost", "power plan", "high performance", "ultimate performance")):
            add("performance_boost")
        if any(word in lower_prompt for word in ("ram", "memory")):
            add("clear_ram")
        if any(word in lower_prompt for word in ("component", "winsxs", "dism")):
            add("component_cleanup")
        if any(word in lower_prompt for word in ("storage", "disk", "drive", "large file")):
            add("storage_manager")
        if "startup" in lower_prompt:
            add("startup_settings")
        return actions

    def should_answer_locally_without_ai(self, lower_prompt: str) -> bool:
        return (
            self.is_unclear_prompt(lower_prompt)
            or self.is_greeting(lower_prompt)
            or any(word in lower_prompt for word in ("thanks", "thank you", "ty"))
            or any(phrase in lower_prompt for phrase in ("help", "what can you do", "commands", "questions can i ask"))
        )

    def prompt_needs_scan(self, lower_prompt: str) -> bool:
        system_topics = (
            "my pc",
            "my computer",
            "my laptop",
            "my gpu",
            "my cpu",
            "my ram",
            "my memory",
            "my disk",
            "my drive",
            "how much",
            "usage",
            "being used",
            "why is it slow",
            "what is wrong",
            "what's wrong",
            "bottleneck",
            "lag",
            "stutter",
            "fps",
            "temperature",
            "temp",
        )
        metric_words = ("gpu", "cpu", "ram", "memory", "disk", "storage", "startup", "power plan")
        return any(topic in lower_prompt for topic in system_topics) or (
            "used" in lower_prompt and any(word in lower_prompt for word in metric_words)
        )

    def start_answer_worker(self, prompt: str) -> None:
        if self.responding:
            return
        self.set_responding(True)
        threading.Thread(target=self.answer_worker, args=(prompt,), daemon=True).start()

    def answer_worker(self, prompt: str) -> None:
        online_error = ""
        answer = ""
        try:
            if self.should_use_online_ai():
                try:
                    answer = ask_openai_performance_assistant(prompt, self.last_scan, self.conversation)
                except Exception as exc:
                    online_error = str(exc)
            if not answer:
                answer = self.local_assistant_response(prompt)
                if online_error:
                    answer += f"\n\nOnline AI was unavailable, so I used local diagnostics instead. Error: {online_error}"
        except Exception as exc:
            answer = f"I could not answer that cleanly: {exc}"
        self.post_ui(lambda answer=answer: self.answer_finished(answer))

    def should_use_online_ai(self) -> bool:
        if not os.environ.get(OPENAI_API_KEY_ENV, "").strip():
            return False
        if self.online_ai_allowed is True:
            return True
        if self.online_ai_allowed is False:
            return False

        accepted = False
        done = threading.Event()

        def ask_permission() -> None:
            nonlocal accepted
            try:
                accepted = mb.askyesno(
                    "Online AI",
                    (
                        "Use online AI for richer answers?\n\n"
                        "This sends your question and a compact diagnostic summary to OpenAI. "
                        "No optimizer action will run without a separate confirmation."
                    ),
                    parent=self.window,
                )
            except Exception:
                accepted = False
            finally:
                done.set()

        self.post_ui(ask_permission)
        if not done.wait(120):
            self.online_ai_allowed = False
            return False
        self.online_ai_allowed = accepted
        return accepted

    def answer_finished(self, answer: str) -> None:
        self.set_responding(False)
        self.append_assistant(answer)

    def local_assistant_response(self, prompt: str) -> str:
        lower = prompt.casefold()
        metrics = self.last_scan.get("metrics", {}) if self.last_scan else {}

        if self.is_unclear_prompt(lower):
            return self.clarify_response()
        if self.is_greeting(lower):
            return (
                "Hi. Ask me what you want checked, like GPU usage, CPU usage, RAM pressure, storage space, "
                "startup apps, why games are lagging, or what to fix first."
            )
        if any(word in lower for word in ("thanks", "thank you", "ty")):
            return "You're welcome. Ask me any specific PC performance question and I will answer from the latest scan when I can."
        if "what is" in lower or "explain" in lower:
            return self.explain_performance_term(lower)
        if any(phrase in lower for phrase in ("what can you do", "help", "commands", "questions can i ask")):
            return self.capabilities_response()
        if any(word in lower for word in ("gpu", "graphics", "vram")):
            return self.gpu_answer(metrics)
        if "cpu" in lower or "processor" in lower:
            return self.cpu_answer(metrics)
        if any(word in lower for word in ("ram", "memory")):
            return self.memory_answer(metrics)
        if any(word in lower for word in ("storage", "disk", "drive", "cache", "temp", "space")):
            return self.storage_answer(metrics)
        if "startup" in lower or "boot" in lower or "login" in lower:
            return self.startup_answer(metrics)
        if "power" in lower or "boost" in lower or "battery" in lower:
            return self.power_answer(metrics)
        if any(word in lower for word in ("game", "gaming", "fps", "frames", "lag", "stutter", "slow", "bottleneck", "performance", "wrong", "issue", "problem", "fix first", "what should")):
            return self.performance_answer(metrics)

        if self.last_scan:
            return self.no_topic_match_response()
        return (
            "I can answer general PC optimization questions, but for anything specific to this computer I need a read-only scan first. "
            "For slow performance, the usual first checks are CPU/GPU usage, RAM pressure, free disk space, startup apps, and the active power plan."
        )

    def is_unclear_prompt(self, lower_prompt: str) -> bool:
        cleaned = re.sub(r"[^a-z0-9\s?]", " ", lower_prompt).strip()
        if not cleaned:
            return True
        tokens = cleaned.split()
        if len(tokens) == 1 and len(tokens[0]) <= 2 and tokens[0] not in ("hi", "yo"):
            return True
        random_chars = re.sub(r"[^a-z0-9]", "", cleaned)
        if len(random_chars) <= 2 and "?" not in cleaned:
            return True
        return False

    def is_greeting(self, lower_prompt: str) -> bool:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", lower_prompt).strip()
        return cleaned in ("hi", "hello", "hey", "yo", "sup")

    def clarify_response(self) -> str:
        return (
            "I need a little more detail. Ask a specific question like:\n"
            "- How much is my GPU being used?\n"
            "- Why is my PC slow?\n"
            "- What is using my RAM?\n"
            "- Do I need to clean storage?\n"
            "- What should I fix first?"
        )

    def capabilities_response(self) -> str:
        mode = "online AI is available" if os.environ.get(OPENAI_API_KEY_ENV, "").strip() else "using local diagnostics"
        return (
            f"I can answer performance questions ({mode}). I can check or explain CPU, GPU, RAM, storage, startup apps, "
            "power plan, FPS/lag, cache buildup, and scan findings. I will ask before scanning and before running any fix."
        )

    def no_topic_match_response(self) -> str:
        return (
            "I am not sure which performance area you mean. Ask about CPU, GPU, RAM, storage, startup apps, power plan, "
            "game FPS, or ask 'what should I fix first?'"
        )

    def gpu_answer(self, metrics) -> str:
        gpu = metrics.get("gpu") or {}
        gpus = gpu.get("gpus") or []
        if not gpu:
            return "The last scan does not include GPU data. Run Scan PC again and I can check GPU usage, GPU name, VRAM, and temperature when Windows exposes it."
        if not gpus and gpu.get("overall_usage_percent") is None:
            return (
                "I could not read GPU usage from Windows. If you have an NVIDIA card, installing/updating NVIDIA drivers usually provides `nvidia-smi`, "
                "which lets the assistant read GPU usage more accurately."
            )

        lines = []
        overall = gpu.get("overall_usage_percent")
        if overall is not None:
            lines.append(f"Current GPU usage is about {overall}%.")
        for item in gpus:
            name = item.get("name") or "GPU"
            parts = [name]
            if item.get("usage_percent") is not None:
                parts.append(f"{item['usage_percent']}% core")
            if item.get("memory_used") is not None and item.get("memory_total"):
                parts.append(f"{humanize(item['memory_used'])} / {humanize(item['memory_total'])} VRAM")
            elif item.get("memory_total"):
                parts.append(f"{humanize(item['memory_total'])} VRAM")
            if item.get("temperature_c") is not None:
                parts.append(f"{item['temperature_c']} C")
            lines.append("- " + ", ".join(parts))
        if overall is None:
            lines.append("Windows exposed the GPU model, but not live usage in this scan.")
        elif overall >= 90:
            lines.append("That is high. It is normal while gaming/rendering, but unexpected high usage can mean a game, browser tab, recorder, or overlay is using the GPU.")
        elif overall >= 40:
            lines.append("That is moderate. It can be normal with games, video playback, browser acceleration, or desktop effects.")
        else:
            lines.append("That is low, so the GPU is probably not the main bottleneck right now.")
        return "\n".join(lines)

    def cpu_answer(self, metrics) -> str:
        cpu = metrics.get("cpu") or {}
        if not cpu:
            return "The last scan does not include CPU data. Run Scan PC again and I can check current CPU load."
        name = cpu.get("name") or "CPU"
        load = cpu.get("load_percent")
        details = []
        if cpu.get("cores") and cpu.get("logical_processors"):
            details.append(f"{cpu['cores']} cores / {cpu['logical_processors']} threads")
        if cpu.get("max_clock_mhz"):
            details.append(f"up to {cpu['max_clock_mhz']} MHz")
        suffix = f" ({', '.join(details)})" if details else ""
        if load is None:
            return f"{name}{suffix}. Windows did not report a live CPU usage number in the scan."
        if load >= 90:
            advice = "That is very high. Open Task Manager and sort by CPU to find the process before applying cleanup fixes."
        elif load >= 75:
            advice = "That is elevated. If the PC feels slow, a busy foreground app or startup/background app may be the cause."
        else:
            advice = "That is not high enough by itself to explain major slowdowns right now."
        return f"{name}{suffix} is currently around {load}% used. {advice}"

    def memory_answer(self, metrics) -> str:
        memory = metrics.get("memory") or {}
        processes = metrics.get("top_memory_processes") or []
        if not memory:
            return "I could not read memory pressure from the last scan."
        lines = [
            f"Memory is {memory['load_percent']}% used with {humanize(memory['available'])} available out of {humanize(memory['total'])}."
        ]
        if processes:
            lines.append("Largest visible memory users:")
            for proc in processes[:5]:
                lines.append(f"- {proc['name']} (PID {proc['pid']}): {humanize(proc['memory'])}")
        if memory["load_percent"] >= 85:
            lines.append("That is high. Close heavy apps first; Clear RAM Cache is only a temporary refresh.")
        elif memory["load_percent"] >= 75:
            lines.append("That is somewhat tight. Startup apps and browser tabs are common causes.")
        else:
            lines.append("RAM pressure does not look like the main issue right now.")
        return "\n".join(lines)

    def storage_answer(self, metrics) -> str:
        drive = metrics.get("drive") or {}
        caches = sorted(metrics.get("caches") or [], key=lambda item: item.get("size", 0), reverse=True)
        lines = []
        if drive:
            lines.append(
                f"{drive['path']} has {humanize(drive['free'])} free out of {humanize(drive['total'])} ({drive['free_percent']:.1f}% free)."
            )
        if caches:
            lines.append("Largest cache areas from the last scan:")
            for cache in caches[:5]:
                limited = " or more" if cache.get("limited") else ""
                lines.append(f"- {cache['name']}: {humanize(cache['size'])}{limited}")
        if drive and drive.get("free_percent", 100) <= 15:
            lines.append("Low free space can slow updates, paging, and app launches. Use Optimize & Clean, then Storage Manager for large personal files.")
        else:
            lines.append("Best fix: clean ordinary temp files first, then use Storage Manager if you need to find large files.")
        return "\n".join(lines)

    def startup_answer(self, metrics) -> str:
        startup = metrics.get("startup_items") or []
        lines = [f"The last scan found {len(startup)} startup entries."]
        for item in startup[:8]:
            lines.append(f"- {item['name']} ({item['location']})")
        if len(startup) >= 18:
            lines.append("That is a lot. Open Startup Apps settings and disable anything you do not need immediately after login.")
        elif len(startup) >= 10:
            lines.append("This is worth reviewing if boot or login feels slow.")
        else:
            lines.append("Startup apps do not look excessive from this scan.")
        return "\n".join(lines)

    def power_answer(self, metrics) -> str:
        power = metrics.get("power_plan") or {}
        plan = power.get("name") or power.get("raw") or "unknown"
        lower_plan = plan.casefold()
        if "high performance" in lower_plan or "ultimate performance" in lower_plan:
            return f"The active power plan is {plan}. That is already performance-focused."
        return (
            f"The active power plan is {plan}. Balanced or saver plans can reduce CPU responsiveness. "
            "Boost Performance can switch to a performance-focused plan after you approve it."
        )

    def performance_answer(self, metrics) -> str:
        if not self.last_scan:
            return "Run Scan PC first and I can tell you what looks wrong on this computer."
        findings = self.last_scan.get("findings", [])
        if not findings:
            return "The last scan did not find a clear bottleneck. Ask about CPU, GPU, RAM, storage, startup apps, or power plan for a more specific check."
        lines = ["Most likely performance issues from the last scan:"]
        for finding in findings[:4]:
            lines.append(f"- {finding.get('title')}: {finding.get('detail')}")
            if finding.get("fix"):
                lines.append(f"  Fix: {finding['fix']}")
        actions = self.last_scan.get("actions", [])
        if actions:
            labels = ", ".join(ASSISTANT_ACTIONS[action]["label"] for action in actions if action in ASSISTANT_ACTIONS)
            lines.append(f"I can start these after you approve: {labels}.")
        return "\n".join(lines)

    def explain_performance_term(self, lower_prompt: str) -> str:
        if "gpu" in lower_prompt:
            return "A GPU handles graphics and some compute work. High GPU usage is normal in games, rendering, or video work; unexpected high usage can come from overlays, browsers, recorders, or background apps."
        if "cpu" in lower_prompt:
            return "A CPU runs general app and system work. High CPU usage can make the whole PC feel slow, especially if one process is stuck or startup apps are busy."
        if "ram" in lower_prompt or "memory" in lower_prompt:
            return "RAM is short-term working memory. When it gets full, Windows uses the disk more, which can cause stutter and slow switching between apps."
        if "power plan" in lower_prompt:
            return "A Windows power plan controls how aggressively the CPU boosts and saves power. Balanced is usually fine, but High or Ultimate Performance can improve responsiveness while plugged in."
        if "cache" in lower_prompt:
            return "Caches are temporary files used to speed things up. They are normal, but large or stale caches can waste storage and sometimes cause update or app issues."
        return "I can explain PC performance terms like CPU, GPU, RAM, VRAM, cache, startup apps, power plans, and bottlenecks."

    def confirm_scan(self) -> None:
        if self.scanning:
            self.append_assistant("A scan is already running.")
            return
        if not self.app.require_windows("AI Performance Scan"):
            return

        accepted = mb.askyesno(
            "AI Performance Scan",
            (
                "Run a read-only performance scan?\n\n"
                "I will check drive free space, temp/cache sizes, CPU load, GPU details/usage when available, "
                "active power plan, memory pressure, startup entries, uptime, and the largest visible memory users.\n\n"
                "No files will be deleted and no settings will be changed."
            ),
            parent=self.window,
        )
        if not accepted:
            self.append_system("Scan denied. No diagnostics were read.")
            return

        self.append_system("Scan accepted. Reading diagnostics only.")
        self.set_scanning(True)
        threading.Thread(target=self.scan_worker, daemon=True).start()

    def scan_worker(self) -> None:
        try:
            result = build_performance_scan()
        except Exception as exc:
            self.post_ui(lambda exc=exc: self.scan_failed(exc))
            return
        self.post_ui(lambda: self.scan_finished(result))

    def post_ui(self, callback) -> None:
        try:
            self.window.after(0, callback)
        except tk.TclError:
            pass

    def scan_failed(self, exc: Exception) -> None:
        self.set_scanning(False)
        self.append_assistant(f"Scan failed: {exc}")

    def scan_finished(self, result) -> None:
        self.last_scan = result
        self.set_scanning(False)
        self.append_assistant(self.format_scan_report(result))
        self.app.write(f"> AI Performance scan complete. Findings: {len(result.get('findings', []))}")
        self.update_fix_button()

    def format_scan_report(self, result) -> str:
        lines = [
            "I scanned storage, temp/cache folders, CPU load, GPU details/usage when available, memory pressure, the power plan, startup entries, uptime, and high-memory processes."
        ]
        for finding in result.get("findings", []):
            lines.append("")
            lines.append(f"[{finding.get('severity', 'info').upper()}] {finding.get('title', 'Finding')}")
            lines.append(f"  {finding.get('detail', '')}")
            if finding.get("fix"):
                lines.append(f"  Fix: {finding['fix']}")

        actions = result.get("actions", [])
        if actions:
            labels = ", ".join(ASSISTANT_ACTIONS[action]["label"] for action in actions if action in ASSISTANT_ACTIONS)
            lines.append("")
            lines.append(f"Recommended actions I can start after you approve: {labels}.")
        else:
            lines.append("")
            lines.append("No automatic optimizer action is required from this scan.")
        return "\n".join(lines)

    def on_apply_recommended(self) -> None:
        if not self.last_scan:
            self.append_assistant("I need a scan before I can recommend fixes.")
            self.confirm_scan()
            return
        self.confirm_and_apply_actions(self.last_scan.get("actions", []))

    def confirm_and_apply_actions(self, action_keys) -> None:
        actions = []
        for action_key in action_keys:
            if action_key in ASSISTANT_ACTIONS and action_key not in actions:
                actions.append(action_key)

        if not actions:
            self.append_assistant("I do not have an automatic optimizer action for that yet. I can still scan and explain what to fix manually.")
            return

        lines = ["The AI assistant will do the following:"]
        for action_key in actions:
            action = ASSISTANT_ACTIONS[action_key]
            lines.append(f"- {action['label']}: {action['description']}")
        lines.append("")
        lines.append("Continue?")

        accepted = mb.askyesno("Apply AI Recommendation", "\n".join(lines), icon=mb.WARNING, parent=self.window)
        if not accepted:
            self.append_system("Fix denied. No optimizer action was started.")
            return

        self.append_system("Fix accepted. Starting approved action(s).")
        runnable = [key for key in actions if key in ("optimize_clean", "performance_boost", "aggressive_cleanup", "clear_ram", "component_cleanup")]
        open_actions = [key for key in actions if key in ("storage_manager", "startup_settings")]
        if runnable:
            self.app.start_ai_fix_plan(runnable)
        for action_key in open_actions:
            self.app.apply_ai_open_action(action_key)

    def close(self) -> None:
        if getattr(self.app, "ai_assistant", None) is self:
            self.app.ai_assistant = None
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class PCOptimizerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.storage_manager = None
        self.ai_assistant = None
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

        self.btn_ai = tk.Button(
            adv_frame,
            text="AI Assistant",
            command=self.open_ai_assistant,
            bg="#111",
            fg=FG,
            activebackground="#1a1a1a",
            activeforeground=FG,
            font=FONT,
            relief=tk.FLAT,
            padx=10,
            pady=6,
        )
        self.btn_ai.pack(side=tk.LEFT)

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
        self.btn_aggressive.pack(side=tk.LEFT, padx=(8, 0))

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
        self.btn_ai.configure(state=state)
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

    def start_ai_fix_plan(self, action_keys) -> None:
        runnable = [
            key
            for key in action_keys
            if key in ("optimize_clean", "performance_boost", "aggressive_cleanup", "clear_ram", "component_cleanup")
        ]
        if not runnable:
            return
        threading.Thread(target=self.run_ai_fix_plan, args=(runnable,), daemon=True).start()

    def run_ai_fix_plan(self, action_keys) -> None:
        labels = [ASSISTANT_ACTIONS[key]["label"] for key in action_keys if key in ASSISTANT_ACTIONS]
        self.write(f"> AI Assistant approved fix plan: {', '.join(labels)}")
        for action_key in action_keys:
            try:
                if action_key == "optimize_clean":
                    self.optimize_clean()
                elif action_key == "performance_boost":
                    self.performance_boost()
                elif action_key == "aggressive_cleanup":
                    self.aggressive_cleanup(confirm=False)
                elif action_key == "clear_ram":
                    self.clear_ram_cache()
                elif action_key == "component_cleanup":
                    self.component_cleanup(confirm=False)
            except Exception as exc:
                label = ASSISTANT_ACTIONS.get(action_key, {}).get("label", action_key)
                self.write(f"[!] AI action failed ({label}): {exc}")
        self.write("> AI Assistant fix plan finished.")

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

    def open_ai_assistant(self) -> None:
        if self.ai_assistant:
            try:
                if self.ai_assistant.window.winfo_exists():
                    self.ai_assistant.window.lift()
                    self.ai_assistant.window.focus_force()
                    return
            except tk.TclError:
                self.ai_assistant = None
        self.ai_assistant = AIAssistantWindow(self)

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

    def open_startup_settings(self) -> None:
        if not self.require_windows("Startup Apps settings"):
            return
        try:
            subprocess.run(["explorer", "ms-settings:startupapps"], check=False)
            self.write("> Opened Startup Apps settings.")
        except Exception as e:
            self.write(f"[!] Could not open Startup Apps settings: {e}")

    def apply_ai_open_action(self, action_key: str) -> None:
        if action_key == "storage_manager":
            self.open_storage_manager()
        elif action_key == "startup_settings":
            self.open_startup_settings()

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

    def aggressive_cleanup(self, confirm: bool = True) -> None:
        if not self.require_windows("Aggressive Clean"):
            return
        if confirm and not mb.askyesno(
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

    def component_cleanup(self, confirm: bool = True) -> None:
        if not self.require_windows("Component Cleanup"):
            return
        if confirm and not mb.askyesno(
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
