import argparse
import ctypes
from ctypes import wintypes
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import pyperclip
from pynput.keyboard import Key, Controller

SW_RESTORE = 9
SW_SHOW = 5
KEYEVENTF_KEYUP = 0x0002
VK_MENU = 0x12  # ALT key
VK_ESCAPE = 0x1B

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _find_windows_with_title(title_substring):
    matches = []
    needle = title_substring.lower()
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value
        if needle in title.lower():
            matches.append((hwnd, title))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return matches


def _resolve_target_hwnd(title_substring):
    matches = _find_windows_with_title(title_substring)
    if not matches:
        raise RuntimeError(f"No visible window found with title containing: {title_substring!r}")
    return matches[0][0]


def _focus_window_by_title(title_substring, timeout_seconds=3):
    matches = _find_windows_with_title(title_substring)
    if not matches:
        raise RuntimeError(f"No visible window found with title containing: {title_substring!r}")

    hwnd, full_title = matches[0]
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

        attached_foreground = False
        attached_target = False
        try:
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
            if target_thread and target_thread != current_thread:
                attached_target = bool(user32.AttachThreadInput(target_thread, current_thread, True))

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            if attached_target:
                user32.AttachThreadInput(target_thread, current_thread, False)
            if attached_foreground:
                user32.AttachThreadInput(foreground_thread, current_thread, False)

        if user32.GetForegroundWindow() == hwnd:
            # Prevent accidental menu accelerator state before typing.
            user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
            return full_title

        # Fallback for stricter foreground lock scenarios.
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() == hwnd:
            user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
            return full_title

        time.sleep(0.05)

    raise RuntimeError(f"Unable to focus window: {full_title!r}")


def _ensure_target_focus(title_substring):
    target_hwnd = _resolve_target_hwnd(title_substring)
    if user32.GetForegroundWindow() != target_hwnd:
        _focus_window_by_title(title_substring)


def _count_typeable_chars(text):
    return sum(1 for char in text if char != "\r")


def _send_ctrl_hotkey(keyboard, key_char):
    with keyboard.pressed(Key.ctrl):
        keyboard.press(key_char)
        keyboard.release(key_char)


def _select_all_and_copy(window_title, skip_focus, status_callback=None):
    if not skip_focus:
        _ensure_target_focus(window_title)

    keyboard = Controller()
    if status_callback is not None:
        status_callback("Selecting all and copying in target window...")
    _send_ctrl_hotkey(keyboard, "a")
    time.sleep(0.05)
    _send_ctrl_hotkey(keyboard, "c")
    time.sleep(0.05)


def _type_reliable_text(
    text,
    key_delay,
    chunk_size,
    chunk_pause,
    refocus_each_chunk,
    window_title,
    skip_focus,
    status_callback=None,
    progress_callback=None,
):
    keyboard = Controller()
    total = _count_typeable_chars(text)
    typed = 0
    chunk_typed = 0

    if progress_callback is not None:
        progress_callback(0, total)
    if status_callback is not None:
        status_callback("Simulating keypresses (reliable mode)...")

    for letter in text:
        if letter == "\r":
            continue
        if letter == "\n":
            keyboard.press(Key.enter)
            keyboard.release(Key.enter)
        else:
            keyboard.press(letter)
            keyboard.release(letter)

        typed += 1
        chunk_typed += 1
        if progress_callback is not None:
            progress_callback(typed, total)

        if key_delay > 0:
            time.sleep(key_delay)

        if chunk_typed >= chunk_size:
            if refocus_each_chunk and not skip_focus:
                if status_callback is not None:
                    status_callback(f"Checking focus at {typed}/{total}...")
                _ensure_target_focus(window_title)
                if status_callback is not None:
                    status_callback("Simulating keypresses (reliable mode)...")
            if chunk_pause > 0:
                time.sleep(chunk_pause)
            chunk_typed = 0

    if status_callback is not None:
        status_callback("Typing complete.")


