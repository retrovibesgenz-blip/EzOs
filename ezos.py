"""
ezos  -  Easy OS   (v2.0  "Jarvis edition")
===========================================
A tiny, human-readable harness that lets an AI (or a lazy human) drive the
operating system with dead-simple Python functions. Perfect foundation for
building your own Jarvis.

What's new in v2.0
------------------
* open_app() now ACTUALLY launches real apps - Spotify, Zoom, Discord,
  ChatGPT, WhatsApp, Chrome, VS Code, anything in your Start menu - using
  Windows' own Get-StartApps resolver with smart fallbacks.
* Browser + search are fixed: search_web('x', browser='chrome') really opens
  Chrome, and Google is the default engine (no more Bing surprises).
* Failures are now VISIBLE: when something can't run you get a clear
  "WARNING ezos: ..." printed to the screen, instead of silence.
* Zero required dependencies for the core - app launching, browser, media
  keys, window control, volume, weather, etc. all work with a plain Python
  install. (psutil / pyautogui only unlock a few extras.)
* 30+ new Jarvis commands: play music, play YouTube, weather, reminders,
  media keys, window management, brightness, public IP, WhatsApp, and more.
* AI dispatcher: ezos.run("open_app", app_name="spotify") and
  ezos.list_commands() so an LLM can call everything by name.

Quick taste
-----------
    import ezos

    ezos.open_app("spotify")                 # launches Spotify (Store app!)
    ezos.play_on_youtube("lofi hip hop")     # finds + opens the first video
    ezos.search_web("weather", browser="chrome")
    print(ezos.weather("London"))
    ezos.reminder(10, "Stretch your legs!")  # notifies + speaks in 10s
    ezos.speak("All systems online, boss.")

Both snake_case (open_app) and camelCase (openApp) names work everywhere.
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import types
import shutil
import socket
import zipfile
import platform
import threading
import subprocess
import webbrowser
import datetime
import urllib.request
import urllib.parse
from urllib.parse import quote_plus, quote

__version__ = "2.1.0"

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# When True, failures print a visible warning so you (or your AI) notice them
# immediately instead of a silent "nothing happened".
VERBOSE = True


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------
def set_verbose(on: bool = True) -> None:
    """Turn the visible WARNING-on-failure messages on or off."""
    global VERBOSE
    VERBOSE = bool(on)


def _ok(message: str, **extra) -> dict:
    d = {"ok": True, "message": message}
    d.update(extra)
    return d


def _fail(message: str, **extra) -> dict:
    if VERBOSE:
        print(f"WARNING ezos: {message}", file=sys.stderr)
    d = {"ok": False, "message": message}
    d.update(extra)
    return d


def _need(package: str, pip_name: str | None = None):
    """Import an optional package or raise a friendly, actionable error."""
    pip_name = pip_name or package
    try:
        return __import__(package)
    except ImportError:
        raise RuntimeError(
            f"ezos: this function needs the '{package}' package.\n"
            f"       Install it with:  pip install {pip_name}"
        )


def _powershell(command: str, timeout: int = 20) -> subprocess.CompletedProcess:
    """Run a PowerShell command and return the CompletedProcess."""
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, timeout=timeout,
    )


def _http_get(url: str, timeout: int = 15, user_agent: str = "Mozilla/5.0 ezos") -> str:
    """Fetch a URL's text (stdlib, no deps). user_agent is customizable because
    some services (e.g. wttr.in) return plain text only to curl-like agents."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ---- Windows virtual-key codes (for ctypes keyboard/media, no pyautogui) ----
_VK = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "space": 0x20, "f4": 0x73,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "v": 0x56, "d": 0x44, "m": 0x4D,
    "vol_mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play": 0xB3,
}


def _tap(vk: int, times: int = 1) -> None:
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def _combo(*names: str) -> None:
    """Press a key combo like _combo('win', 'd') using ctypes (no deps)."""
    import ctypes
    vks = [_VK[n] for n in names]
    for vk in vks:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.03)
    for vk in reversed(vks):
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


# ===========================================================================
#  1. FILES  &  FOLDERS
# ===========================================================================
def create_file(path: str, content: str = "") -> dict:
    """Create a new file (any type) and optionally put text inside it."""
    try:
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return _ok(f"Created file '{path}'")
    except Exception as e:
        return _fail(f"Could not create '{path}': {e}")


def read_file(path: str) -> str:
    """Return the full text contents of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        _fail(f"Could not read '{path}': {e}")
        return ""


def write_file(path: str, content: str) -> dict:
    """Overwrite a file with new text (creates it if missing)."""
    return create_file(path, content)


def append_file(path: str, content: str) -> dict:
    """Add text to the END of a file without erasing what's there."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return _ok(f"Appended to '{path}'")
    except Exception as e:
        return _fail(f"Could not append to '{path}': {e}")


def delete_file(path: str) -> dict:
    """Delete a single file."""
    try:
        os.remove(path)
        return _ok(f"Deleted file '{path}'")
    except Exception as e:
        return _fail(f"Could not delete '{path}': {e}")


def copy_file(source: str, destination: str) -> dict:
    """Copy a file from one place to another."""
    try:
        shutil.copy2(source, destination)
        return _ok(f"Copied '{source}' -> '{destination}'")
    except Exception as e:
        return _fail(f"Copy failed: {e}")


def move_file(source: str, destination: str) -> dict:
    """Move a file (or folder) to a new location."""
    try:
        shutil.move(source, destination)
        return _ok(f"Moved '{source}' -> '{destination}'")
    except Exception as e:
        return _fail(f"Move failed: {e}")


def rename_file(path: str, new_name: str) -> dict:
    """Rename a file, keeping it in the same folder."""
    try:
        new_path = os.path.join(os.path.dirname(path), new_name)
        os.rename(path, new_path)
        return _ok(f"Renamed to '{new_path}'")
    except Exception as e:
        return _fail(f"Rename failed: {e}")


def file_exists(path: str) -> bool:
    """True if the file or folder exists."""
    return os.path.exists(path)


def list_files(folder: str = ".") -> list[str]:
    """List the names of everything inside a folder."""
    try:
        return sorted(os.listdir(folder))
    except Exception as e:
        _fail(f"Could not list '{folder}': {e}")
        return []


def find_file(name: str, root: str | None = None, limit: int = 50) -> list[str]:
    """Search for files whose name contains `name`, starting from a folder.

    Defaults to searching your user home folder. Returns up to `limit` paths.
    """
    root = root or os.path.expanduser("~")
    needle = name.lower()
    matches: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if needle in f.lower():
                matches.append(os.path.join(dirpath, f))
                if len(matches) >= limit:
                    return matches
    return matches


def create_folder(path: str) -> dict:
    """Create a folder (and any missing parent folders)."""
    try:
        os.makedirs(path, exist_ok=True)
        return _ok(f"Created folder '{path}'")
    except Exception as e:
        return _fail(f"Could not create folder: {e}")


def delete_folder(path: str) -> dict:
    """Delete a folder AND everything inside it. Be careful!"""
    try:
        shutil.rmtree(path)
        return _ok(f"Deleted folder '{path}'")
    except Exception as e:
        return _fail(f"Could not delete folder: {e}")


def zip_files(output_zip: str, files: list[str]) -> dict:
    """Compress a list of files into a single .zip archive."""
    try:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, os.path.basename(f))
        return _ok(f"Zipped {len(files)} file(s) into '{output_zip}'")
    except Exception as e:
        return _fail(f"Zip failed: {e}")


