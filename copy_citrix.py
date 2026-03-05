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
            # Ensure we are not in menu-accelerator mode before typing.
            user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
            return full_title

        # Fallback for stricter foreground lock cases.
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


def _count_typeable_chars(text):
    return sum(1 for char in text if char != "\r")


def _normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _text_matches(expected, actual, strict_verify):
    if strict_verify:
        return expected == actual
    return _normalize_newlines(expected) == _normalize_newlines(actual)


def _ctrl_hotkey(keyboard, key_char):
    with keyboard.pressed(Key.ctrl):
        keyboard.press(key_char)
        keyboard.release(key_char)


def _clear_target_buffer(keyboard, settle_delay):
    _ctrl_hotkey(keyboard, "a")
    time.sleep(settle_delay)
    keyboard.press(Key.backspace)
    keyboard.release(Key.backspace)
    time.sleep(settle_delay)


def _capture_selected_text(keyboard, copy_timeout, settle_delay):
    sentinel = f"__clipboard_sync_{time.time_ns()}__"
    pyperclip.copy(sentinel)
    time.sleep(settle_delay)
    _ctrl_hotkey(keyboard, "a")
    time.sleep(settle_delay)
    _ctrl_hotkey(keyboard, "c")

    deadline = time.time() + copy_timeout
    while time.time() < deadline:
        current = str(pyperclip.paste())
        if current != sentinel:
            return current
        time.sleep(0.02)
    raise RuntimeError("Timed out while waiting for copied text from target window.")


def _chunk_count(text_length, chunk_size):
    return max(1, (text_length + chunk_size - 1) // chunk_size)


def _paste_text_in_chunks(
    text,
    keyboard,
    chunk_size,
    chunk_delay,
    clipboard_settle_delay,
    status_callback=None,
    progress_callback=None,
):
    if chunk_size <= 0:
        raise RuntimeError("chunk_size must be greater than 0.")

    total = len(text)
    if progress_callback is not None:
        progress_callback(0, total)

    if total == 0:
        return

    total_chunks = _chunk_count(total, chunk_size)
    pasted = 0
    for chunk_index, start in enumerate(range(0, total, chunk_size), start=1):
        if status_callback is not None:
            status_callback(f"Pasting chunk {chunk_index}/{total_chunks}...")
        chunk = text[start : start + chunk_size]
        pyperclip.copy(chunk)
        time.sleep(clipboard_settle_delay)
        _ctrl_hotkey(keyboard, "v")
        pasted += len(chunk)
        if progress_callback is not None:
            progress_callback(pasted, total)
        if chunk_delay > 0:
            time.sleep(chunk_delay)


def _type_clipboard_text(text, key_delay, progress_callback=None):
    keyboard = Controller()
    total = _count_typeable_chars(text)
    typed = 0
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
        if progress_callback is not None:
            progress_callback(typed, total)
        time.sleep(key_delay)


def _run_typing_mode(text, key_delay, status_callback=None, progress_callback=None):
    if status_callback is not None:
        status_callback("Simulating keypresses (type mode)...")
    _type_clipboard_text(text, key_delay, progress_callback=progress_callback)
    if status_callback is not None:
        status_callback("Completed.")


def _run_paste_mode(text, args, status_callback=None, progress_callback=None):
    keyboard = Controller()

    verify_enabled = args.mode == "paste-verify"
    attempts = args.verify_attempts if verify_enabled else 1
    expected_text = str(text)

    original_clipboard = pyperclip.paste()
    try:
        for attempt in range(1, attempts + 1):
            if verify_enabled and status_callback is not None:
                status_callback(f"Reliable mode attempt {attempt}/{attempts}...")

            if verify_enabled or args.clear_before_paste:
                if status_callback is not None:
                    status_callback("Clearing target buffer...")
                _clear_target_buffer(keyboard, args.hotkey_settle_delay)

            _paste_text_in_chunks(
                expected_text,
                keyboard,
                chunk_size=args.chunk_size,
                chunk_delay=args.chunk_delay,
                clipboard_settle_delay=args.clipboard_settle_delay,
                status_callback=status_callback,
                progress_callback=progress_callback,
            )

            if not verify_enabled:
                if status_callback is not None:
                    status_callback("Completed.")
                return

            if status_callback is not None:
                status_callback("Verifying pasted content...")
            captured = _capture_selected_text(
                keyboard,
                copy_timeout=args.copy_timeout,
                settle_delay=args.hotkey_settle_delay,
            )
            if _text_matches(expected_text, captured, args.strict_verify):
                if status_callback is not None:
                    status_callback(f"Completed. Verified on attempt {attempt}.")
                return

            if status_callback is not None and attempt < attempts:
                status_callback("Verification mismatch. Retrying...")

        raise RuntimeError(
            "Verification failed after all attempts. Increase delays/chunking or use dedicated target input."
        )
    finally:
        pyperclip.copy(original_clipboard)


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

    if args.mode == "type":
        total = _count_typeable_chars(clip_text)
        if progress_callback is not None:
            progress_callback(0, total)
        _run_typing_mode(clip_text, args.key_delay, status_callback=status_callback, progress_callback=progress_callback)
        return

    _run_paste_mode(clip_text, args, status_callback=status_callback, progress_callback=progress_callback)


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
        self.count_var = tk.StringVar(value="0 / 0 units")

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
                self.count_var.set(f"{current} / {event[2]} units")
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
        description="Send clipboard text into a target window using typing or reliable paste modes."
    )
    parser.add_argument(
        "--mode",
        choices=["type", "paste", "paste-verify"],
        default="type",
        help="Input mode: key-by-key typing, chunked paste, or chunked paste with verification/retries.",
    )
    parser.add_argument(
        "--key-delay",
        type=float,
        default=0.005,
        help="Delay in seconds between simulated key presses.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Characters per chunk for paste modes.",
    )
    parser.add_argument(
        "--chunk-delay",
        type=float,
        default=0.03,
        help="Delay between chunk pastes for paste modes.",
    )
    parser.add_argument(
        "--clipboard-settle-delay",
        type=float,
        default=0.03,
        help="Delay after writing each chunk to clipboard before Ctrl+V.",
    )
    parser.add_argument(
        "--hotkey-settle-delay",
        type=float,
        default=0.05,
        help="Delay after Ctrl+A/C style hotkeys in paste-verify mode.",
    )
    parser.add_argument(
        "--copy-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait for Ctrl+C read-back in paste-verify mode.",
    )
    parser.add_argument(
        "--verify-attempts",
        type=int,
        default=3,
        help="Number of full paste+verify attempts in paste-verify mode.",
    )
    parser.add_argument(
        "--strict-verify",
        action="store_true",
        help="Require exact match for verification (default normalizes newline style only).",
    )
    parser.add_argument(
        "--clear-before-paste",
        action="store_true",
        help="Clear target text before pasting in plain paste mode.",
    )
    parser.add_argument(
        "--window-title",
        default="VCSe Production",
        help="Window title substring used to find and focus the target app.",
    )
    parser.add_argument(
        "--skip-focus",
        action="store_true",
        help="Skip window focusing and type into the current foreground window.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in terminal mode without the progress dialog.",
    )
    args = parser.parse_args()
    if args.chunk_size < 1:
        parser.error("--chunk-size must be greater than 0.")
    if args.verify_attempts < 1:
        parser.error("--verify-attempts must be greater than 0.")

    if args.no_gui:
        _run_cli(args)
    else:
        ProgressDialog(args).start()


if __name__ == "__main__":
    main()
