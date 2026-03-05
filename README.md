# citrix_copy_clipboard_to_remote

Reliable simulated typing from host clipboard into a target Citrix/VPN window.

## Install

```powershell
pip install pyperclip pynput
```

## Default Behavior

The script is now locked to reliable typing mode by default.

This command is the baseline configuration:

```powershell
python copy_citrix.py --mode type-reliable --reliable-key-delay 0.012 --reliable-chunk-size 180
```

`python copy_citrix.py` also runs reliable typing with those defaults.

## Window Targeting

Focus is matched by window title substring:

- default: `VCSe Production`
- override with:

```powershell
python copy_citrix.py --window-title "Your Citrix/VPN Window Title"
```

## Tuning Overrides

Use these flags to trade off speed vs reliability:

- `--reliable-key-delay <seconds>`
  - lower: faster typing, higher garble risk
  - higher: slower typing, better stability
- `--reliable-chunk-size <chars>`
  - larger: fewer pauses, faster throughput, higher long-run risk
  - smaller: more frequent pauses, better long-run stability
- `--reliable-chunk-pause <seconds>`
  - lower: faster
  - higher: gives remote app time to catch up
- `--refocus-each-chunk`
  - checks/restores focus after every chunk
  - useful if focus occasionally drifts

Additional runtime controls:

- `--skip-focus` to type into current foreground window only
- `--no-gui` for terminal output instead of dialog/progress UI

## Example Stability Profiles

Fast (if your session is stable):

```powershell
python copy_citrix.py --reliable-key-delay 0.010 --reliable-chunk-size 220 --reliable-chunk-pause 0.05
```

Conservative (for long payloads/high latency):

```powershell
python copy_citrix.py --reliable-key-delay 0.020 --reliable-chunk-size 120 --reliable-chunk-pause 0.12 --refocus-each-chunk
```