def unzip(zip_path: str, extract_to: str = ".") -> dict:
    """Extract everything from a .zip archive into a folder."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_to)
        return _ok(f"Extracted '{zip_path}' -> '{extract_to}'")
    except Exception as e:
        return _fail(f"Unzip failed: {e}")


def open_file(path: str) -> dict:
    """Open a file with its default program (e.g. a .pdf in a PDF viewer)."""
    try:
        full = os.path.abspath(path)
        if IS_WINDOWS:
            os.startfile(full)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", full])
        else:
            subprocess.Popen(["xdg-open", full])
        return _ok(f"Opened file '{full}'")
    except Exception as e:
        return _fail(f"open_file failed: {e}")


def open_folder(path: str = ".") -> dict:
    """Open a folder in the file explorer / finder."""
    try:
        full = os.path.abspath(path)
        if IS_WINDOWS:
            os.startfile(full)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", full])
        else:
            subprocess.Popen(["xdg-open", full])
        return _ok(f"Opened folder '{full}'")
    except Exception as e:
        return _fail(f"open_folder failed: {e}")


# ===========================================================================
#  2. APPS  &  PROCESSES   (the big fix)
# ===========================================================================
# Friendly names -> what to actually search for in the Start menu.
_APP_ALIASES = {
    "vscode": "visual studio code", "vs code": "visual studio code",
    "code": "visual studio code",
    "zoom": "zoom workplace", "word": "word", "excel": "excel",
    "powerpoint": "powerpoint", "ppt": "powerpoint",
    "cmd": "command prompt", "terminal": "windows terminal",
    "files": "file explorer", "explorer": "file explorer",
    "vlc": "vlc media player", "chatgpt": "chatgpt",
}

# Simple built-ins that os.startfile finds instantly (System32 is on PATH).
_BUILTIN_EXES = {
    "notepad", "calc", "mspaint", "paint", "taskmgr", "wordpad", "write",
    "snippingtool", "charmap", "magnify", "control", "regedit", "cmd",
    "powershell", "explorer",
}
_BUILTIN_FIX = {"paint": "mspaint", "task manager": "taskmgr",
                "calculator": "calc", "command prompt": "cmd"}

_START_APPS_CACHE: list[dict] | None = None


def _get_start_apps() -> list[dict]:
    """Return [{'Name':.., 'AppID':..}, ...] for every Start-menu app (cached)."""
    global _START_APPS_CACHE
    if _START_APPS_CACHE is not None:
        return _START_APPS_CACHE
    _START_APPS_CACHE = []
    if not IS_WINDOWS:
        return _START_APPS_CACHE
    try:
        out = _powershell("Get-StartApps | ConvertTo-Json -Compress")
        data = json.loads(out.stdout) if out.stdout.strip() else []
        if isinstance(data, dict):
            data = [data]
        _START_APPS_CACHE = [d for d in data if d.get("AppID")]
    except Exception:
        _START_APPS_CACHE = []
    return _START_APPS_CACHE


def _find_start_app(query: str) -> dict | None:
    """Best Start-menu app match for a query (ignores uninstallers)."""
    q = query.lower().strip()
    best, best_score = None, -1
    for app in _get_start_apps():
        name = (app.get("Name") or "").lower()
        if not name or "uninstall" in name:
            continue
        if name == q:
            score = 1000
        elif name.startswith(q):
            score = 500 - len(name)
        elif q in name:
            score = 300 - len(name)
        elif all(w in name for w in q.split()):
            score = 150 - len(name)
        else:
            continue
        if score > best_score:
            best, best_score = app, score
    return best


def open_app(app_name: str) -> dict:
    """Launch an application by friendly name.

    Works with Store apps AND desktop apps:
        ezos.open_app("spotify")      ezos.open_app("zoom")
        ezos.open_app("discord")      ezos.open_app("chatgpt")
        ezos.open_app("chrome")       ezos.open_app("notepad")
        ezos.open_app("whatsapp")     ezos.open_app("visual studio code")
    """
    raw = app_name.strip()
    key = raw.lower().removesuffix(".exe")

    # 0) if it's a full path or an exe we can start directly, do it
    if os.path.isabs(raw) and os.path.exists(raw):
        try:
            os.startfile(raw)  # type: ignore[attr-defined]
            return _ok(f"Opened '{raw}'")
        except Exception as e:
            return _fail(f"Could not open '{raw}': {e}")

    # 1) browsers -> use the dedicated, reliable browser launcher
    if key in _BROWSER_PATHS:
        return open_browser(browser=key)

    if not IS_WINDOWS:
        # macOS / Linux simple path
        try:
            if IS_MAC:
                subprocess.Popen(["open", "-a", raw])
            else:
                subprocess.Popen([key])
            return _ok(f"Opened app '{raw}'")
        except Exception as e:
            return _fail(f"Could not open '{raw}': {e}")

    # 2) fast path for tiny built-in Windows tools
    builtin = _BUILTIN_FIX.get(key, key)
    if builtin in _BUILTIN_EXES:
        try:
            os.startfile(builtin)  # type: ignore[attr-defined]
            return _ok(f"Opened '{builtin}'")
        except Exception:
            pass  # fall through to the resolver

    # 3) THE reliable path: match against the real Start menu and launch via AppsFolder
    search = _APP_ALIASES.get(key, key)
    match = _find_start_app(search)
    if match:
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{match['AppID']}"])
            return _ok(f"Opened '{match['Name']}'", resolved=match["Name"])
        except Exception as e:
            return _fail(f"Found '{match['Name']}' but could not launch it: {e}")

    # 4) try letting Windows resolve it (PATH / file associations / App Paths)
    try:
        os.startfile(key)  # type: ignore[attr-defined]
        return _ok(f"Opened '{key}'")
    except Exception:
        pass

    # 5) try where.exe
    try:
        w = subprocess.run(["where", key], capture_output=True, text=True)
        exe = w.stdout.strip().splitlines()[0] if w.stdout.strip() else ""
        if exe:
            os.startfile(exe)  # type: ignore[attr-defined]
            return _ok(f"Opened '{exe}'")
    except Exception:
        pass

    # 6) give up - but helpfully suggest what IS installed
    suggestions = [a["Name"] for a in _get_start_apps()
                   if key.split()[0] in a["Name"].lower()][:5]
    hint = f"  Did you mean: {', '.join(suggestions)}?" if suggestions else \
        "  (not found in your Start menu, PATH, or as an .exe)"
    return _fail(f"Could not find an app called '{app_name}'.{hint}",
                 suggestions=suggestions)


def close_app(app_name: str) -> dict:
    """Force-close an application by its name (e.g. 'spotify' or 'notepad')."""
    try:
        if IS_WINDOWS:
            name = app_name if app_name.lower().endswith(".exe") else app_name + ".exe"
            r = subprocess.run(["taskkill", "/F", "/IM", name],
                               capture_output=True, text=True)
            if r.returncode != 0:
                return _fail(f"No running process named '{name}' "
                             f"({r.stderr.strip() or 'not found'})")
        else:
            subprocess.run(["pkill", "-f", app_name], check=True)
        return _ok(f"Closed app '{app_name}'")
    except Exception as e:
        return _fail(f"Could not close '{app_name}': {e}")


def is_app_running(app_name: str) -> bool:
    """True if a process whose name contains app_name is currently running."""
    needle = app_name.lower().replace(".exe", "")
    try:
        psutil = _need("psutil")
        for p in psutil.process_iter(["name"]):
            if needle in (p.info["name"] or "").lower():
                return True
        return False
    except RuntimeError:
        # no psutil: fall back to tasklist on Windows
        if IS_WINDOWS:
            r = subprocess.run(["tasklist"], capture_output=True, text=True)
            return needle in r.stdout.lower()
        return False


def list_running_apps() -> list[str]:
    """List the names of all currently running processes."""
    try:
        psutil = _need("psutil")
        names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]}
        return sorted(names)
    except RuntimeError:
        if IS_WINDOWS:
            r = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                               capture_output=True, text=True)
            names = {line.split(",")[0].strip('"') for line in r.stdout.splitlines() if line}
            return sorted(names)
        return []


def run_command(command: str) -> dict:
    """Run a raw shell/terminal command and capture its output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
        }
    except Exception as e:
        return _fail(f"Command failed: {e}")


# ===========================================================================
#  3. BROWSER  &  WEB
# ===========================================================================
def _expand_first_existing(paths: list[str]) -> str | None:
    for p in paths:
        full = os.path.expandvars(p)
        if os.path.exists(full):
            return full
    return None


_BROWSER_PATHS: dict[str, list[str]] = {
    "chrome": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ],
    "brave": [
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [r"%LocalAppData%\Programs\Opera\opera.exe"],
}
_BROWSER_PATHS["google chrome"] = _BROWSER_PATHS["chrome"]
_BROWSER_PATHS["msedge"] = _BROWSER_PATHS["edge"]


def _find_browser_exe(name: str) -> str | None:
    paths = _BROWSER_PATHS.get(name.lower().strip())
    return _expand_first_existing(paths) if paths else None


def open_browser(url: str = "", browser: str = "default") -> dict:
    """Open a web page in a specific browser (or the system default).

    browser can be "default", "chrome", "edge", "firefox", "brave", "opera".
        ezos.open_browser("github.com", "chrome")
        ezos.open_browser(browser="firefox")   # just open Firefox
    """
    url = url.strip()
    if url and not url.startswith(("http://", "https://", "about:")):
        url = "https://" + url

    if browser and browser.lower() != "default":
        exe = _find_browser_exe(browser)
        if exe:
            try:
                args = [exe] + ([url] if url else [])
                subprocess.Popen(args)
                return _ok(f"Opened {browser}" + (f" at '{url}'" if url else ""))
            except Exception as e:
                return _fail(f"Could not launch {browser}: {e}")
        # requested browser not installed -> tell the user, then use default
        _fail(f"'{browser}' browser not found; using your default browser instead.")

    try:
        webbrowser.open(url or "about:blank")
        return _ok(f"Opened '{url or 'browser'}' in the default browser")
    except Exception as e:
        return _fail(f"Could not open browser: {e}")


def open_url(url: str, browser: str = "default") -> dict:
    """Open any URL (adds https:// if missing). Optionally pick a browser."""
    return open_browser(url, browser)


_SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "ddg": "https://duckduckgo.com/?q=",
    "youtube": "https://www.youtube.com/results?search_query=",
    "brave": "https://search.brave.com/search?q=",
}


def search_web(query: str, engine: str = "google", browser: str = "default") -> dict:
    """Search the web for a phrase.

    engine: google (default) / bing / duckduckgo / youtube / brave
    browser: default / chrome / edge / firefox / brave / opera
        ezos.search_web("python tips")                    # Google, default browser
        ezos.search_web("python tips", browser="chrome")  # Google, in Chrome
    """
    base = _SEARCH_ENGINES.get(engine.lower(), _SEARCH_ENGINES["google"])
    url = base + quote_plus(query)
    result = open_browser(url, browser)
    if result["ok"]:
        return _ok(f"Searched {engine} for '{query}'")
    return result


def google(query: str, browser: str = "default") -> dict:
    """Shortcut: Google something."""
    return search_web(query, "google", browser)


def search_youtube(query: str, browser: str = "default") -> dict:
    """Shortcut: open a YouTube search results page."""
    return search_web(query, "youtube", browser)


# common website shortcuts for open_website()
_SITES = {
    "youtube": "https://youtube.com", "google": "https://google.com",
    "gmail": "https://mail.google.com", "mail": "https://mail.google.com",
    "github": "https://github.com", "chatgpt": "https://chat.openai.com",
    "maps": "https://maps.google.com", "drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com", "netflix": "https://netflix.com",
    "amazon": "https://amazon.com", "wikipedia": "https://wikipedia.org",
    "stackoverflow": "https://stackoverflow.com", "reddit": "https://reddit.com",
    "twitter": "https://x.com", "x": "https://x.com",
    "instagram": "https://instagram.com", "linkedin": "https://linkedin.com",
    "whatsapp": "https://web.whatsapp.com", "spotify": "https://open.spotify.com",
    "claude": "https://claude.ai", "chat": "https://chat.openai.com",
}


def open_website(name: str, browser: str = "default") -> dict:
    """Open a well-known website by nickname (youtube, gmail, github, ...)
    or any domain/URL. Unknown words become a Google search."""
    key = name.lower().strip()
    if key in _SITES:
        return open_browser(_SITES[key], browser)
    if "." in key or key.startswith("http"):
        return open_browser(name, browser)
    return search_web(name, "google", browser)


