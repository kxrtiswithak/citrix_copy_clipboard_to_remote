# citrix_copy_clipboard_to_remote

Reliable simulated typing from host clipboard into a target Citrix/VPN window.

## OS Caveat

This project is designed for **Windows only**.
It relies on Windows APIs and Windows keyboard behavior. Other OSes are not supported.

## Default Usage

This command is the baseline:

```powershell
python copy_citrix.py --mode type-reliable --reliable-key-delay 0.012 --reliable-chunk-size 180
```

`python copy_citrix.py` runs the same reliable mode with the same defaults.

## Window Title Targeting

Focus is matched by title substring.

- Default window title match: `VCSe Production`
- Override example:

```powershell
python copy_citrix.py --window-title "My Citrix Desktop"
```

## Flag Overrides and Impact

- `--reliable-key-delay <seconds>`
  - Lower value: faster typing, higher corruption risk on long text.
  - Higher value: slower typing, better stability.
- `--reliable-chunk-size <chars>`
  - Higher value: fewer pauses, faster throughput, more risk in unstable sessions.
  - Lower value: more pauses, safer long runs.
- `--reliable-chunk-pause <seconds>`
  - Extra pause between chunks to let remote session catch up.
- `--refocus-each-chunk`
  - Re-checks and restores target focus after every chunk.
- `--window-title "<text>"`
  - Changes which window is targeted for typing.
- `--skip-focus`
  - Types into whichever window is currently active.
- `--no-gui`
  - Runs in terminal mode instead of the progress dialog.

## GitHub Actions: Zero-Dependency Binary

This repo now includes:

- `.github/workflows/build-windows-binary.yml`

It builds a single-file Windows executable (`copy-citrix.exe`) using PyInstaller.

How to use:

1. Push to `main` or run the workflow manually from GitHub Actions (`workflow_dispatch`).
2. Open the completed workflow run.
3. Download artifact `copy-citrix-windows`.
4. Use `copy-citrix.exe` directly on Windows without installing Python/pip dependencies.

## Windows Shortcut + Hotkey Setup

You can run with one keyboard shortcut.

1. Put `copy-citrix.exe` somewhere stable, e.g. `C:\Tools\copy-citrix.exe`.
2. Right click Desktop -> New -> Shortcut.
3. Set target to:
```text
"C:\Tools\copy-citrix.exe"
```
4. Open shortcut Properties.
5. Set a value in `Shortcut key`, e.g. `Ctrl+Alt+V`.
6. Optional: set `Run` to `Minimized`.
7. Apply and use that hotkey globally.

If you prefer script instead of EXE, target example:

```text
"C:\Path\to\pythonw.exe" "C:\Path\to\copy_citrix.py"
```