def _run_transfer(args, status_callback=None, progress_callback=None):
    clip_text = pyperclip.paste()
    if not clip_text:
        raise RuntimeError("Clipboard is empty.")
    clip_text = str(clip_text)

    if not args.skip_focus:
        if status_callback is not None:
            status_callback(f"Focusing window matching '{args.window_title}'...")
        focused_title = _focus_window_by_title(args.window_title)
        if status_callback is not None:
            status_callback(f"Focused: {focused_title}")

    _type_reliable_text(
        text=clip_text,
        key_delay=args.reliable_key_delay,
        chunk_size=args.reliable_chunk_size,
        chunk_pause=args.reliable_chunk_pause,
        refocus_each_chunk=args.refocus_each_chunk,
        window_title=args.window_title,
        skip_focus=args.skip_focus,
        status_callback=status_callback,
        progress_callback=progress_callback,
    )

    if args.copy_after_type:
        _select_all_and_copy(
            window_title=args.window_title,
            skip_focus=args.skip_focus,
            status_callback=status_callback,
        )
    if status_callback is not None:
        status_callback("Completed.")


class ProgressDialog:
    def __init__(self, args):
        self.args = args
        self.events = queue.Queue()
        self.running = True

        self.root = tk.Tk()
        self.root.title("Clipboard Typing")
        self.root.geometry("460x180")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Preparing...")
        self.count_var = tk.StringVar(value="0 / 0 keypresses")

        ttk.Label(frame, text="Status").pack(anchor="w")
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w", pady=(2, 10))
        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate", maximum=1, value=0)
        self.progress.pack(fill="x")
        ttk.Label(frame, textvariable=self.count_var).pack(anchor="w", pady=(8, 0))

        self.close_btn = ttk.Button(frame, text="Close", command=self._on_close, state="disabled")
        self.close_btn.pack(anchor="e", pady=(16, 0))

    def start(self):
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        self.root.after(50, self._drain_events)
        self.root.mainloop()

    def _worker(self):
        try:
            _run_transfer(
                self.args,
                status_callback=lambda status: self.events.put(("status", status)),
                progress_callback=lambda current, total: self.events.put(("progress", current, total)),
            )
            self.events.put(("done",))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "status":
                self.status_var.set(event[1])
            elif kind == "progress":
                current, total = event[1], max(event[2], 1)
                self.progress.configure(maximum=total)
                self.progress["value"] = current
                self.count_var.set(f"{current} / {event[2]} keypresses")
            elif kind == "done":
                self.running = False
                self.close_btn.configure(state="normal")
            elif kind == "error":
                self.running = False
                self.status_var.set("Failed.")
                self.close_btn.configure(state="normal")
                messagebox.showerror("Typing Failed", event[1])

        if self.running:
            self.root.after(50, self._drain_events)

    def _on_close(self):
        if self.running:
            messagebox.showinfo("In Progress", "Typing is still running.")
            return
        self.root.destroy()


def _run_cli(args):
    def _status(text):
        print(text)

    def _progress(current, total):
        print(f"Progress: {current}/{total}", end="\r", flush=True)

    _run_transfer(args, status_callback=_status, progress_callback=_progress)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Send clipboard text into a target window using reliable simulated typing."
    )
    parser.add_argument(
        "--mode",
        choices=["type-reliable"],
        default="type-reliable",
        help="Compatibility flag. Only reliable typing mode is supported.",
    )
    parser.add_argument(
        "--reliable-key-delay",
        type=float,
        default=0.012,
        help="Delay between keypresses (seconds). Increase to improve reliability.",
    )
    parser.add_argument(
        "--reliable-chunk-size",
        type=int,
        default=180,
        help="Characters typed before pausing briefly.",
    )
    parser.add_argument(
        "--reliable-chunk-pause",
        type=float,
        default=0.08,
        help="Pause between chunks (seconds). Increase for unstable sessions.",
    )
    parser.add_argument(
        "--refocus-each-chunk",
        action="store_true",
        help="Re-check and restore focus after each chunk.",
    )
    parser.add_argument(
        "--window-title",
        default="VCSe Production",
        help="Window title substring used to find and focus the target app.",
    )
    parser.add_argument(
        "--skip-focus",
        action="store_true",
        help="Skip focusing and type into whichever window is active.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in terminal mode without the progress dialog.",
    )
    parser.add_argument(
        "--copy-after-type",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="After typing, send Ctrl+A then Ctrl+C in the target window (enabled by default).",
    )

    args = parser.parse_args()
    if args.reliable_chunk_size < 1:
        parser.error("--reliable-chunk-size must be greater than 0.")

    if args.no_gui:
        _run_cli(args)
    else:
        ProgressDialog(args).start()


if __name__ == "__main__":
    main()