def download_file(url: str, save_as: str) -> dict:
    """Download a file from the internet and save it to disk (stdlib, no deps)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ezos"})
        with urllib.request.urlopen(req, timeout=60) as r, open(save_as, "wb") as f:
            shutil.copyfileobj(r, f)
        return _ok(f"Downloaded '{url}' -> '{save_as}'")
    except Exception as e:
        return _fail(f"Download failed: {e}")


def weather(city: str = "") -> str:
    """One-line current weather for a city (uses free wttr.in, no API key).

    Returns plain text like 'London: Partly cloudy +12C' - safe to print on
    any console and safe to pass to ezos.speak().
    """
    try:
        loc = quote(city)
        # %C=condition text, %t=temp, %h=humidity, %f=feels-like. No emoji -> safe to print.
        # wttr.in only returns plain text to a curl-like agent, not a browser UA.
        raw = _http_get(f"https://wttr.in/{loc}?format=%l:+%C+%t+(feels+%f),+%h+humidity",
                        user_agent="curl/8.4.0")
        return raw.strip().replace("°", "")  # drop the degree symbol too
    except Exception as e:
        _fail(f"weather failed: {e}")
        return ""


def public_ip() -> str:
    """Your public (internet-facing) IP address."""
    try:
        return _http_get("https://api.ipify.org").strip()
    except Exception as e:
        _fail(f"public_ip failed: {e}")
        return ""


# ===========================================================================
#  4. MEDIA  (Jarvis: play music / videos / control playback)
# ===========================================================================
def play_on_youtube(query: str) -> dict:
    """Find the FIRST YouTube result for a query and open that video."""
    try:
        html = _http_get(
            "https://www.youtube.com/results?search_query=" + quote_plus(query))
        m = re.search(r'"videoId":"([\w-]{11})"', html)
        if m:
            url = "https://www.youtube.com/watch?v=" + m.group(1)
            webbrowser.open(url)
            return _ok(f"Playing '{query}' on YouTube", url=url)
    except Exception:
        pass
    # fallback: just open the search page
    search_youtube(query)
    return _ok(f"Opened YouTube search for '{query}'")


def play_on_spotify(query: str) -> dict:
    """Open Spotify and search for a song/artist (desktop app, or web)."""
    try:
        if IS_WINDOWS:
            os.startfile(f"spotify:search:{quote(query)}")  # type: ignore[attr-defined]
            return _ok(f"Searching Spotify for '{query}'")
    except Exception:
        pass
    webbrowser.open(f"https://open.spotify.com/search/{quote(query)}")
    return _ok(f"Opened Spotify web search for '{query}'")


def play_pause_media() -> dict:
    """Press the Play/Pause media key (controls Spotify, YouTube, etc.)."""
    if not IS_WINDOWS:
        return _fail("media keys are Windows-only here")
    _tap(_VK["media_play"])
    return _ok("Toggled play/pause")


def next_track() -> dict:
    """Skip to the next track."""
    if not IS_WINDOWS:
        return _fail("media keys are Windows-only here")
    _tap(_VK["media_next"])
    return _ok("Next track")


def previous_track() -> dict:
    """Go back to the previous track."""
    if not IS_WINDOWS:
        return _fail("media keys are Windows-only here")
    _tap(_VK["media_prev"])
    return _ok("Previous track")


def stop_media() -> dict:
    """Stop media playback."""
    if not IS_WINDOWS:
        return _fail("media keys are Windows-only here")
    _tap(_VK["media_stop"])
    return _ok("Stopped media")


# ===========================================================================
#  5. SYSTEM  INFO
# ===========================================================================
def system_info() -> dict:
    """A quick snapshot of the computer: OS, machine name, Python, CPU count."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "release": platform.release(),
        "machine": platform.machine(),
        "computer_name": platform.node(),
        "processor": platform.processor(),
        "cpu_cores": os.cpu_count(),
        "python_version": platform.python_version(),
    }


def cpu_usage() -> float:
    """Current CPU usage as a percentage (0-100)."""
    psutil = _need("psutil")
    return psutil.cpu_percent(interval=1)


def ram_usage() -> dict:
    """Memory usage: total, used, free (in GB) and percent used."""
    psutil = _need("psutil")
    m = psutil.virtual_memory()
    gb = 1024 ** 3
    return {
        "total_gb": round(m.total / gb, 2),
        "used_gb": round(m.used / gb, 2),
        "free_gb": round(m.available / gb, 2),
        "percent_used": m.percent,
    }


def disk_space(drive: str | None = None) -> dict:
    """Free / used disk space (in GB) for a drive (defaults to C: / root)."""
    if drive is None:
        drive = "C:\\" if IS_WINDOWS else "/"
    total, used, free = shutil.disk_usage(drive)
    gb = 1024 ** 3
    return {
        "drive": drive,
        "total_gb": round(total / gb, 2),
        "used_gb": round(used / gb, 2),
        "free_gb": round(free / gb, 2),
    }


def battery_status() -> dict:
    """Battery percentage and whether it's plugged in."""
    psutil = _need("psutil")
    b = psutil.sensors_battery()
    if b is None:
        return _fail("No battery detected (desktop?)")
    return {"percent": b.percent, "plugged_in": b.power_plugged,
            "seconds_left": b.secsleft}


def get_ip() -> dict:
    """The computer's local IP address and hostname."""
    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except Exception:
        ip = "unknown"
    return {"hostname": hostname, "local_ip": ip}


def wifi_name() -> str:
    """The name (SSID) of the Wi-Fi network you're connected to (Windows)."""
    if not IS_WINDOWS:
        return _fail("wifi_name is Windows-only here") and ""
    try:
        r = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if re.match(r"\s*SSID\s*:", line):   # 'SSID' but not 'BSSID'
                return line.split(":", 1)[1].strip()
        return ""
    except Exception as e:
        _fail(f"wifi_name failed: {e}")
        return ""


def current_time() -> str:
    """The current time as HH:MM:SS."""
    return datetime.datetime.now().strftime("%H:%M:%S")


def current_date() -> str:
    """Today's date as YYYY-MM-DD."""
    return datetime.date.today().strftime("%Y-%m-%d")


# ===========================================================================
#  6. SYSTEM  CONTROL   (power / session / screen)
# ===========================================================================
def shutdown(delay_seconds: int = 0) -> dict:
    """Shut down the computer after an optional delay (in seconds)."""
    try:
        if IS_WINDOWS:
            subprocess.run(["shutdown", "/s", "/t", str(delay_seconds)], check=True)
        else:
            subprocess.run(["shutdown", "-h", f"+{max(1, delay_seconds // 60)}"], check=True)
        return _ok(f"Shutting down in {delay_seconds}s (cancel with ezos.cancel_shutdown())")
    except Exception as e:
        return _fail(f"Shutdown failed: {e}")


def restart(delay_seconds: int = 0) -> dict:
    """Restart the computer after an optional delay (in seconds)."""
    try:
        if IS_WINDOWS:
            subprocess.run(["shutdown", "/r", "/t", str(delay_seconds)], check=True)
        else:
            subprocess.run(["shutdown", "-r", f"+{max(1, delay_seconds // 60)}"], check=True)
        return _ok(f"Restarting in {delay_seconds}s")
    except Exception as e:
        return _fail(f"Restart failed: {e}")


def cancel_shutdown() -> dict:
    """Cancel a scheduled shutdown or restart."""
    try:
        subprocess.run(["shutdown", "/a" if IS_WINDOWS else "-c"], check=True)
        return _ok("Cancelled scheduled shutdown")
    except Exception as e:
        return _fail(f"Could not cancel: {e}")


def lock_screen() -> dict:
    """Lock the computer (requires a password to get back in)."""
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        elif IS_MAC:
            subprocess.run(["pmset", "displaysleepnow"])
        else:
            subprocess.run(["loginctl", "lock-session"])
        return _ok("Screen locked")
    except Exception as e:
        return _fail(f"Lock failed: {e}")


def sleep_pc() -> dict:
    """Put the computer to sleep."""
    try:
        if IS_WINDOWS:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif IS_MAC:
            subprocess.run(["pmset", "sleepnow"])
        else:
            subprocess.run(["systemctl", "suspend"])
        return _ok("Going to sleep")
    except Exception as e:
        return _fail(f"Sleep failed: {e}")


def empty_recycle_bin() -> dict:
    """Empty the Windows Recycle Bin (Windows only)."""
    if not IS_WINDOWS:
        return _fail("empty_recycle_bin is Windows-only")
    try:
        import ctypes
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x07)
        return _ok("Recycle Bin emptied")
    except Exception as e:
        return _fail(f"Could not empty Recycle Bin: {e}")


def set_brightness(level: int) -> dict:
    """Set screen brightness 0-100 (laptops; Windows)."""
    if not IS_WINDOWS:
        return _fail("set_brightness is Windows-only here")
    level = max(0, min(100, int(level)))
    try:
        out = _powershell(
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{level})")
        if out.returncode == 0:
            return _ok(f"Brightness set to {level}%")
        return _fail(f"set_brightness failed: {out.stderr.strip()}")
    except Exception as e:
        return _fail(f"set_brightness failed: {e}")


# ===========================================================================
#  7. WINDOW  MANAGEMENT   (ctypes, no extra deps)
# ===========================================================================
def _foreground_hwnd():
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow()


def active_window() -> str:
    """The title of the window currently in focus (Windows)."""
    if not IS_WINDOWS:
        return ""
    import ctypes
    hwnd = _foreground_hwnd()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def minimize_window() -> dict:
    """Minimize the currently focused window."""
    if not IS_WINDOWS:
        return _fail("window control is Windows-only here")
    import ctypes
    ctypes.windll.user32.ShowWindow(_foreground_hwnd(), 6)  # SW_MINIMIZE
    return _ok("Minimized active window")


def maximize_window() -> dict:
    """Maximize the currently focused window."""
    if not IS_WINDOWS:
        return _fail("window control is Windows-only here")
    import ctypes
    ctypes.windll.user32.ShowWindow(_foreground_hwnd(), 3)  # SW_MAXIMIZE
    return _ok("Maximized active window")


def close_window() -> dict:
    """Close the currently focused window (like clicking the X)."""
    if not IS_WINDOWS:
        return _fail("window control is Windows-only here")
    import ctypes
    ctypes.windll.user32.PostMessageW(_foreground_hwnd(), 0x0010, 0, 0)  # WM_CLOSE
    return _ok("Closed active window")


def show_desktop() -> dict:
    """Minimize everything and show the desktop (Win+D)."""
    if not IS_WINDOWS:
        return _fail("show_desktop is Windows-only here")
    _combo("win", "d")
    return _ok("Showing desktop")


def switch_window() -> dict:
    """Switch to the next window (Alt+Tab)."""
    if not IS_WINDOWS:
        return _fail("switch_window is Windows-only here")
    _combo("alt", "tab")
    return _ok("Switched window")


