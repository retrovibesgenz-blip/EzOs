"""
example.py  -  a quick tour of ezos v2.

Run it with:  python example.py
Non-destructive (no deleting, no shutdown). A couple of lines open apps /
browser tabs - comment them out if you don't want that.
"""

import ezos

# --- files ---------------------------------------------------------------
ezos.create_file("hello.txt", "Hi from ezos!")
print(ezos.read_file("hello.txt"))

# --- system info ---------------------------------------------------------
print("Computer:", ezos.system_info()["computer_name"])
print("Wi-Fi   :", ezos.wifi_name())
print("Disk    :", ezos.disk_space())
print("Weather :", ezos.weather("New York"))

# --- clipboard -----------------------------------------------------------
ezos.copy_to_clipboard("ezos put this on the clipboard")
print("Clipboard says:", ezos.paste_from_clipboard())

# --- apps & web (these actually open things - comment out if you want) ---
ezos.open_app("notepad")                 # launches Notepad
# ezos.open_app("spotify")               # launches Spotify (Store app!)
# ezos.search_web("ezos python", browser="chrome")
# ezos.play_on_youtube("lofi hip hop")

# --- the AI dispatcher (how your Jarvis calls ezos) ----------------------
print("Via run():", ezos.run("current_time"))
print("Total commands your AI can call:", len(ezos.list_commands()))

# --- talk + notify -------------------------------------------------------
ezos.toast("Demo finished!", "ezos")     # non-blocking notification
# ezos.speak("Demo complete")

# clean up
ezos.close_app("notepad")
ezos.delete_file("hello.txt")
print("Done.")
