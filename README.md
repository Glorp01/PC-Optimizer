# PC Optimizer Panel

A small Windows utility with a terminal-style Tkinter UI for cleaning temporary files, trimming caches, and applying a simple performance-oriented power-plan tweak.

## Features
- Optimize & Clean: clears user temp files, Windows temp files where possible, Recent items, and the Recycle Bin.
- Boost Performance: switches to Ultimate Performance when available, otherwise High performance, and applies a CPU performance tweak on AC power.
- Aggressive Clean: attempts Windows Update cache, Delivery Optimization cache, thumbnail cache, WER cleanup, and Prefetch cleanup.
- Revert Boost: switches the system back to the Balanced power plan.
- Clear RAM Cache: best-effort working-set trim across running processes.
- Component Cleanup: runs `dism /Online /Cleanup-Image /StartComponentCleanup`.
- Live UI log: shows progress and any skipped operations while tasks run.

## Requirements
- Windows 10 or Windows 11
- Python 3.8+

## Run
```powershell
python main.py
```

If `python` is not on your `PATH`, run the script with your Python executable directly.

## Notes
- Some operations are best-effort and may skip locked files or protected system resources.
- A few actions may require Administrator privileges for full effect.
- Power-plan changes can be reverted from the app or through Windows Power Options.

## Optional: Create a Taskbar Shortcut
1. Create a desktop shortcut.
2. Set the target to `"<path-to-pythonw.exe>" "<path-to-project>\\main.py"`.
3. Rename it to something like `PC Optimizer`.
4. Pin the shortcut to the taskbar.