# ===========================================================================
#  8. CLIPBOARD
# ===========================================================================
def copy_to_clipboard(text: str) -> dict:
    """Put text onto the system clipboard."""
    try:
        try:
            __import__("pyperclip").copy(text)
        except ImportError:
            if IS_WINDOWS:
                subprocess.run("clip", input=text, text=True, shell=True)
            elif IS_MAC:
                subprocess.run("pbcopy", input=text, text=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True)
        return _ok("Copied to clipboard")
    except Exception as e:
        return _fail(f"Clipboard copy failed: {e}")


def paste_from_clipboard() -> str:
    """Return whatever text is currently on the clipboard."""
    try:
        return __import__("pyperclip").paste()
    except ImportError:
        if IS_WINDOWS:
            r = _powershell("Get-Clipboard")
            return r.stdout.rstrip("\n")
        elif IS_MAC:
            return subprocess.run("pbpaste", capture_output=True, text=True).stdout
        else:
            return subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                  capture_output=True, text=True).stdout


# ===========================================================================
#  9. SOUND  &  WALLPAPER  &  SCREENSHOT
# ===========================================================================
def screenshot(save_as: str = "screenshot.png") -> dict:
    """Take a screenshot of the whole screen and save it as a PNG."""
    try:
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(save_as)
        except ImportError:
            pyautogui = _need("pyautogui")
            pyautogui.screenshot(save_as)
        return _ok(f"Saved screenshot to '{os.path.abspath(save_as)}'")
    except Exception as e:
        return _fail(f"Screenshot failed: {e}")


def volume_up(steps: int = 5) -> dict:
    """Turn the system volume UP (each step is ~2%)."""
    if not IS_WINDOWS:
        return _fail("volume_up is Windows-only")
    _tap(_VK["vol_up"], steps)
    return _ok(f"Volume up ({steps} steps)")


def volume_down(steps: int = 5) -> dict:
    """Turn the system volume DOWN (each step is ~2%)."""
    if not IS_WINDOWS:
        return _fail("volume_down is Windows-only")
    _tap(_VK["vol_down"], steps)
    return _ok(f"Volume down ({steps} steps)")


def mute() -> dict:
    """Toggle mute on/off."""
    if not IS_WINDOWS:
        return _fail("mute is Windows-only")
    _tap(_VK["vol_mute"])
    return _ok("Toggled mute")


def set_volume(level: int) -> dict:
    """Set the exact system volume (0-100). Needs the 'pycaw' package."""
    if not IS_WINDOWS:
        return _fail("set_volume is Windows-only")
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100.0, None)
        return _ok(f"Volume set to {level}%")
    except ImportError:
        return _fail("set_volume needs:  pip install pycaw comtypes")
    except Exception as e:
        return _fail(f"set_volume failed: {e}")


def set_wallpaper(image_path: str) -> dict:
    """Change the desktop wallpaper to an image file (Windows)."""
    if not IS_WINDOWS:
        return _fail("set_wallpaper is Windows-only here")
    try:
        import ctypes
        path = os.path.abspath(image_path)
        ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
        return _ok(f"Wallpaper set to '{path}'")
    except Exception as e:
        return _fail(f"set_wallpaper failed: {e}")


