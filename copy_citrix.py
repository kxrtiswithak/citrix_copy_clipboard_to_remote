from pynput.keyboard import Key, Controller
import pyperclip as clipboard
import time

keyboard = Controller() # To simulate keyboard key presses
clipboard = clipboard.paste() # Get clipboard information

time.sleep(5) # Wait 5 seconds
for letter in str(clipboard):
    if letter == '\r':
        continue  # Skip carriage return, handle newline with \n
    elif letter == '\n':
        keyboard.press(Key.enter)
        keyboard.release(Key.enter)
    else:
        keyboard.press(letter)
        keyboard.release(letter)
    time.sleep(0.005) # Wait some miliseconds between key presses for better performance
