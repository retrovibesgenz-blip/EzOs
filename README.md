<div align="center">

# 🖥️ ezos — Easy OS

### Control your Windows PC with one-line Python. Build your own Jarvis.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/core%20deps-0-brightgreen.svg)](#-install)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-ff69b4.svg)](#-contributing)

**`ezos`** is a single-file Python library that gives an AI (or you) a simple,
reliable toolbox to drive the operating system — open apps, control the browser,
research the web, manage files, control media, and more — with dead-simple
functions that read like plain English.                  You can check our official website on https://ezos.bytovex.app

```python
import ezos

ezos.open_app("spotify")                 # launches Spotify (Store app!)
ezos.play_on_youtube("lofi hip hop")     # finds + opens the first video
ezos.search_web("weather", browser="chrome")
print(ezos.weather("London"))            # "London: Overcast +12C, 84% humidity"
ezos.speak("All systems online, boss.")
```

</div>

---

## ✨ Why ezos?

When you point an AI at a computer, it needs **simple, predictable verbs** — not
40 lines of `subprocess` / `ctypes` / Win32 boilerplate per task. `ezos` gives it
**85 of them**, each named like plain English, each returning a structured result
so the AI always knows what happened.

- 🎯 **It actually works.** App launching uses Windows' own `Get-StartApps`
  resolver, so Store apps (Spotify, ChatGPT) *and* desktop apps (Zoom, Discord)
  really launch — not just the ones on your PATH.
- 📦 **Zero dependencies for the core.** Launching, browser, media keys, window
  control, volume, weather, clipboard, speak — all work on a plain Python install.
- 🤖 **Built for AI.** Ships OpenAI-compatible + Claude tool formats, a config
  builder, and a ready-made `Jarvis` agent loop. Works with OpenAI, **Gemini**,
  **Z.ai**, Groq, and any OpenAI-format API.
- 🔎 **Real web research** with DuckDuckGo + BeautifulSoup — your AI can *find
  things out*, not just open a search page.
- 😌 **Readable both ways.** `ezos.open_app()` and `ezos.openApp()` both work.

---

## 📦 Install

```bash
git clone https://github.com/<your-username>/ezos.git
cd ezos
pip install -r requirements.txt     # optional extras; the core needs nothing
```

Or just drop **`ezos.py`** next to your script and `import ezos`.

| Package | Unlocks |
|---|---|
| *(nothing)* | app launch, browser, media, windows, volume, weather, clipboard, speak… |
| `ddgs` + `beautifulsoup4` | `web_search`, `read_webpage`, `research` |
| `openai` | real-AI Jarvis mode (works with OpenAI/Gemini/Z.ai/Groq) |
| `psutil` | `cpu_usage`, `ram_usage`, `battery_status` |
| `pyautogui` | `click`, `move_mouse`, `scroll` |
| `pycaw` + `comtypes` | `set_volume` to an exact level |

---

## 🚀 Quick start

```python
import ezos

# files
ezos.create_file("notes.txt", "hello world")
print(ezos.read_file("notes.txt"))

# apps & web
ezos.open_app("discord")
ezos.search_web("python tips", browser="chrome")

# system
print(ezos.system_info())
print(ezos.weather("Tokyo"))
ezos.volume_up(10)

# talk & notify
ezos.speak("Task complete")
ezos.reminder(600, "Take a break")       # pops + speaks in 10 min
```

Every action returns a structured result, so you always know what happened:

```python
ezos.open_app("spotify")
# -> {"ok": True,  "message": "Opened 'Spotify'", "resolved": "Spotify"}
ezos.open_app("notarealapp")
# -> {"ok": False, "message": "Could not find an app called 'notarealapp'. ..."}
#    (also prints a visible  WARNING ezos: ...  so failures aren't silent)
```

---

## 🤖 Build your own Jarvis

`ezos` is the **toolbox**; your LLM is the **brain**. It works with any
**OpenAI-compatible** provider — OpenAI, **Google Gemini**, **Z.ai**, Groq,
Together, OpenRouter, local servers — just point the client's `base_url` at them.

### 1. Configure the AI

`aiRead()` makes one instruction block. Stack as many as you like and feed them to
`configure()`, which also tells the AI *which tools it has, with an instruction for
each*.

```python
import ezos

cfg = ezos.configure(
    ezos.aiRead("Call me 'boss'."),
    ezos.aiRead("Prefer Chrome for browsing."),
    ezos.aiRead("Research before answering factual questions."),
    provider="openai",
)
cfg["system_prompt"]   # -> system message for your LLM
cfg["tools"]           # -> tools in the OpenAI-compatible format
```

### 2. Use the ready-made `Jarvis` loop