# ===========================================================================
# 10. KEYBOARD  &  MOUSE
# ===========================================================================
def type_text(text: str, interval: float = 0.02) -> dict:
    """Type text into the focused window.

    Uses pyautogui if installed; otherwise falls back to a dependency-free
    clipboard-paste trick so it still works out of the box on Windows.
    """
    try:
        import pyautogui
        pyautogui.typewrite(text, interval=interval)
        return _ok("Typed text")
    except ImportError:
        if IS_WINDOWS:
            copy_to_clipboard(text)
            time.sleep(0.1)
            _combo("ctrl", "v")
            return _ok("Typed text (via clipboard paste)")
        return _fail("type_text needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"type_text failed: {e}")


def press_key(key: str) -> dict:
    """Press a single key, e.g. 'enter', 'esc', 'tab', 'f5', 'space'."""
    try:
        import pyautogui
        pyautogui.press(key)
        return _ok(f"Pressed '{key}'")
    except ImportError:
        if IS_WINDOWS and key.lower() in _VK:
            _tap(_VK[key.lower()])
            return _ok(f"Pressed '{key}'")
        return _fail("press_key needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"press_key failed: {e}")


def hotkey(*keys: str) -> dict:
    """Press a key combo, e.g. ezos.hotkey('ctrl', 'c') to copy."""
    try:
        import pyautogui
        pyautogui.hotkey(*keys)
        return _ok(f"Pressed hotkey {'+'.join(keys)}")
    except ImportError:
        if IS_WINDOWS and all(k.lower() in _VK for k in keys):
            _combo(*[k.lower() for k in keys])
            return _ok(f"Pressed hotkey {'+'.join(keys)}")
        return _fail("hotkey needs:  pip install pyautogui  (for non-standard keys)")
    except Exception as e:
        return _fail(f"hotkey failed: {e}")


def click(x: int | None = None, y: int | None = None) -> dict:
    """Click the mouse. With no coordinates, clicks where it is now.

    Uses pyautogui if installed, otherwise a dependency-free ctypes fallback on
    Windows - so the AI can click out of the box.
    """
    try:
        pg = _pyautogui_or_none()
        if pg:
            pg.click() if x is None or y is None else pg.click(x, y)
            return _ok("Clicked")
        if IS_WINDOWS:
            import ctypes
            if x is not None and y is not None:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
            ctypes.windll.user32.mouse_event(_MOUSE_LEFT_DOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(_MOUSE_LEFT_UP, 0, 0, 0, 0)
            return _ok("Clicked")
        return _fail("click needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"click failed: {e}")


def move_mouse(x: int, y: int, duration: float = 0.3) -> dict:
    """Move the mouse cursor to screen coordinates (x, y)."""
    try:
        pg = _pyautogui_or_none()
        if pg:
            pg.moveTo(x, y, duration=duration)
            return _ok(f"Moved mouse to ({x}, {y})")
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
            return _ok(f"Moved mouse to ({x}, {y})")
        return _fail("move_mouse needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"move_mouse failed: {e}")


def scroll(amount: int) -> dict:
    """Scroll the mouse wheel. Positive = up, negative = down."""
    try:
        pg = _pyautogui_or_none()
        if pg:
            pg.scroll(amount)
            return _ok(f"Scrolled {amount}")
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(amount), 0)
            return _ok(f"Scrolled {amount}")
        return _fail("scroll needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"scroll failed: {e}")


# ===========================================================================
# 10b. VISION + CURSOR + KEYBOARD   (give the AI its own eyes & hands)
# ---------------------------------------------------------------------------
# This is what turns ezos from "run commands" into a real computer-using agent:
#   * grid_screenshot() -> a screenshot with a labelled coordinate grid, so a
#     VISION model can read pixel coordinates straight off the picture.
#   * give_cursor() / give_keyboard() -> hand the AI its own mouse & keyboard.
#   * VisionAgent -> a full see -> think -> act loop: the model looks at the
#     screen, decides, moves the cursor, clicks and types, then looks again.
# ===========================================================================

# mouse_event flags for the ctypes fallback (zero pip installs on Windows)
_MOUSE_LEFT_DOWN, _MOUSE_LEFT_UP = 0x0002, 0x0004
_MOUSE_RIGHT_DOWN, _MOUSE_RIGHT_UP = 0x0008, 0x0010


def _pyautogui_or_none():
    """Return pyautogui if it's installed (fail-safe off), else None."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        return pyautogui
    except Exception:
        return None


def _screen_size() -> tuple:
    """(width, height) of the primary screen - dependency-free on Windows."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        pg = _pyautogui_or_none()
        if pg:
            size = pg.size()
            return int(size[0]), int(size[1])
        return (1920, 1080)


def _capture():
    """Grab the screen as a PIL image, or None if nothing can capture it."""
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        pg = _pyautogui_or_none()
        if pg:
            try:
                return pg.screenshot()
            except Exception:
                return None
        return None


def grid_screenshot(save_as: str = "ezos_vision.png", spacing: int = 100,
                    show_labels: bool = True) -> dict:
    """Screenshot the screen with a labelled coordinate grid drawn on top.

    This is the AI's EYES. Hand the saved image to a vision model (GPT-4o,
    Gemini, Claude...) and it can read the x,y numbers off the grid, then
    click/move to those exact coordinates with its cursor.

        shot = ezos.grid_screenshot(spacing=100)
        # -> {ok, path, width, height, spacing} ; send shot['path'] to the AI

    Needs Pillow for the grid (pip install Pillow). Without it you still get a
    plain screenshot so nothing breaks.
    """
    img = _capture()
    if img is None:
        return _fail("grid_screenshot needs Pillow or pyautogui:  pip install Pillow")
    try:
        from PIL import ImageDraw, ImageFont
    except Exception:
        try:
            img.convert("RGB").save(save_as)
        except Exception as e:
            return _fail(f"grid_screenshot failed: {e}")
        return _ok(f"Saved plain screenshot (install Pillow for the grid) to "
                   f"'{os.path.abspath(save_as)}'", path=os.path.abspath(save_as),
                   width=img.size[0], height=img.size[1], spacing=spacing, grid=False)
    try:
        img = img.convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except Exception:
            font = ImageFont.load_default()
        line = (255, 0, 0)
        for x in range(0, w, spacing):
            draw.line([(x, 0), (x, h)], fill=line, width=1)
        for y in range(0, h, spacing):
            draw.line([(0, y), (w, y)], fill=line, width=1)
        if show_labels:
            for x in range(0, w, spacing):
                for y in range(0, h, spacing):
                    tag = f"{x},{y}"
                    draw.rectangle([x + 1, y + 1, x + 2 + 6 * len(tag), y + 13],
                                   fill=(0, 0, 0))
                    draw.text((x + 2, y + 1), tag, fill=(255, 255, 0), font=font)
        img.save(save_as)
    except Exception as e:
        return _fail(f"grid_screenshot failed: {e}")
    return _ok(f"Saved grid screenshot to '{os.path.abspath(save_as)}'",
               path=os.path.abspath(save_as), width=w, height=h,
               spacing=spacing, grid=True)


def double_click(x: int | None = None, y: int | None = None) -> dict:
    """Double-click the mouse (optionally move to x,y first)."""
    pg = _pyautogui_or_none()
    try:
        if pg:
            pg.doubleClick() if x is None or y is None else pg.doubleClick(x, y)
            return _ok("Double-clicked")
        if IS_WINDOWS:
            import ctypes
            if x is not None and y is not None:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
            for _ in range(2):
                ctypes.windll.user32.mouse_event(_MOUSE_LEFT_DOWN, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(_MOUSE_LEFT_UP, 0, 0, 0, 0)
            return _ok("Double-clicked")
        return _fail("double_click needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"double_click failed: {e}")


def right_click(x: int | None = None, y: int | None = None) -> dict:
    """Right-click the mouse (optionally move to x,y first)."""
    pg = _pyautogui_or_none()
    try:
        if pg:
            pg.rightClick() if x is None or y is None else pg.rightClick(x, y)
            return _ok("Right-clicked")
        if IS_WINDOWS:
            import ctypes
            if x is not None and y is not None:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
            ctypes.windll.user32.mouse_event(_MOUSE_RIGHT_DOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(_MOUSE_RIGHT_UP, 0, 0, 0, 0)
            return _ok("Right-clicked")
        return _fail("right_click needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"right_click failed: {e}")


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
    """Drag the mouse from (x1,y1) to (x2,y2) with the left button held."""
    pg = _pyautogui_or_none()
    try:
        if pg:
            pg.moveTo(x1, y1)
            pg.dragTo(x2, y2, duration=duration, button="left")
            return _ok(f"Dragged ({x1},{y1}) -> ({x2},{y2})")
        if IS_WINDOWS:
            import ctypes
            u = ctypes.windll.user32
            u.SetCursorPos(int(x1), int(y1))
            u.mouse_event(_MOUSE_LEFT_DOWN, 0, 0, 0, 0)
            time.sleep(max(0.0, duration))
            u.SetCursorPos(int(x2), int(y2))
            u.mouse_event(_MOUSE_LEFT_UP, 0, 0, 0, 0)
            return _ok(f"Dragged ({x1},{y1}) -> ({x2},{y2})")
        return _fail("drag needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"drag failed: {e}")


def mouse_position() -> dict:
    """Where the mouse cursor is right now: {ok, x, y}."""
    pg = _pyautogui_or_none()
    try:
        if pg:
            px, py = pg.position()
            return _ok(f"Mouse at ({int(px)}, {int(py)})", x=int(px), y=int(py))
        if IS_WINDOWS:
            import ctypes

            class _P(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = _P()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return _ok(f"Mouse at ({pt.x}, {pt.y})", x=int(pt.x), y=int(pt.y))
        return _fail("mouse_position needs:  pip install pyautogui")
    except Exception as e:
        return _fail(f"mouse_position failed: {e}")


def read_screen(region: tuple | None = None) -> str:
    """Read ALL the text currently visible on screen (OCR). The AI's reading eyes.

    Lets an agent KNOW what's on screen without a vision model. Pass an optional
    (left, top, right, bottom) box to read just part of the screen.
    Needs:  pip install pytesseract Pillow  + the Tesseract engine
    (Windows: https://github.com/UB-Mannheim/tesseract/wiki).
    """
    img = _capture()
    if img is None:
        _fail("read_screen needs Pillow:  pip install Pillow pytesseract")
        return ""
    try:
        import pytesseract
    except Exception:
        _fail("read_screen needs:  pip install pytesseract  (+ the Tesseract engine)")
        return ""
    try:
        if region:
            img = img.crop(tuple(region))
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        _fail(f"read_screen failed: {e}")
        return ""


def find_text_on_screen(text: str) -> list:
    """Find on-screen text and return where it is: [{text, x, y, width, height}].

    x,y is the CENTRE of the matched word - feed it straight to click(x, y).
    Needs:  pip install pytesseract Pillow  + the Tesseract engine.
    """
    img = _capture()
    if img is None:
        _fail("find_text_on_screen needs Pillow:  pip install Pillow pytesseract")
        return []
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        _fail("find_text_on_screen needs:  pip install pytesseract  (+ the engine)")
        return []
    try:
        data = pytesseract.image_to_data(img, output_type=Output.DICT)
        hits, want = [], text.lower().strip()
        for i, word in enumerate(data["text"]):
            if want and want in (word or "").lower().strip():
                x, y = data["left"][i], data["top"][i]
                w, h = data["width"][i], data["height"][i]
                hits.append({"text": word, "x": int(x + w / 2),
                             "y": int(y + h / 2), "width": int(w), "height": int(h)})
        return hits
    except Exception as e:
        _fail(f"find_text_on_screen failed: {e}")
        return []


def click_text(text: str) -> dict:
    """Find on-screen text and CLICK it. 'click the button that says Save'.

    Needs:  pip install pytesseract Pillow  + the Tesseract engine.
    """
    hits = find_text_on_screen(text)
    if not hits:
        return _fail(f"Couldn't find '{text}' on screen")
    target = hits[0]
    click(target["x"], target["y"])
    return _ok(f"Clicked '{text}' at ({target['x']}, {target['y']})",
               x=target["x"], y=target["y"], matches=len(hits))


# ---- persistent agent memory (survives restarts, zero dependencies) --------
_MEMORY_PATH = os.path.join(os.path.expanduser("~"), ".ezos_memory.json")


def _load_memory() -> dict:
    try:
        with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_memory(mem: dict) -> None:
    with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, default=str)


def remember(key: str, value: str) -> dict:
    """Save a fact to the agent's long-term memory (survives restarts).

        ezos.remember("owner_name", "boss")
        ezos.remember("favourite_artist", "Karan Aujla")
    """
    try:
        mem = _load_memory()
        mem[key] = value
        _save_memory(mem)
        return _ok(f"Remembered '{key}'", key=key, value=value)
    except Exception as e:
        return _fail(f"remember failed: {e}")


def recall(key: str | None = None):
    """Recall a saved fact by key (or the WHOLE memory dict if no key given)."""
    mem = _load_memory()
    return mem if key is None else mem.get(key)


def forget(key: str) -> dict:
    """Delete one fact from the agent's long-term memory."""
    try:
        mem = _load_memory()
        if key not in mem:
            return _fail(f"No memory named '{key}'")
        mem.pop(key, None)
        _save_memory(mem)
        return _ok(f"Forgot '{key}'", key=key)
    except Exception as e:
        return _fail(f"forget failed: {e}")


def ask_user(question: str = "ezos needs your input:") -> str:
    """Ask the human a question and return their typed answer (human-in-the-loop)."""
    try:
        return input(f"{question} ")
    except Exception as e:
        _fail(f"ask_user failed: {e}")
        return ""


def listen(timeout: float = 6.0, phrase_limit: float = 12.0) -> str:
    """Listen on the microphone and return what was said as text. The AI's EARS.

    Say "play karan aujla on spotify" and it comes back as a string you can hand
    straight to a Jarvis / VisionAgent.
    Needs:  pip install SpeechRecognition pyaudio   (free Google STT, a mic).
    """
    try:
        import speech_recognition as sr
    except Exception:
        _fail("listen needs:  pip install SpeechRecognition pyaudio")
        return ""
    try:
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.4)
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        return r.recognize_google(audio)
    except Exception as e:
        _fail(f"listen failed: {e}")
        return ""


def api_call(url: str, method: str = "GET", headers: dict | None = None,
             json_body: dict | None = None, params: dict | None = None,
             timeout: int = 20) -> dict:
    """Call ANY web API and get the JSON (or text) back. Dependency-free.

    Lets your agent use the whole internet - weather, GitHub, your own backend,
    an LLM endpoint, anything.

        ezos.api_call("https://api.github.com/repos/python/cpython")
        ezos.api_call("https://httpbin.org/post", method="POST",
                      json_body={"hello": "world"})
    """
    try:
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        hdrs = {"User-Agent": "ezos", "Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=hdrs,
                                     method=method.upper())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
        try:
            body = json.loads(raw)
        except Exception:
            body = raw
        return _ok(f"{method.upper()} {url} -> {status}", status=status, data=body)
    except Exception as e:
        return _fail(f"api_call failed: {e}")


def run_python(code: str) -> dict:
    """Run a snippet of Python the AI wrote and capture its output.

    The snippet shares this process and has `ezos` available, so an agent can
    compose its own multi-step actions on the fly. Powerful - only run code you
    (or an AI you trust) produced.

        ezos.run_python("import ezos; ezos.open_app('spotify')")
    """
    import io
    import contextlib
    buf = io.StringIO()
    env = {"ezos": sys.modules[__name__], "__name__": "__ezos_snippet__"}
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, env)
        return _ok("Ran python snippet", output=buf.getvalue())
    except Exception as e:
        return _fail(f"run_python error: {e}", output=buf.getvalue())


class _RepeatTask:
    """Handle for a repeating background task. Call .stop() to end it."""

    def __init__(self, interval: float, command: str, kwargs: dict):
        self._stop = threading.Event()
        self.command = command
        self.interval = interval

        def _loop():
            while not self._stop.wait(interval):
                try:
                    run(command, **kwargs)
                except Exception as e:
                    _fail(f"every('{command}') tick failed: {e}")

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        return _ok(f"Stopped repeating '{self.command}'")

    def __repr__(self):
        return f"<ezos repeating '{self.command}' every {self.interval}s>"


def every(seconds: float, command: str, args: dict | None = None) -> _RepeatTask:
    """Run an ezos command on a repeat, in the background. Returns a handle.

        job = ezos.every(60, "battery_status")          # check every minute
        job = ezos.every(5, "play_pause_media")          # with no args
        job = ezos.every(30, "set_volume", {"level": 20})
        ...
        job.stop()                                       # when you're done
    """
    return _RepeatTask(seconds, command, args or {})


def send_email(to: str, subject: str, body: str, *, smtp_host: str,
               username: str, password: str, smtp_port: int = 587,
               use_tls: bool = True, sender: str | None = None) -> dict:
    """Send an email via SMTP (stdlib, no pip install). Use an app password.

        ezos.send_email("friend@x.com", "hi", "sent by my agent",
                        smtp_host="smtp.gmail.com", username="me@gmail.com",
                        password=GMAIL_APP_PASSWORD)
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender or username
        msg["To"] = to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            if use_tls:
                s.starttls()
            s.login(username, password)
            s.send_message(msg)
        return _ok(f"Email sent to {to}")
    except Exception as e:
        return _fail(f"send_email failed: {e}")


class Cursor:
    """The AI's own mouse. Get one with ezos.give_cursor().

        cur = ezos.give_cursor()
        cur.look()                 # grid screenshot to show the vision model
        cur.click(840, 460)        # click the coordinate it chose
    """

    def __init__(self, spacing: int = 100):
        self.spacing = spacing
        self.width, self.height = _screen_size()

    def look(self, save_as: str = "ezos_vision.png", spacing: int | None = None) -> dict:
        """Take a grid screenshot (what the AI sees before it acts)."""
        return grid_screenshot(save_as, spacing or self.spacing)

    def move(self, x, y, duration: float = 0.3):
        return move_mouse(x, y, duration)

    def click(self, x=None, y=None):
        return click(x, y)

    def double_click(self, x=None, y=None):
        return double_click(x, y)

    def right_click(self, x=None, y=None):
        return right_click(x, y)

    def drag(self, x1, y1, x2, y2, duration: float = 0.5):
        return drag(x1, y1, x2, y2, duration)

    def scroll(self, amount):
        return scroll(amount)

    def where(self):
        return mouse_position()

    def __repr__(self):
        return f"<ezos.Cursor screen {self.width}x{self.height}, grid {self.spacing}px>"


class Keyboard:
    """The AI's own keyboard. Get one with ezos.give_keyboard().

        kb = ezos.give_keyboard()
        kb.type("karan aujla")
        kb.press("enter")
        kb.hotkey("ctrl", "a")
    """

    def type(self, text: str, interval: float = 0.02):
        return type_text(text, interval)

    def press(self, key: str):
        return press_key(key)

    def enter(self):
        return press_key("enter")

    def hotkey(self, *keys: str):
        return hotkey(*keys)

    def shortcut(self, *keys: str):
        return hotkey(*keys)

    def __repr__(self):
        return "<ezos.Keyboard>"


_CURSOR_GRANTED = False
_KEYBOARD_GRANTED = False


def give_cursor(spacing: int = 100) -> Cursor:
    """Give your AI its OWN mouse cursor.

    Pair it with grid_screenshot() (or cur.look()) so a vision model can see the
    screen, read the coordinate grid, and move/click to any point it wants:

        cur = ezos.give_cursor()
        shot = cur.look()                 # screenshot + coordinate grid
        # the vision model reads the grid, picks (840, 460) = the search bar...
        cur.click(840, 460)

    Returns a Cursor you can also drive by hand.
    """
    global _CURSOR_GRANTED
    _CURSOR_GRANTED = True
    w, h = _screen_size()
    if VERBOSE:
        print(f"ezos: cursor granted - the AI can now move & click "
              f"(screen {w}x{h}, grid every {spacing}px)")
    return Cursor(spacing)


def give_keyboard() -> Keyboard:
    """Give your AI its OWN keyboard (type text, press keys, hit shortcuts).

        kb = ezos.give_keyboard()
        kb.type("lofi hip hop"); kb.press("enter")
    """
    global _KEYBOARD_GRANTED
    _KEYBOARD_GRANTED = True
    if VERBOSE:
        print("ezos: keyboard granted - the AI can now type & press keys")
    return Keyboard()


# Tools the VisionAgent is allowed to use (its eyes, hands + a few shortcuts).
_VISION_TOOLS = [
    "grid_screenshot", "click", "double_click", "right_click", "move_mouse",
    "drag", "scroll", "mouse_position", "type_text", "press_key", "hotkey",
    "open_app", "close_app", "search_web", "play_on_spotify", "play_on_youtube",
    "read_screen", "click_text", "find_text_on_screen", "wait", "speak",
    "remember", "recall",
]

_VISION_RULES = (
    "You are a computer-using agent. You control the screen with your OWN mouse "
    "and keyboard through ezos tools.\n"
    "EVERY step you are shown a fresh screenshot with a red coordinate grid; the "
    "yellow 'x,y' labels are pixel coordinates. To act on something, read its "
    "coordinate off the grid and call click(x=.., y=..) / double_click / "
    "move_mouse, then type_text / press_key as needed.\n"
    "Work ONE action at a time, then look at the next screenshot to check the "
    "result. Open apps with open_app('name'). To type in a field, click it "
    "first, then type_text('...'). When the task is fully done, reply with a "
    "short sentence that starts with DONE and make no tool call.\n"
)


def _data_uri(path: str) -> str:
    """Read an image file into a base64 data: URI for vision models."""
    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


class VisionAgent:
    """A full see -> think -> act loop: the AI gets its own eyes, cursor and
    keyboard and completes on-screen tasks for you.

    Bring an OpenAI-COMPATIBLE *vision* client (GPT-4o, Gemini, GLM-4V, a local
    LLaVA server...). Then just tell it what to do:

        from openai import OpenAI
        import ezos

        agent = ezos.VisionAgent(OpenAI(), model="gpt-4o")
        agent.do("open spotify and play karan aujla")

    Under the hood, each step: grid_screenshot() -> send the image to the model
    -> the model calls click/type/etc. with coordinates it read off the grid ->
    repeat until it replies DONE.
    """

    def __init__(self, client, model: str = "gpt-4o", instructions=None,
                 spacing: int = 100, max_steps: int = 15, persona: str = "Jarvis",
                 speak_replies: bool = False, tools: list | None = None):
        if client is None:
            raise RuntimeError("VisionAgent needs an OpenAI-compatible vision "
                               "client, e.g. ezos.VisionAgent(OpenAI()).")
        self.client = client
        self.model = model
        self.spacing = spacing
        self.max_steps = max_steps
        self.speak_replies = speak_replies
        self.width, self.height = _screen_size()
        if instructions is None:
            instructions = []
        if isinstance(instructions, str):
            instructions = [instructions]
        blocks = _collect_blocks(instructions)
        system = [_BASE_PERSONA.format(persona=persona), _VISION_RULES,
                  f"The screen is {self.width}x{self.height} pixels.",
                  f"The coordinate grid is drawn every {spacing} pixels."]
        if blocks:
            system += ["", "YOUR INSTRUCTIONS:", *(f"- {b}" for b in blocks)]
        self.system_prompt = "\n".join(system)
        self.tools = openai_tools(only=tools or _VISION_TOOLS)
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def _trim_old_images(self) -> None:
        """Keep only the newest screenshot so context stays small and cheap."""
        imgs = [m for m in self.messages
                if m.get("role") == "user" and isinstance(m.get("content"), list)]
        for m in imgs[:-1]:
            m["content"] = [c for c in m["content"]
                            if isinstance(c, dict) and c.get("type") == "text"]

    def _attach_screen(self, note: str) -> None:
        shot = grid_screenshot("ezos_vision.png", spacing=self.spacing)
        content = [{"type": "text", "text": note}]
        if shot.get("ok") and shot.get("path"):
            try:
                content.append({"type": "image_url",
                                "image_url": {"url": _data_uri(shot["path"])}})
            except Exception:
                pass
        self.messages.append({"role": "user", "content": content})

    def do(self, task: str) -> str:
        """Carry out an on-screen task described in plain language."""
        self.messages.append({"role": "user", "content": f"TASK: {task}"})
        last = ""
        for step in range(self.max_steps):
            self._trim_old_images()
            self._attach_screen(
                f"Screen now (step {step + 1}/{self.max_steps}). Take the next "
                f"single action, or reply DONE when the task is complete.")
            resp = self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=self.tools)
            msg = resp.choices[0].message
            if not getattr(msg, "tool_calls", None):
                last = msg.content or ""
                self.messages.append({"role": "assistant", "content": last})
                if self.speak_replies and last:
                    speak(last)
                return last
            self.messages.append(msg)
            self.messages += handle_openai_tool_calls(msg.tool_calls)
            time.sleep(0.4)  # let the UI react before the next screenshot
        return last or "(stopped: too many steps)"

    # friendly alias so it reads like Jarvis
    chat = do


# ===========================================================================
# 11. EXTRAS   (notify / speak / reminders / wait)
# ===========================================================================
def notify(title: str, message: str) -> dict:
    """Show a desktop notification / message box."""
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
        elif IS_MAC:
            subprocess.run(["osascript", "-e",
                            f'display notification "{message}" with title "{title}"'])
        else:
            subprocess.run(["notify-send", title, message])
        return _ok("Notification shown")
    except Exception as e:
        return _fail(f"notify failed: {e}")


def toast(message: str, title: str = "ezos") -> dict:
    """A non-blocking Windows toast notification (doesn't freeze your script)."""
    if not IS_WINDOWS:
        return notify(title, message)
    try:
        safe_t = title.replace("'", "''")
        safe_m = message.replace("'", "''")
        ps = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
            " ContentType = WindowsRuntime] > $null;"
            "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{safe_t}')) > $null;"
            f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{safe_m}')) > $null;"
            "$n = [Windows.UI.Notifications.ToastNotification]::new($t);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('ezos').Show($n);"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
        return _ok("Toast shown")
    except Exception as e:
        return _fail(f"toast failed: {e}")


def speak(text: str) -> dict:
    """Say text out loud using the computer's text-to-speech voice.

    Multi-line text (e.g. a triple-quoted string) is fine - newlines are
    flattened to spaces so it reads as one natural sentence.
    """
    spoken = " ".join(text.split())  # collapse newlines/extra spaces
    try:
        if IS_WINDOWS:
            safe = spoken.replace("'", "''")
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                 f".Speak('{safe}')"], check=True)
        elif IS_MAC:
            subprocess.run(["say", spoken])
        else:
            subprocess.run(["espeak", spoken])
        return _ok("Spoke text")
    except Exception as e:
        return _fail(f"speak failed: {e}")


def say_time() -> dict:
    """Speak the current time out loud."""
    t = datetime.datetime.now().strftime("%I:%M %p")
    speak(f"The time is {t}")
    return _ok(f"Said the time: {t}")


def say_date() -> dict:
    """Speak today's date out loud."""
    d = datetime.date.today().strftime("%A, %B %d, %Y")
    speak(f"Today is {d}")
    return _ok(f"Said the date: {d}")


def reminder(seconds: float, message: str, title: str = "Reminder",
             announce: bool = True) -> dict:
    """Pop a reminder (and optionally speak it) after N seconds. Non-blocking.

        ezos.reminder(600, "Take a break")   # in 10 minutes
    """
    def fire():
        toast(message, title)
        if announce:
            speak(message)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    when = (datetime.datetime.now() +
            datetime.timedelta(seconds=seconds)).strftime("%H:%M:%S")
    return _ok(f"Reminder set for {when}: '{message}'")


def set_timer(seconds: float, message: str = "Timer finished!") -> dict:
    """Start a countdown timer that alerts you when it ends. Non-blocking."""
    return reminder(seconds, message, title="Timer")


def whatsapp_message(number: str, message: str) -> dict:
    """Open a WhatsApp chat pre-filled with a message (you press Send).

    number: full international number, e.g. '14155552671' (no + or spaces).
    """
    url = f"https://wa.me/{number}?text={quote(message)}"
    webbrowser.open(url)
    return _ok("Opened WhatsApp chat - press Enter/Send to deliver the message")


def wait(seconds: float) -> dict:
    """Pause for a number of seconds (handy between automation steps)."""
    time.sleep(seconds)
    return _ok(f"Waited {seconds}s")


# ===========================================================================
# 12. AI  INTEGRATION   (so your LLM/Jarvis can call everything by name)
# ===========================================================================
_META = {"set_verbose", "run", "list_commands", "describe_commands", "help_me",
         "openai_tools", "anthropic_tools", "execute_tool_call",
         "handle_openai_tool_calls", "ai_read", "configure", "explain", "Jarvis",
         "give_cursor", "give_keyboard", "VisionAgent"}


def _primary_commands() -> dict[str, types.FunctionType]:
    """All public commands keyed by their real (snake_case) name."""
    cmds = {}
    for name, obj in globals().items():
        if (isinstance(obj, types.FunctionType) and not name.startswith("_")
                and obj.__name__ == name and obj.__module__ == __name__
                and name not in _META):
            cmds[name] = obj
    return cmds


def list_commands() -> list[str]:
    """Every command name ezos exposes (great for showing an AI its toolbox)."""
    return sorted(_primary_commands())


def describe_commands() -> list[dict]:
    """Structured description of every command: name, params, one-line doc.

    Feed this to an LLM so it knows exactly what tools it can call via run().
    """
    import inspect
    out = []
    for name, fn in sorted(_primary_commands().items()):
        sig = inspect.signature(fn)
        params = []
        for p in sig.parameters.values():
            params.append({
                "name": p.name,
                "required": p.default is inspect.Parameter.empty
                            and p.kind != p.VAR_POSITIONAL,
                "default": None if p.default is inspect.Parameter.empty else p.default,
            })
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        out.append({"name": name, "doc": doc, "params": params})
    return out


def run(command: str, **kwargs) -> dict:
    """Call any ezos command by name. Perfect for AI function-calling.

        ezos.run("open_app", app_name="spotify")
        ezos.run("search_web", query="news", browser="chrome")
        ezos.run("weather", city="Tokyo")
    """
    import inspect
    fn = globals().get(command)
    if not isinstance(fn, types.FunctionType) or command.startswith("_"):
        close = [c for c in list_commands() if command.lower() in c]
        return _fail(f"Unknown command '{command}'."
                     + (f" Did you mean: {', '.join(close[:5])}?" if close else ""))
    try:
        # support *args commands like hotkey(*keys): a list kwarg gets splatted
        var_pos = [p.name for p in inspect.signature(fn).parameters.values()
                   if p.kind == p.VAR_POSITIONAL]
        if var_pos and var_pos[0] in kwargs:
            seq = kwargs.pop(var_pos[0])
            seq = seq if isinstance(seq, (list, tuple)) else [seq]
            result = fn(*seq, **kwargs)
        else:
            result = fn(**kwargs)
        # normalise non-dict returns so AI always gets structured output
        if isinstance(result, dict):
            return result
        return {"ok": True, "message": f"{command} ran", "result": result}
    except TypeError as e:
        return _fail(f"Bad arguments for '{command}': {e}")
    except Exception as e:
        return _fail(f"'{command}' raised: {e}")


def help_me() -> None:
    """Print every command grouped, for a quick human overview."""
    cmds = describe_commands()
    print(f"ezos v{__version__} - {len(cmds)} commands:\n")
    for c in cmds:
        args = ", ".join(p["name"] for p in c["params"])
        print(f"  ezos.{c['name']}({args})")
        if c["doc"]:
            print(f"        {c['doc']}")


# ===========================================================================
# 13. WEB  RESEARCH   (DuckDuckGo search + BeautifulSoup page reading)
# ===========================================================================
def web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> list[dict]:
    """Search the web and return results WITHOUT opening a browser.

    Each result is {"title":.., "url":.., "snippet":..}. Great for letting
    your AI actually find information instead of just opening a search page.
    Needs:  pip install ddgs
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # older package name
    except ImportError:
        _fail("web_search needs:  pip install ddgs")
        return []
    try:
        with DDGS() as d:
            raw = list(d.text(query, max_results=max_results, region=region))
        return [{"title": r.get("title", ""),
                 "url": r.get("href") or r.get("url", ""),
                 "snippet": r.get("body", "")} for r in raw]
    except Exception as e:
        _fail(f"web_search failed: {e}")
        return []


def read_webpage(url: str, max_chars: int = 5000) -> str:
    """Fetch a web page and return its clean, readable text (no HTML tags).

    Uses BeautifulSoup. Needs:  pip install beautifulsoup4
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _fail("read_webpage needs:  pip install beautifulsoup4")
        return ""
    try:
        html = _http_get(url, timeout=20)
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "noscript", "svg", "form", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        clean = "\n".join(lines)
        return clean[:max_chars]
    except Exception as e:
        _fail(f"read_webpage failed: {e}")
        return ""


def research(query: str, max_results: int = 3, chars_per_page: int = 1500) -> dict:
    """Full web research: search, open the top pages, and extract their text.

    Returns {"query":.., "sources":[{title,url,content}], "summary": combined text}.
    Feed 'summary' straight to your AI so it can answer from real, current info.
    Needs:  pip install ddgs beautifulsoup4
    """
    hits = web_search(query, max_results=max_results)
    sources = []
    for h in hits:
        if not h["url"]:
            continue
        content = read_webpage(h["url"], max_chars=chars_per_page)
        sources.append({"title": h["title"], "url": h["url"],
                        "content": content or h["snippet"]})
    summary = "\n\n".join(
        f"SOURCE: {s['title']}\nURL: {s['url']}\n{s['content']}" for s in sources)
    return {"query": query, "sources": sources, "summary": summary}


# ===========================================================================
# 14. AI  /  LLM   CONFIG  &  TOOL  FORMATS   (build your own Jarvis)
# ===========================================================================
def _json_type(default) -> str:
    """Map a Python default value to a JSON-schema type string."""
    import inspect
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "integer"
    if isinstance(default, float):
        return "number"
    if isinstance(default, (list, tuple)):
        return "array"
    return "string"


def _tool_schema(only: list[str] | None = None) -> list[dict]:
    """Shared JSON-schema builder for both OpenAI and Anthropic tool formats."""
    import inspect
    tools = []
    for name, fn in sorted(_primary_commands().items()):
        if only and name not in only:
            continue
        sig = inspect.signature(fn)
        props, required = {}, []
        for p in sig.parameters.values():
            if p.kind == p.VAR_POSITIONAL:   # *keys -> array of strings
                props[p.name] = {"type": "array", "items": {"type": "string"},
                                 "description": f"list of {p.name}"}
                continue
            jtype = ("string" if p.default is inspect.Parameter.empty
                     else _json_type(p.default))
            props[p.name] = {"type": jtype, "description": f"{p.name} argument"}
            if p.default is inspect.Parameter.empty:
                required.append(p.name)
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        tools.append({"name": name, "description": doc,
                      "parameters": {"type": "object", "properties": props,
                                     "required": required}})
    return tools


def openai_tools(only: list[str] | None = None) -> list[dict]:
    """ezos commands as OpenAI function-calling tools (the `tools=` argument).

        tools = ezos.openai_tools()
        resp = client.chat.completions.create(model=..., tools=tools, messages=...)
    Pass `only=[...]` to expose just a subset of commands.
    """
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["parameters"]}}
            for t in _tool_schema(only)]


def anthropic_tools(only: list[str] | None = None) -> list[dict]:
    """ezos commands as Anthropic (Claude) tools (the `tools=` argument)."""
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]} for t in _tool_schema(only)]


def execute_tool_call(name: str, arguments) -> dict:
    """Run a tool call chosen by an LLM. `arguments` may be a dict or JSON string.

        ezos.execute_tool_call("open_app", '{"app_name": "spotify"}')
        ezos.execute_tool_call("search_web", {"query": "news"})
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as e:
            return _fail(f"Bad JSON arguments for '{name}': {e}")
    if not isinstance(arguments, dict):
        arguments = {}
    return run(name, **arguments)


def handle_openai_tool_calls(tool_calls) -> list[dict]:
    """Execute a list of OpenAI tool_calls and return 'tool' role messages.

    Append the returned list to your messages before the next model call:

        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(msg)
            messages += ezos.handle_openai_tool_calls(msg.tool_calls)
    """
    out = []
    for tc in tool_calls:
        name = tc.function.name
        result = execute_tool_call(name, tc.function.arguments)
        out.append({"role": "tool", "tool_call_id": tc.id, "name": name,
                    "content": json.dumps(result, default=str)})
    return out


_BASE_PERSONA = (
    "You are {persona}, a voice/chat assistant that controls the user's Windows "
    "PC through the `ezos` toolbox. You can open and close apps, control the "
    "browser, search and research the web, manage files and windows, control "
    "media and volume, and speak out loud.\n"
)

_BASE_RULES = (
    "HOW TO ACT:\n"
    "- To DO something on the PC, call the matching ezos tool. Prefer one tool "
    "call per step; for multi-step requests (e.g. 'open chrome and search X'), "
    "call the tools in order.\n"
    "- To ANSWER a question that needs current/real info, call `research` (or "
    "`web_search`) first, then answer from the results. Don't guess.\n"
    "- Every tool returns {\"ok\": true/false, ...}. If ok is false, read the "
    "message, fix the arguments, and try again or tell the user.\n"
    "- Open apps by simple name: open_app('spotify'), open_app('chrome').\n"
    "- To search the web in a browser use search_web(query, browser='chrome'); "
    "to read info yourself use research(query).\n"
    "- Keep spoken replies short and natural. Confirm BEFORE destructive actions "
    "(delete_file, delete_folder, shutdown, empty_recycle_bin).\n"
    "- Never invent tool names; only use the tools provided.\n"
)


def ai_read(instructions: str = "", persona: str | None = None) -> str:
    """Make ONE instruction block for the AI to read / follow.

    Two uses:
      * ezos.aiRead("Always call me boss. Prefer Chrome.")
            -> wraps your text as a rule block for the AI.
      * ezos.aiRead("open_app")
            -> returns the detailed instructions for ONE command, so the AI can
               "read the open_app function" before using it.

    Build as MANY of these as you want and hand them all to ezos.configure():

        cfg = ezos.configure(
            ezos.aiRead("Call me boss."),
            ezos.aiRead("Prefer Chrome for browsing."),
            ezos.aiRead("Always research() before answering factual questions."),
        )
    """
    text = instructions.strip()
    if text in _primary_commands():            # a command name -> its own instructions
        return explain(text)
    if persona and text:
        return f"[{persona}] {text}"
    return text


def _tool_manifest() -> str:
    """The 'you have these tools, and here's what each one does' section."""
    lines = ["TOOLS YOU CAN USE — call any of these to act. "
             "Each line is  name(params) — what it does:"]
    for c in describe_commands():
        args = ", ".join(p["name"] for p in c["params"])
        lines.append(f"  - {c['name']}({args}) — {c['doc']}")
    return "\n".join(lines)


def _collect_blocks(blocks) -> list[str]:
    """Flatten strings / lists / aiRead() results into a clean list of blocks."""
    out: list[str] = []
    for b in blocks:
        if b is None:
            continue
        if isinstance(b, (list, tuple)):
            out.extend(str(x).strip() for x in b if str(x).strip())
        elif str(b).strip():
            out.append(str(b).strip())
    return out


def configure(*instructions, persona: str = "Jarvis",
              provider: str = "openai") -> dict:
    """Configure an AI with the ezos toolbox.

    This is what tells the AI "you have these tools you can use" (every function,
    with an instruction for each), plus any rules you add on top.

    Pass ANY NUMBER of instruction blocks — plain strings and/or ezos.aiRead(...)
    results. They're combined in order:

        cfg = ezos.configure(
            ezos.aiRead("Call me boss."),
            ezos.aiRead("Prefer Chrome."),
            "Confirm before deleting anything.",
            provider="openai",
        )
        cfg["system_prompt"]   # -> the system message for your LLM
        cfg["tools"]           # -> tools in the chosen format

    provider="openai" gives the OpenAI-COMPATIBLE tool format — the same format
    used by OpenAI, Google Gemini, Z.ai, Groq, Together, and local servers
    (point your client's base_url at them). provider="anthropic" gives Claude's
    native tool format.
    """
    blocks = _collect_blocks(instructions)
    parts = [_BASE_PERSONA.format(persona=persona), _BASE_RULES, "", _tool_manifest()]
    if blocks:
        parts += ["", "YOUR INSTRUCTIONS (follow these):",
                  *(f"- {b}" for b in blocks)]
    system_prompt = "\n".join(parts)
    tools = anthropic_tools() if provider == "anthropic" else openai_tools()
    return {"system_prompt": system_prompt, "tools": tools, "provider": provider,
            "command_count": len(list_commands()), "instructions": blocks}


def explain(command: str) -> str:
    """Detailed help for one command: its signature, doc, and an example.

    'If the AI has to open Chrome, it can read the open_app function.'
    """
    fn = globals().get(command)
    if not isinstance(fn, types.FunctionType):
        return f"No command named '{command}'. See ezos.list_commands()."
    import inspect
    sig = str(inspect.signature(fn))
    doc = (fn.__doc__ or "").strip()
    return f"ezos.{command}{sig}\n\n{doc}"


# ===========================================================================
# 15. Jarvis  -  the ready-made agent loop (bring your own LLM client)
# ===========================================================================
class Jarvis:
    """A complete tool-using assistant loop, so you tell it things and it acts.

    Uses the OpenAI-COMPATIBLE API, so it works with OpenAI, Google Gemini,
    Z.ai, Groq, Together, OpenRouter, and local servers — just build the client
    with the right base_url and model:

        from openai import OpenAI
        import ezos

        # OpenAI:
        client = OpenAI()
        # Gemini (OpenAI-compatible endpoint):
        # client = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        #                 api_key=GEMINI_KEY)   ; model="gemini-2.0-flash"
        # Z.ai:
        # client = OpenAI(base_url="https://api.z.ai/api/paas/v4/", api_key=ZAI_KEY)
        #                 model="glm-4.6"

        jarvis = ezos.Jarvis(
            client, model="gpt-4o-mini",
            instructions=[                       # pass MANY instruction blocks
                ezos.aiRead("Call me boss."),
                ezos.aiRead("Prefer Chrome."),
                ezos.aiRead("Research before answering factual questions."),
            ],
        )
        print(jarvis.chat("open spotify and play daft punk"))
        print(jarvis.chat("what's the weather in Tokyo and who won the match today?"))

    No client? Pass none and use .keyword(text) for an offline keyword demo.
    """

    def __init__(self, client=None, model: str = "gpt-4o-mini",
                 instructions=None, persona: str = "Jarvis",
                 provider: str = "openai", speak_replies: bool = False,
                 max_steps: int = 8):
        self.client = client
        self.model = model
        self.speak_replies = speak_replies
        self.max_steps = max_steps
        if instructions is None:
            instructions = []
        if isinstance(instructions, str):
            instructions = [instructions]
        cfg = configure(*instructions, persona=persona, provider=provider)
        self.system_prompt = cfg["system_prompt"]
        self.tools = cfg["tools"]
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def chat(self, user_text: str) -> str:
        """Send a message; ezos runs any tools the model picks; returns the reply."""
        if self.client is None:
            raise RuntimeError(
                "Jarvis has no LLM client. Pass one (e.g. ezos.Jarvis(OpenAI())) "
                "or use jarvis.keyword(text) for the offline demo.")
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(self.max_steps):
            resp = self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=self.tools)
            msg = resp.choices[0].message
            if not getattr(msg, "tool_calls", None):
                reply = msg.content or ""
                self.messages.append({"role": "assistant", "content": reply})
                if self.speak_replies and reply:
                    speak(reply)
                return reply
            # model wants to use tools -> run them and feed results back
            self.messages.append(msg)
            self.messages += handle_openai_tool_calls(msg.tool_calls)
        return "(stopped: too many tool steps)"

    def keyword(self, text: str) -> dict:
        """Tiny offline intent matcher (no LLM). Handy for testing the wiring."""
        t = text.lower().strip()
        if t.startswith("open "):
            return run("open_app", app_name=t[5:].strip())
        if "research" in t:
            return {"ok": True, "message": research(t.replace("research", "").strip())["summary"][:800]}
        if "search" in t or "google" in t:
            q = t.replace("search for", "").replace("search", "").replace("google", "").strip()
            return run("search_web", query=q, browser="chrome")
        if t.startswith("play "):
            return run("play_on_youtube", query=t[5:].strip())
        if "weather" in t:
            return {"ok": True, "message": weather(t.replace("weather in", "").replace("weather", "").strip())}
        if "time" in t:
            return run("say_time")
        if "volume up" in t:
            return run("volume_up", steps=10)
        if "volume down" in t:
            return run("volume_down", steps=10)
        if "screenshot" in t:
            return run("screenshot", save_as="jarvis_shot.png")
        if "lock" in t:
            return run("lock_screen")
        return {"ok": False, "message": f"Didn't understand: '{text}'"}


