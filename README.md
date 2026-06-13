# PC Optimizer Panel

A small Windows utility with a terminal-style Tkinter UI for cleaning temporary files, trimming caches, and applying a simple performance-oriented power-plan tweak.

## Features
- Optimize & Clean: clears user temp files, Windows temp files where possible, Recent items, and the Recycle Bin.
- Boost Performance: switches to Ultimate Performance when available, otherwise High performance, and applies a CPU performance tweak on AC power.
- Aggressive Clean: attempts Windows Update cache, Delivery Optimization cache, thumbnail cache, WER cleanup, and Prefetch cleanup.
- Revert Boost: switches the system back to the Balanced power plan.
- Clear RAM Cache: best-effort working-set trim across running processes.
- Component Cleanup: runs `dism /Online /Cleanup-Image /StartComponentCleanup`.
- Storage Manager: select a drive, scan folder contents, sort largest to smallest, drill into folders, open locations, and move selected items to the Recycle Bin.
- AI Assistant: ask performance questions, run a read-only diagnostic scan, review likely bottlenecks, and approve or deny recommended optimizer actions. It answers from local diagnostics by default and can use online AI when `OPENAI_API_KEY` is set; override the model with `PC_OPTIMIZER_AI_MODEL`.
- Update App: checks the latest GitHub Release, downloads the newest Windows installer, and launches it.
- Live UI log: shows progress and any skipped operations while tasks run.

## Requirements
- Windows 10 or Windows 11
- Python 3.8+

## Download
The recommended Windows download is the installer:
- `PCOptimizer-Windows-Setup.exe`

There is also a portable Windows zip:
- `PCOptimizer-Windows-Portable.zip`

The GitHub workflow also builds a basic macOS app zip, but the cleanup and performance actions are Windows-only.

## Run From Source
Use the no-console launcher when opening the app locally:
```powershell
pythonw pc_optimizer.pyw
```

You can also double-click `pc_optimizer.pyw` if Python is installed and associated with `.pyw` files.

Running this command is still useful for debugging, but it keeps a terminal window open behind the app:
```powershell
python main.py
```

If `python` is not on your `PATH`, run the script with your Python executable directly.

## Build Windows Downloads Locally
Install Python, then run:
```powershell
.\scripts\build_windows.ps1
```

This creates:
- `dist\PCOptimizer.exe`
- `dist\PCOptimizer-Windows-Portable.zip`

To build the Windows installer too, install Inno Setup 6 and run this from the repo root:
```powershell
iscc installer\windows\PCOptimizer.iss
```

The installer output is:
- `dist\installer\PCOptimizer-Windows-Setup.exe`

## Publish Downloads On GitHub
Push this repository to GitHub with the included workflow. Every push to `main` or `master` creates downloadable build artifacts under the workflow run.

To create a public GitHub Release with the installer and zip files attached, push a version tag:
```powershell
git tag v0.1.0
git push origin v0.1.0
```

After the workflow finishes, the files will be attached to the `v0.1.0` release.

## In-App Updates
Installed Windows copies include an `Update App` button. It checks the latest GitHub Release for `PCOptimizer-Windows-Setup.exe`; if the release tag is newer than the installed version, it downloads the installer, applies it silently in the background, closes PC Optimizer, and relaunches it when the update finishes.

The button fades when the installed version is current and switches to a brighter update style when a newer release is available.

Each PC updates itself when the user presses the button. GitHub cannot force-update already installed copies remotely, and versions installed before the updater was added need one manual install of the newer release first.

## Notes
- Some operations are best-effort and may skip locked files or protected system resources.
- A few actions may require Administrator privileges for full effect.
- The Windows build is not code-signed, so Windows SmartScreen may warn the first time it is downloaded.
- Power-plan changes can be reverted from the app or through Windows Power Options.

## Optional: Create a Taskbar Shortcut
1. Create a desktop shortcut.
2. Set the target to `"<path-to-pythonw.exe>" "<path-to-project>\\pc_optimizer.pyw"`.
3. Rename it to something like `PC Optimizer`.
4. Pin the shortcut to the taskbar.