```python
from openai import OpenAI
import ezos

# Google Gemini (via the OpenAI-compatible endpoint)
client = OpenAI(
    api_key="YOUR_GEMINI_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

jarvis = ezos.Jarvis(client, model="gemini-2.0-flash", instructions=[
    ezos.aiRead("Call me boss."),
    ezos.aiRead("Prefer Chrome."),
])

jarvis.chat("open spotify and search lofi on youtube")
jarvis.chat("what's the weather in Tokyo and who won the last F1 race?")
```

### 3. Or do raw tool-calling

```python
tools = ezos.openai_tools()           # or ezos.anthropic_tools() for Claude
resp = client.chat.completions.create(model=..., tools=tools, messages=[...])
msg = resp.choices[0].message
if msg.tool_calls:
    messages.append(msg)
    messages += ezos.handle_openai_tool_calls(msg.tool_calls)   # ezos runs them
```

> 💡 A complete, runnable chatbot is in **[`test.py`](test.py)** (Gemini) and
> **[`jarvis_demo.py`](jarvis_demo.py)** (any provider, with an offline keyword
> fallback that needs no API key).

---

## 🔎 Web research (no API key)

```python
ezos.web_search("who won the match today")       # -> [{title, url, snippet}, ...]
ezos.read_webpage("https://en.wikipedia.org/wiki/Mars")   # clean text
info = ezos.research("python 3.13 new features")  # search + read top pages
print(info["summary"])                            # feed straight to your AI
```

---

## 📚 The 85 commands

Open **[`index.html`](index.html)** in a browser for a searchable reference with
an example for every function. Categories:

| Category | Examples |
|---|---|
| **Files & Folders** (17) | `create_file`, `read_file`, `copy_file`, `zip_files`, `find_file`, `open_folder` |
| **Apps & Processes** (5) | `open_app`, `close_app`, `is_app_running`, `run_command` |
| **Browser & Web** (9) | `open_browser`, `search_web`, `open_website`, `weather`, `download_file` |
| **Media** (6) | `play_on_youtube`, `play_on_spotify`, `play_pause_media`, `next_track` |
| **Web Research** (3) | `web_search`, `read_webpage`, `research` |
| **System Info** (9) | `system_info`, `cpu_usage`, `ram_usage`, `disk_space`, `wifi_name` |
| **System Control** (7) | `shutdown`, `restart`, `lock_screen`, `sleep_pc`, `set_brightness` |
| **Window Management** (6) | `minimize_window`, `maximize_window`, `show_desktop`, `switch_window` |
| **Clipboard** (2) | `copy_to_clipboard`, `paste_from_clipboard` |
| **Sound & Wallpaper** (6) | `volume_up`, `mute`, `set_volume`, `screenshot`, `set_wallpaper` |
| **Keyboard & Mouse** (6) | `type_text`, `press_key`, `hotkey`, `click`, `scroll` |
| **Extras** (9) | `notify`, `toast`, `speak`, `reminder`, `set_timer`, `whatsapp_message` |
| **AI Integration** | `aiRead`, `configure`, `openai_tools`, `run`, `Jarvis`, … |

See everything at runtime:

```python
ezos.help_me()            # printed overview
ezos.list_commands()      # list of names
ezos.describe_commands()  # name + params + doc (great for feeding an LLM)
```

---

## 🛠️ How it works

- **App launching** uses `Get-StartApps` + `explorer.exe shell:AppsFolder\<AppID>`,
  which resolves *any* Start-menu app (Store or desktop), not just PATH entries.
- **Browser** finds the real `chrome.exe` / `msedge.exe` / `firefox.exe` so the
  URL opens in the browser you ask for.
- **Media keys, window control, volume** use `ctypes` — no third-party deps.
- **Web/weather** use the standard-library `urllib`; **research** adds DDGS + BS4.

---

## ⚠️ Safety

- Built and tested on **Windows 11**. File/web helpers also work on macOS/Linux;
  app-launch / volume / window / wallpaper helpers are Windows-first.
- Destructive verbs (`delete_file`, `delete_folder`, `shutdown`,
  `empty_recycle_bin`) do exactly what they say — have your AI confirm before
  calling them. `whatsapp_message` only *opens* the chat; you press Send.

---

## 🤝 Contributing

Contributions are welcome! To add a command:

1. Write a function in `ezos.py` that returns `_ok(...)` / `_fail(...)`.
2. Add a `camelCase` alias in the aliases block.
3. Add an entry to `index.html` so it shows in the docs.
4. Open a PR. 🎉

Found a bug or want a feature? [Open an issue](../../issues).

---

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE). Free to use, modify,
and share.

---

<div align="center">

**Built for makers who want to build their own Jarvis.** ⭐ Star it if it helped!

</div>