# ===========================================================================
#  camelCase aliases  (ezos.createFile and ezos.create_file both work)
# ===========================================================================
createFile = create_file;           readFile = read_file
writeFile = write_file;             appendFile = append_file
deleteFile = delete_file;           copyFile = copy_file
moveFile = move_file;               renameFile = rename_file
fileExists = file_exists;           listFiles = list_files
findFile = find_file;               createFolder = create_folder
deleteFolder = delete_folder;       zipFiles = zip_files
openFile = open_file;               openFolder = open_folder
openApp = open_app;                 closeApp = close_app
isAppRunning = is_app_running;       listRunningApps = list_running_apps
runCommand = run_command
openBrowser = open_browser;         openUrl = open_url
searchWeb = search_web;             searchYoutube = search_youtube
openWebsite = open_website;         downloadFile = download_file
publicIp = public_ip
playOnYoutube = play_on_youtube;     playOnSpotify = play_on_spotify
playPauseMedia = play_pause_media;   nextTrack = next_track
previousTrack = previous_track;      stopMedia = stop_media
systemInfo = system_info;           cpuUsage = cpu_usage
ramUsage = ram_usage;               diskSpace = disk_space
batteryStatus = battery_status;      getIp = get_ip
wifiName = wifi_name;               currentTime = current_time
currentDate = current_date
cancelShutdown = cancel_shutdown;    lockScreen = lock_screen
sleepPc = sleep_pc;                 emptyRecycleBin = empty_recycle_bin
setBrightness = set_brightness
activeWindow = active_window;        minimizeWindow = minimize_window
maximizeWindow = maximize_window;    closeWindow = close_window
showDesktop = show_desktop;         switchWindow = switch_window
copyToClipboard = copy_to_clipboard; pasteFromClipboard = paste_from_clipboard
volumeUp = volume_up;               volumeDown = volume_down
setVolume = set_volume;             setWallpaper = set_wallpaper
typeText = type_text;               pressKey = press_key
moveMouse = move_mouse
giveCursor = give_cursor;           giveKeyboard = give_keyboard
gridScreenshot = grid_screenshot
doubleClick = double_click;         rightClick = right_click
mousePosition = mouse_position
readScreen = read_screen;           findTextOnScreen = find_text_on_screen
clickText = click_text;             askUser = ask_user
apiCall = api_call;                 runPython = run_python
sendEmail = send_email
sayTime = say_time;                 sayDate = say_date
setTimer = set_timer;               whatsappMessage = whatsapp_message
listCommands = list_commands;        describeCommands = describe_commands
setVerbose = set_verbose;           helpMe = help_me
webSearch = web_search;             readWebpage = read_webpage
openaiTools = openai_tools;          anthropicTools = anthropic_tools
executeToolCall = execute_tool_call; handleOpenaiToolCalls = handle_openai_tool_calls
aiRead = ai_read;                   read = ai_read   # 'read' kept for back-compat


if __name__ == "__main__":
    print(f"ezos v{__version__} ready on {platform.system()}")
    print("System:", system_info()["computer_name"], "|",
          current_date(), current_time())
    print(f"{len(list_commands())} commands available. "
          f"Run ezos.help_me() to see them all.")
