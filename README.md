# citrix_copy_clipboard_to_remote

Reliable simulated typing from host clipboard into a target Citrix/VPN window.

## OS Caveat

This project is designed for **Windows only**.
It relies on Windows APIs and Windows keyboard behavior. Other OSes are not supported.

## Requirements and Setup

This repo includes `requirements.txt` for runtime dependencies.

Install with:

```powershell
python -m pip install -r requirements.txt
```

Run with:

```powershell
python copy_citrix.py
```

## Default Behavior

Default run is equivalent to:

```powershell
python copy_citrix.py --mode type-reliable --reliable-key-delay 0.012 --reliable-chunk-size 180 --copy-after-type
```

What it does by default:

1. Focuses the target window by title match.
2. Types clipboard text using reliable chunked keypress simulation.
3. Sends `Ctrl+A` then `Ctrl+C` inside the target window to place the typed content into the session clipboard.

Disable step 3 with:

```powershell
python copy_citrix.py --no-copy-after-type
```

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
- `--copy-after-type` / `--no-copy-after-type`
  - Enable or disable the default post-typing `Ctrl+A` + `Ctrl+C` step.
- `--window-title "<text>"`
  - Changes which window is targeted for typing.
- `--skip-focus`
  - Types into whichever window is currently active.
- `--no-gui`
  - Runs in terminal mode instead of the progress dialog.

## Suggested Workflow (Citrix Notepad)

1. In the Citrix session, open Notepad (or another plain text editor) and place cursor in the document.
2. On host Windows, copy the source text to clipboard.
3. Trigger `copy_citrix.py` (terminal, shortcut, or hotkey).
4. Let it complete without changing focus.
5. Paste from session clipboard where needed in Citrix.

Using Notepad as the initial landing area is recommended for reliability and easy visual verification.

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
5. Set `Shortcut key` to `Ctrl+Alt+V` (recommended).
6. Optional: set `Run` to `Minimized`.
7. Apply and use that hotkey globally.

Note: `Alt` is typically handled by the host OS even while Citrix is focused, so `Ctrl+Alt+V` usually triggers the host shortcut reliably whether focus is inside or outside the Citrix window.

If you prefer script instead of EXE, target example:

```text
"C:\Path\to\pythonw.exe" "C:\Path\to\copy_citrix.py"
```
