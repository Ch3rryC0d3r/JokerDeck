"""
JokerDeck - a balatro mod manager

A simple balatro mod manager made with Python!
"""

# imports
import os
import sys
import json
import re
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import urllib.request
import zipfile
import threading
from pathlib import Path
from ctypes import windll, byref, create_unicode_buffer

try: # so pillow is optional
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# crispy text
try:
    windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass
        
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JokerDeck.App")
except Exception:
    pass        

def load_custom_font(font_filename: str) -> str:
    # loads da font
    font_path = Path(__file__).parent / font_filename
    if font_path.exists() and os.name == "nt":
        windll.gdi32.AddFontResourceExW(byref(create_unicode_buffer(str(font_path))), 0x10, 0)
        if "m6x11" in font_filename.lower():
            return "m6x11plus"
        return font_path.stem
    return "Arial"

# defaults
DEFAULT_MODS_DIR  = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Balatro", "Mods")
DEFAULT_GAME_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Balatro"
GAME_EXE_NAME     = "Balatro.exe"

# save config in the actual folder the exe sits in, not inside a temp extract path
if getattr(sys, 'frozen', False):
    CONFIG_FILE = Path(sys.executable).parent / "jokerdeck_config.json"
else:
    CONFIG_FILE = Path(__file__).parent / "jokerdeck_config.json"

IGNORE_FILE       = ".lovelyignore"
UNINSTALLED_DIR   = "Uninstalled"
SMODS_VERSIONS_DIR = "Versions"

FONT_FAMILY = load_custom_font("m6x11plus.ttf")

ACCENT   = "#cc1b3b"
ENABLED  = "#1a7f37"
DISABLED = "#8e8e93"

LIGHT = {
    "BG": "#f2f2f7", "PANEL": "#ffffff", "TEXT": "#1c1c1e",
    "SUBTEXT": "#68686e", "BORDER": "#d1d1d6", "HOVER": "#fafdff",
    "SEL_BG": "#fff0f3", "SEL_BDR": "#cc1b3b",
}
DARK = {
    "BG": "#1c1c1e", "PANEL": "#2c2c2e", "TEXT": "#f2f2f7",
    "SUBTEXT": "#98989f", "BORDER": "#3a3a3c", "HOVER": "#3a3a3c",
    "SEL_BG": "#3a1a1f", "SEL_BDR": "#cc1b3b",
}

def apply_theme(dark: bool):
    # wooo, dark modee
    t = DARK if dark else LIGHT
    global BG, PANEL, TEXT, SUBTEXT, BORDER, HOVER, SEL_BG, SEL_BDR
    BG, PANEL, TEXT, SUBTEXT, BORDER, HOVER, SEL_BG, SEL_BDR = (
        t["BG"], t["PANEL"], t["TEXT"], t["SUBTEXT"],
        t["BORDER"], t["HOVER"], t["SEL_BG"], t["SEL_BDR"]
    )

# config i/o
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"mods_dir": DEFAULT_MODS_DIR, "game_path": DEFAULT_GAME_PATH, "dark_mode": False}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

_init_cfg = load_config()
apply_theme(_init_cfg.get("dark_mode", False))

# mod helpers
def _has_valid_json(entry: Path) -> bool:
    """Returns True only if the folder has at least one valid, readable JSON file."""
    for jf in entry.glob("*.json"):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                try:
                    data = json.loads(f.read().strip().rstrip(","))
                except Exception:
                    continue
            if isinstance(data, dict) and data:
                return True
        except Exception:
            pass
    return False

def get_mods(mods_dir: str) -> list[dict]:
    mods = []
    p = Path(mods_dir)
    if not p.exists():
        return mods
    for entry in sorted(p.iterdir()):
        if not entry.is_dir():
            continue

        ignore = entry / IGNORE_FILE
        mod_name = None
        description = "No description provided."
        version = ""
        author = ""

        # Hunt through ALL json files, pick the most informative
        for meta_file in entry.glob("*.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                    raw = re.sub(r",\s*([}\]])", r"\1", raw)
                    data = json.loads(raw)

                if not isinstance(data, dict):
                    continue

                temp_name = data.get("display_name") or data.get("name") or data.get("id")
                temp_desc = data.get("description")
                temp_ver  = data.get("version")
                raw_author = data.get("author")
                internal_id = data.get("id")

                # name
                if temp_name and not mod_name:
                    mod_name = temp_name

                # description
                if temp_desc and description == "No description provided.":
                    description = temp_desc

                # version
                if temp_ver and not version:
                    version = str(temp_ver)

                # author formatting
                if raw_author and not author:
                    if isinstance(raw_author, list):
                        cleaned = [str(a).strip() for a in raw_author if a]

                        if len(cleaned) == 1:
                            author = cleaned[0]
                        elif len(cleaned) == 2:
                            author = f"{cleaned[0]} & {cleaned[1]}"
                        else:
                            author = ", ".join(cleaned[:-1]) + f" & {cleaned[-1]}"
                    else:
                        author = str(raw_author)

                # stop early only if core fields are filled
                if mod_name and version and description != "No description provided.":
                    break

            except Exception:
                pass

        # Read dependency configuration arrays directly from the latest parsed valid data frame
        m_deps = []
        try:
            for meta_file in entry.glob("*.json"):
                with open(meta_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                    raw = re.sub(r",\s*([}\]])", r"\1", raw)
                    data = json.loads(raw)
                    if isinstance(data, dict) and "dependencies" in data:
                        m_deps = data["dependencies"]
                        if not isinstance(m_deps, list):
                            m_deps = [str(m_deps)]
                        break
        except Exception:
            pass

        icon_path = None
        _icon_dir = entry / "assets" / "1x"
        if _icon_dir.exists():
            _flat = sorted(_icon_dir.glob("*.png"), key=lambda p: (0 if "icon" in p.stem.lower() else 1))
            _deep = sorted(_icon_dir.rglob("*.png"), key=lambda p: (0 if "icon" in p.stem.lower() else 1))
            _icon_pool = sorted(set(_flat + _deep), key=lambda p: (0 if "icon" in p.stem.lower() else 1, str(p)))
        else:
            _icon_pool = sorted(entry.rglob("*.[Pp][Nn][Gg]"), key=lambda p: (0 if "icon" in p.stem.lower() else 1))
        for img in _icon_pool:
            try:
                if PIL_AVAILABLE:
                    with Image.open(img) as im:
                        w, h = im.size
                        if w == h and 16 < w < 48:
                            icon_path = img
                            print(f"[{entry.name}] icon={icon_path}")
                            break
                else:
                    icon_path = img
                    break
            except Exception:
                pass

        mods.append({
            "name":        str(mod_name).strip() if mod_name else entry.name,
            "path":        entry,
            "id":          entry.name, 
            "manifest_id": internal_id if internal_id else entry.name,
            "enabled":     not ignore.exists(),
            "description": description.strip(),
            "version":     str(version).strip(),
            "author":      str(author).strip(),
            "icon":        icon_path,
            "dependencies": m_deps,
        })
    return mods

def parse_conflict_id(conflict_str: str) -> str:
    # pull just the mod id out of something like "Talisman (>=1.1) (<<2~)"
    return conflict_str.strip().split("(")[0].strip()

def normalize_mod_token(name_str: str) -> str:
    s = name_str.strip().lower()
    if s.startswith("thunderstore-"):
        s = s[len("thunderstore-"):]
    s = re.sub(r'-(?:main|master)$', '', s)
    s = re.sub(r'[-_]v?\d+\.\d+.*$', '', s)
    return s.strip()

def get_dependency_tokens(dep_str: str) -> list[str]:
    # splits stuff like 'Amulet | Cryptlib' into tokens.
    raw_tokens = dep_str.split("|")
    return [normalize_mod_token(t) for t in raw_tokens if t.strip()]

def parse_dependency_requirement(dep_str: str):
    # Matches patterns like "Steamodded (>=1.0.0~BETA-1620a)"
    m = re.match(r"^([^\(]+)(?:\((>=|<=|>|<|==)\s*([^\)]+)\))?", dep_str.strip())
    if not m:
        return get_dependency_tokens(dep_str), None, None
    
    raw_name = m.group(1).strip()
    clean_names = get_dependency_tokens(raw_name)
    op = m.group(2)
    ver = m.group(3).strip() if m.group(3) else None
    return clean_names, op, ver

def compare_versions(current_ver: str, op: str, req_ver: str) -> bool:
    if not op or not req_ver:
        return True
    if not current_ver or str(current_ver).strip() in ("", "0.0.0", "unknown"):
        return True

    def parse_to_comparable_tuple(v_str):
        v_str = str(v_str).strip()
        segments = re.findall(r'\d+|[a-zA-Z]+', v_str)
        processed = []
        for seg in segments:
            if seg.isdigit():
                processed.append(int(seg))
            else:
                processed.append(seg.lower())
        return tuple(processed)

    c_parts = parse_to_comparable_tuple(current_ver)
    r_parts = parse_to_comparable_tuple(req_ver)
    
    max_len = max(len(c_parts), len(r_parts))
    c_padded = list(c_parts + (0,) * (max_len - len(c_parts)))
    r_padded = list(r_parts + (0,) * (max_len - len(r_parts)))

    for i in range(max_len):
        if type(c_padded[i]) != type(r_padded[i]):
            c_padded[i] = str(c_padded[i])
            r_padded[i] = str(r_padded[i])

    c_final = tuple(c_padded)
    r_final = tuple(r_padded)

    try:
        if op == "==": return c_final == r_final
        if op == ">=": return c_final >= r_final
        if op == "<=": return c_final <= r_final
        if op == ">":  return c_final > r_final
        if op == "<":  return c_final < r_final
    except Exception:
        pass
    return True

def find_conflicts(mods: list[dict]) -> set[str]:
    # returns paths of any mod that is in a conflict pair with another installed mod
    id_to_path = {}
    conflicts_map = {}

    for m in mods:
        mod_id = m.get("id", "").strip().lower()
        if mod_id:
            id_to_path[mod_id] = str(m["path"])
        raw_conflicts = m.get("conflicts", [])
        if isinstance(raw_conflicts, list) and raw_conflicts:
            conflicts_map[str(m["path"])] = [parse_conflict_id(c).lower() for c in raw_conflicts]

    flagged = set()
    for mod_path, conflict_ids in conflicts_map.items():
        for cid in conflict_ids:
            if cid in id_to_path:
                flagged.add(mod_path)
                flagged.add(id_to_path[cid])
    return flagged

def set_mod_enabled(mod: dict, enabled: bool):
    ignore_path = mod["path"] / IGNORE_FILE
    if enabled:
        if ignore_path.exists():
            ignore_path.unlink()
    else:
        ignore_path.touch()
    mod["enabled"] = enabled

def get_uninstalled_dir(mods_dir: str) -> Path:
    # new home is Balatro/Uninstalled/ (one level above /Mods)
    return Path(mods_dir).parent / UNINSTALLED_DIR

def uninstall_mod(mod: dict, mods_dir: str):
    # moves mod folder out of /Mods and into Balatro/Uninstalled/
    uninstalled = get_uninstalled_dir(mods_dir)
    uninstalled.mkdir(exist_ok=True)
    dest = uninstalled / mod["path"].name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(mod["path"]), str(dest))

def reinstall_mod(mod: dict, mods_dir: str):
    # moves mod folder back from wherever it ended up (new or old location) into /Mods
    dest = Path(mods_dir) / mod["path"].name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(mod["path"]), str(dest))

def get_uninstalled_mods(mods_dir: str) -> list[dict]:
    # checks both Balatro/Uninstalled/ and the old Mods/Uninstalled/ so nothing gets orphaned
    found = []
    locations = [
        get_uninstalled_dir(mods_dir),
        Path(mods_dir) / UNINSTALLED_DIR,
    ]
    for base in locations:
        if not base.exists():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            # mod-reading logic but mark it as uninstalled
            dummy = get_mods(str(base))
            for m in dummy:
                if m["path"].name == entry.name:
                    m["uninstalled"] = True
                    found.append(m)
                    break
    return found

def get_missing_dependency_status(mod: dict, all_mods: list[dict]) -> tuple[list[str], list[dict]]:
    # gets missing deps, pretty self-explanatoryr
    missing_strings = []
    fixable_mods = []
    
    if not mod.get("dependencies"): # fallback, if it doesn't have any deps
        return missing_strings, fixable_mods

    # index
    enabled_map = {}
    all_local_map = {}
    
    for m in all_mods:
        m_id = normalize_mod_token(m.get("manifest_id", ""))
        f_id = normalize_mod_token(m.get("id", ""))
        
        all_local_map[m_id] = m
        all_local_map[f_id] = m
        if m.get("enabled"):
            enabled_map[m_id] = m
            enabled_map[f_id] = m

    if hasattr(mod, "__self__") and hasattr(mod["__self__"], "cfg"):
        app = mod["__self__"]
    else:
        # Fallback tracking lookup sequence
        import __main__
        app = getattr(__main__, "app", None) or next((w for w in tk._default_root.winfo_children() if hasattr(w, "_all_smods_versions")), None)

    if app and hasattr(app, "_active_smods_version"):
        active_smods = app._active_smods_version()
        if active_smods:
            smods_ver = active_smods.get("version") or active_smods.get("version_number", "")
            enabled_map["steamodded"] = {"version": smods_ver, "enabled": True}

    # secondary sweep
    for m in all_mods:
        m_id = normalize_mod_token(m.get("manifest_id", ""))
        f_id = normalize_mod_token(m.get("id", ""))
        current_ver = m.get("version") or m.get("version_number", "")
        if m.get("enabled"):
            enabled_map[m_id] = {"version": current_ver, "enabled": True}
            enabled_map[f_id] = {"version": current_ver, "enabled": True}

    for dep_str in mod["dependencies"]:
        dep_tokens, op, req_ver = parse_dependency_requirement(dep_str)
        
        # if at least ONE of the valid tokens is satisfied
        any_satisfied = False
        potential_fixable = []
        
        for token in dep_tokens:
            if token in ["steamodded", "lovely"]:
                if token not in enabled_map:
                    any_satisfied = True
                    break
                if op and req_ver:
                    current_ver = enabled_map[token].get("version", "")
                    if compare_versions(current_ver, op, req_ver):
                        any_satisfied = True
                        break
                else:
                    any_satisfied = True
                    break
                continue

            if token in enabled_map:
                if op and req_ver:
                    current_ver = enabled_map[token].get("version", "")
                    if compare_versions(current_ver, op, req_ver):
                        any_satisfied = True
                        break
                else:
                    any_satisfied = True
                    break
            else:
                # Keep track of local copies we could turn on to fix this
                if token in all_local_map:
                    potential_fixable.append(all_local_map[token])

        if not any_satisfied:
            missing_strings.append(dep_str)
            for target_disabled_mod in potential_fixable:
                if target_disabled_mod not in fixable_mods:
                    fixable_mods.append(target_disabled_mod)

    return missing_strings, fixable_mods

# launch helpers
def launch_game(game_path: str, vanilla: bool = False):
    p = Path(game_path)
    exe = p / GAME_EXE_NAME if p.is_dir() else p
    if not exe.exists() or exe.is_dir():
        messagebox.showerror("JokerDeck", f"Balatro.exe not found at:\n{exe}\n\nCheck Settings.")
        return
    cmd = [str(exe)]
    if vanilla:
        cmd.append("--vanilla")
    try:
        subprocess.Popen(cmd, cwd=str(exe.parent))
    except Exception as e:
        messagebox.showerror("JokerDeck", f"Failed to launch:\n{e}")

# undo/redo history entry
class ToggleAction:
    def __init__(self, mod: dict, before: bool):
        self.mod = mod
        self.before = before # state BEFORE the action
        self.after = not before

# main app
class JokerDeck(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        
        # Apply the loaded configurations dynamically right away
        apply_theme(self.cfg.get("dark_mode", False))
        global DEFAULT_MODS_DIR, DEFAULT_GAME_PATH
        DEFAULT_MODS_DIR = self.cfg.get("mods_dir", DEFAULT_MODS_DIR)
        DEFAULT_GAME_PATH = self.cfg.get("game_path", DEFAULT_GAME_PATH)
        
        try:
            with open(Path(__file__).parent / "ver.json", "r") as f:
                self._version = json.load(f).get("version", "")
        except Exception:
            self._version = ""
        self.mods = []
        self._search_timer = None
        self._search_var = tk.StringVar()
        self._compact_var = tk.BooleanVar(value=self.cfg.get("compact_mode", False))
        self._sort_var = tk.StringVar(value="Name (A-Z)")

        self._all_authors = []
        self._selected_authors = set()
        self.author_btn = None

        # selection mode
        self._select_mode = False
        self._selected_mods: set = set() # set of mod paths (str)
        self._action_bar = None

        # undo/redo stacks
        self._undo_stack: list[list[ToggleAction]] = []
        self._redo_stack: list[list[ToggleAction]] = []

        # tracks when each mod was last toggled this session, for the sort
        self._toggle_times: dict[str, float] = {}

        # ui caching
        self._card_cache = []
        self._empty_label = None
        self._icon_cache: dict[str, tk.PhotoImage] = {}

        self._search_var.trace_add("write", self._on_search_change)

        self.title("JokerDeck")
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.wm_iconbitmap(default=str(icon_path))
        self.state("zoomed")
        self.minsize(700, 500)
        self.configure(bg=BG)
        self._show_splash()
        self.update()
        self.after(50, self._finish_init)

    def _show_splash(self):
        self._splash = tk.Frame(self, bg=BG)
        self._splash.place(relx=0, rely=0, relwidth=1, relheight=1)
        tk.Label(self._splash, text="JokerDeck", bg=BG, fg=ACCENT, font=(FONT_FAMILY, 48, "bold")).pack(expand=True)
        tk.Label(self._splash, text="loading...", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(pady=(0, 80))

    def _finish_init(self):
        self._build_ui()
        self._refresh_mods()
        self._splash.destroy()

    def _on_search_change(self, *args):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(150, self._render_mods)

    def _enable_all_dependencies(self, fixable_mods: list[dict]):
        if not fixable_mods:
            return
        actions = []
        for m in fixable_mods:
            actions.append(ToggleAction(m, m["enabled"]))
            set_mod_enabled(m, True)
            self._toggle_times[str(m["path"])] = tk.Tk.winfo_pointerx(self) # track activity
        
        self._undo_stack.append(actions)
        self._redo_stack.clear()
        self._update_undo_redo_btns()
        self._update_ui_state_only()
        
    # "re" build.. haha get it? no..? oh ok
    def _rebuild_ui(self):
        for widget in self.winfo_children():
            widget.destroy()
        self._card_cache = []
        self._empty_label = None
        self._icon_cache = {}
        self.configure(bg=BG)
        self._build_ui()
        
        self.update_idletasks()
        self.after(100, self._refresh_mods)
        self.after(100, self._on_sort_change)
        
    # ui build
    def _build_ui(self):
        self._style_ttk()
        self._build_header()
        self._build_toolbar()
        self._build_mod_grid()
        self._build_footer()
        self._bind_shortcuts()
        self.bind("<Button-1>", lambda e: self.focus_set() if e.widget == self or isinstance(e.widget, tk.Frame) else None)

    def _bind_shortcuts(self):
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())
        self.bind_all("<Control-a>", self._handle_control_a)
        self.bind_all("<Escape>", self._handle_escape)

    def _handle_control_a(self, event):
        focused_widget = self.focus_get()
        if isinstance(focused_widget, tk.Entry) or isinstance(focused_widget, ttk.Entry):
            return # Allow default 'Select All Text' within the text inputs
            
        # ensure we aren't accidentally firing inside a modal popup window
        if focused_widget and focused_widget.winfo_toplevel() != self:
            return

        self._select_all()

    def _handle_escape(self, event):
        focused_widget = self.focus_get()
        if focused_widget == getattr(self, "search_entry", None):
            self.focus_set()
            return
        if focused_widget and focused_widget.winfo_toplevel() == self:
            self._deselect_all()

    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        # Clean flat scrollbar
        s.configure("TScrollbar",
                     troughcolor=BG, background=BORDER,
                     arrowcolor=BG, borderwidth=0, relief="flat",
                     arrowsize=0, width=6)
        s.map("TScrollbar", background=[("active", ACCENT), ("!active", BORDER)])
        # Clean combobox
        s.configure("TCombobox",
                     fieldbackground=PANEL, background=PANEL,
                     foreground=TEXT, bordercolor=BORDER,
                     arrowcolor=SUBTEXT, relief="flat", padding=(6, 4))
        s.map("TCombobox",
              fieldbackground=[("readonly", PANEL)],
              background=[("active", PANEL), ("readonly", PANEL)],
              bordercolor=[("focus", ACCENT)])

    def _build_header(self):
        hdr = tk.Frame(self, bg=PANEL, height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="JokerDeck", bg=PANEL, fg=ACCENT, font=(FONT_FAMILY, 36, "bold")).pack(side="left", padx=(20, 8), pady=10)
        tk.Label(hdr, text=f"|  v{self._version}", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18, "bold")).pack(side="left", pady=24)

        self._btn(hdr, "⚙ Settings", self._open_settings, bg=PANEL, fg=SUBTEXT, pad=(12, 8)).pack(side="right", padx=(0, 15))
        self._btn(hdr, "🌐 Browse Mods", self._open_browse, bg=PANEL, fg=SUBTEXT, pad=(12, 8)).pack(side="right", padx=(0, 4))
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=BG, pady=12)
        bar.pack(fill="x", padx=20)

        #launcbbuttons
        self._btn(bar, "▶ Launch Modded", lambda: self._launch(vanilla=False), bg=ACCENT, fg=PANEL, font=(FONT_FAMILY, 18, "bold")).pack(side="left", padx=(0, 8))
        self._btn(bar, "Launch Vanilla",  lambda: self._launch(vanilla=True),  bg=BORDER, fg=TEXT, font=(FONT_FAMILY, 18)).pack(side="left", padx=(0, 20))

        #undo/redo stuff
        self._undo_btn = self._btn(bar, "↩", self._undo, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 20), pad=(10, 4))
        self._undo_btn.pack(side="left", padx=(0, 4))
        self._redo_btn = self._btn(bar, "↪", self._redo, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 20), pad=(10, 4))
        self._redo_btn.pack(side="left", padx=(0, 4))
        self._btn(bar, "🔄", self._refresh_mods, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 20), pad=(10, 4)).pack(side="left", padx=(0, 16))

        # Search
        search_frame = tk.Frame(bar, bg=PANEL, bd=0, highlightbackground=BORDER, highlightthickness=1)
        search_frame.pack(side="right")
        tk.Label(search_frame, text="  🔍 ", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(side="left")
        self.search_entry = tk.Entry(search_frame, textvariable=self._search_var, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 18), width=14, bd=4)
        self.search_entry.pack(side="left", padx=(0, 2))

        # compact toggle
        compact_frame = tk.Frame(bar, bg=BG)
        compact_frame.pack(side="right", padx=(0, 15))
        def toggle_compact():
            self.cfg["compact_mode"] = self._compact_var.get()
            save_config(self.cfg)
            self._render_mods()
        #tk.Checkbutton(compact_frame, text="Compact", variable=self._compact_var, command=toggle_compact, bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG, activeforeground=TEXT, font=(FONT_FAMILY, 18), relief="flat", bd=0, padx=4).pack(side="left")

        # Sort
        sort_frame = tk.Frame(bar, bg=BG)
        sort_frame.pack(side="right", padx=(0, 15))
        tk.Label(sort_frame, text="Sort: ", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(side="left")
        self.sort_combo = ttk.Combobox(sort_frame, textvariable=self._sort_var,
                                        state="readonly", font=(FONT_FAMILY, 18), width=18)
        self.sort_combo.pack(side="left")
        self.sort_combo.bind("<<ComboboxSelected>>", self._on_sort_change)
        self.author_btn = self._btn(sort_frame, "Select Authors...", self._toggle_author_popup, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18), pad=(10, 4)) # author selectionz

        self._update_sort_options()
        self._update_undo_redo_btns()

    def _update_sort_options(self):
        base_options = ["Name (A-Z)", "Name (Z-A)"]
        if self._all_authors:
            base_options.append("Only of author(s):")
        base_options.extend(["Enabled Only", "Disabled Only", "Recently Toggled", "Uninstalled"])
        
        current_selection = self._sort_var.get()
        self.sort_combo.configure(values=base_options)
        if current_selection not in base_options:
            self._sort_var.set("Name (A-Z)")

    def _on_sort_change(self, event=None):
        self.sort_combo.selection_clear()
        self.focus_set()
        if self._sort_var.get() == "Only of author(s):":
            self.author_btn.pack(side="left", padx=(8, 0))
        else:
            self.author_btn.pack_forget()
            self._selected_authors.clear()
        self._render_mods()

    def _toggle_author_popup(self):
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.configure(bg=PANEL, bd=1, highlightbackground=BORDER, highlightthickness=1)
        x = self.author_btn.winfo_rootx()
        y = self.author_btn.winfo_rooty() + self.author_btn.winfo_height()
        popup.geometry(f"280x320+{x}+{y}")
        popup.focus_set()

        def check_focus(event):
            popup.after(10, lambda: _validate_focus())
        def _validate_focus():
            try:
                focused = popup.focus_get()
                if focused and not str(focused).startswith(str(popup)):
                    popup.destroy()
            except Exception:
                pass
        popup.bind("<FocusOut>", check_focus)

        search_var = tk.StringVar()
        entry_frame = tk.Frame(popup, bg=BG, bd=0, highlightbackground=BORDER, highlightthickness=1)
        entry_frame.pack(fill="x", padx=8, pady=8)
        tk.Label(entry_frame, text=" 🔍 ", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(side="left")
        entry = tk.Entry(entry_frame, textvariable=search_var, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 18), bd=2)
        entry.pack(side="left", fill="x", expand=True)
        entry.focus()

        list_container = tk.Frame(popup, bg=PANEL)
        list_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(list_container, bg=PANEL, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        scroll_frame = tk.Frame(canvas, bg=PANEL)
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))

        def populate_authors(*args):
            for child in scroll_frame.winfo_children():
                child.destroy()
            query = search_var.get().strip().lower()
            for author in self._all_authors:
                if query and query not in author.lower():
                    continue
                is_checked = author in self._selected_authors
                var = tk.BooleanVar(value=is_checked)
                cb = tk.Checkbutton(scroll_frame, text=author, variable=var, bg=PANEL, fg=TEXT,
                                     selectcolor=PANEL, activebackground=HOVER, activeforeground=TEXT,
                                     font=(FONT_FAMILY, 18), anchor="w", relief="flat", bd=0, padx=4, pady=2)
                cb.pack(fill="x", anchor="w")
                def make_toggle_cmd(a=author, v=var):
                    if v.get():
                        self._selected_authors.add(a)
                    else:
                        self._selected_authors.discard(a)
                    self._render_mods()
                cb.configure(command=make_toggle_cmd)
        search_var.trace_add("write", populate_authors)
        populate_authors()

    def _build_mod_grid(self):
        container = tk.Frame(self, bg=BG)

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        canvas_frame = tk.Frame(container, bg=BG)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=BG, bd=0, highlightthickness=0, relief="flat")
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.mod_frame = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.mod_frame, anchor="nw")
        self.mod_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda _: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda _: self.canvas.unbind_all("<MouseWheel>"))
        self.mod_frame.columnconfigure(0, weight=1, uniform="group1")
        self.mod_frame.columnconfigure(1, weight=1, uniform="group1")

        # Bottom action bar for select mode (hidden by default)
        self._action_bar = tk.Frame(self, bg=PANEL, height=56)
        tk.Frame(self._action_bar, bg=BORDER, height=1).pack(fill="x", side="top")
        inner = tk.Frame(self._action_bar, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=20)
        self._sel_count_lbl = tk.Label(inner, text="0 selected", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18))
        self._sel_count_lbl.pack(side="left", padx=(0, 16))
        self._bulk_uninstall_btn = self._btn(inner, "🗑 Uninstall",  self._bulk_uninstall,  bg=BG,    fg=ACCENT,   font=(FONT_FAMILY, 18), pad=(12, 6))
        self._bulk_uninstall_btn.pack(side="left", padx=(0, 6))
        self._btn(inner, "🟩 Enable",     self._bulk_enable,     bg=BG,    fg=ENABLED,  font=(FONT_FAMILY, 18), pad=(12, 6)).pack(side="left", padx=(0, 6))
        self._btn(inner, "🟥 Disable",    self._bulk_disable,    bg=BG,    fg=ACCENT,   font=(FONT_FAMILY, 18), pad=(12, 6)).pack(side="left", padx=(0, 6))
        self._btn(inner, "Select All",    self._select_all,     bg=PANEL, fg=SUBTEXT,  font=(FONT_FAMILY, 18), pad=(12, 6)).pack(side="right", padx=(0, 6))
        self._btn(inner, "Deselect All",  self._deselect_all,   bg=PANEL, fg=SUBTEXT,  font=(FONT_FAMILY, 18), pad=(12, 6)).pack(side="right")

    def _build_footer(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = tk.Frame(self, bg=PANEL, height=30)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(footer, textvariable=self.status_var, bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18), anchor="w").pack(side="left", padx=15)
        self.mod_count_var = tk.StringVar(value="")
        tk.Label(footer, textvariable=self.mod_count_var, bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(side="right", padx=15)

    # select mode
    def _toggle_select_mode(self):
        self._select_mode = not self._select_mode
        if self._select_mode:
            self._select_btn.configure(text="⚫ Select", fg=ACCENT)
            self._action_bar.pack(fill="x", before=self.winfo_children()[-1])
        else:
            self._selected_mods.clear()
            self._select_btn.configure(text="⚪ Select", fg=TEXT)
            self._action_bar.pack_forget()
            self._render_mods()
        self._render_mods()

    def _toggle_card_selection(self, mod: dict, ui: dict):
        key = str(mod["path"])
        if key in self._selected_mods:
            self._selected_mods.discard(key)
            ui["card"].configure(highlightbackground=BORDER, bg=PANEL)
            ui["top"].configure(bg=PANEL)
            ui["name"].configure(bg=PANEL)
            ui["desc"].configure(bg=PANEL)
            ui["meta"].configure(bg=PANEL)
            ui["select_btn"].configure(text="⚪", bg=PANEL)
        else:
            self._selected_mods.add(key)
            ui["card"].configure(highlightbackground=SEL_BDR, bg=SEL_BG)
            ui["top"].configure(bg=SEL_BG)
            ui["name"].configure(bg=SEL_BG)
            ui["desc"].configure(bg=SEL_BG)
            ui["meta"].configure(bg=SEL_BG)
            ui["select_btn"].configure(text="⚫", bg=SEL_BG)
        self._sel_count_lbl.configure(text=f"{len(self._selected_mods)} selected")
        if self._selected_mods:
            self._action_bar.pack(fill="x")
            self._update_bulk_uninstall_btn_text()
        else:
            self._action_bar.pack_forget()

    def _update_bulk_uninstall_btn_text(self):
        sel = self._get_selected_mods()
        if sel and all(m.get("uninstalled") for m in sel):
            self._bulk_uninstall_btn.configure(text="🟩 Install", fg=ENABLED)
        else:
            self._bulk_uninstall_btn.configure(text="🗑 Uninstall", fg=ACCENT)

    def _select_all(self):
            sort_mode = self._sort_var.get()
            pool = get_uninstalled_mods(self.cfg["mods_dir"]) if sort_mode == "Uninstalled" else self.mods
            for m in pool:
                self._selected_mods.add(str(m["path"]))
            self._sel_count_lbl.configure(text=f"{len(self._selected_mods)} selected")
      
            self._action_bar.pack(fill="x")
            self._update_bulk_uninstall_btn_text()
            self._render_mods()

    def _deselect_all(self):
        self._selected_mods.clear()
        self._sel_count_lbl.configure(text="0 selected")
        self._action_bar.pack_forget()
        for ui in self._card_cache:
            ui["select_btn"].configure(text="⚪", bg=PANEL)
        self._render_mods()

    def _get_selected_mods(self) -> list[dict]:
        pool = self.mods + get_uninstalled_mods(self.cfg["mods_dir"])
        return [m for m in pool if str(m["path"]) in self._selected_mods]

    def _update_ui_state_only(self):
        """Updates states, error cards, and button toggles inline without layout resets."""
        # Refresh master state list references
        self.mods = get_mods(self.cfg["mods_dir"])
        
        # Build lookup map
        mod_map = {str(m["path"]): m for m in self.mods}
        
        # Re-verify each card layout component cached during rendering loops
        for item in self._card_cache:
            m_path_str = item.get("mod_path")
            if m_path_str not in mod_map:
                continue
                
            updated_mod = mod_map[m_path_str]
            # Update background state indicators
            bg_color = PANEL if updated_mod["enabled"] else BG
            
            # Recalculate missing dependencies
            missing_strings, fixable_mods = get_missing_dependency_status(updated_mod, self.mods)
            
            # Redraw missing warnings or clean labels inline
            if "error_label" in item and item["error_label"].winfo_exists():
                if missing_strings and updated_mod["enabled"]:
                    item["error_label"].configure(text=f"Missing deps: {', '.join(missing_strings)}", fg=ACCENT)
                else:
                    item["error_label"].configure(text="")

            # Update Action Buttons dynamically
            if "toggle_btn" in item and item["toggle_btn"].winfo_exists():
                if updated_mod["enabled"]:
                    item["toggle_btn"].configure(text="🟥 Disable Mod", fg=ACCENT)
                else:
                    item["toggle_btn"].configure(text="🟩 Enable Mod", fg=ENABLED)
                    
            # Handle conditional visibility of the Enable Deps assistance button
            if "dep_btn" in item and item["dep_btn"].winfo_exists():
                if updated_mod["enabled"] and missing_strings and len(fixable_mods) == len(missing_strings):
                    item["dep_btn"].pack(side="right", padx=4)
                    # Re-bind clean closures referencing the fresh array references
                    item["dep_btn"].configure(command=lambda f=fixable_mods: self._enable_all_dependencies(f))
                else:
                    item["dep_btn"].pack_forget()
                    
        self._update_undo_redo_btns()

    def _bulk_enable(self):
        sel = self._get_selected_mods()
        if not sel:
            return
        batch = [ToggleAction(m, m["enabled"]) for m in sel if not m["enabled"]]
        for m in sel:
            set_mod_enabled(m, True)
        if batch:
            self._push_undo(batch)
        self._render_mods()
        self.status_var.set(f"Enabled {len(sel)} mod(s).")

    def _bulk_disable(self):
        sel = self._get_selected_mods()
        if not sel:
            return
        batch = [ToggleAction(m, m["enabled"]) for m in sel if m["enabled"]]
        for m in sel:
            set_mod_enabled(m, False)
        if batch:
            self._push_undo(batch)
        self._render_mods()
        self.status_var.set(f"Disabled {len(sel)} mod(s).")

    def _bulk_uninstall(self):
        sel = self._get_selected_mods()
        if not sel:
            return
        
        is_install_mode = all(m.get("uninstalled") for m in sel)
        title = "Install Mods" if is_install_mode else "Uninstall Mods"
        prompt = f"Move these mods back to active Mods directory?\n\n" if is_install_mode else f"Move these mods to Uninstalled?\n\n"
        names = "\n".join(f"  • {m['name']}" for m in sel)
        
        if not messagebox.askyesno(title, prompt + names):
            return
            
        for m in sel:
            try:
                if is_install_mode:
                    reinstall_mod(m, self.cfg["mods_dir"])
                else:
                    uninstall_mod(m, self.cfg["mods_dir"])
            except Exception as e:
                action_str = "reinstall" if is_install_mode else "uninstall"
                messagebox.showerror("JokerDeck", f"Failed to {action_str} {m['name']}:\n{e}")
    
        self._selected_mods.clear()
        self._refresh_mods()
        action_done = "Installed" if is_install_mode else "Uninstalled"
        self.status_var.set(f"{action_done} {len(sel)} mod(s).")
        self._deselect_all()

    # undo / redo
    def _push_undo(self, batch: list[ToggleAction]):
        self._undo_stack.append(batch)
        self._redo_stack.clear()
        self._update_undo_redo_btns()

    def _undo(self):
        if not self._undo_stack:
            return
        batch = self._undo_stack.pop()
        for action in batch:
            set_mod_enabled(action.mod, action.before)
        self._redo_stack.append(batch)
        self._update_undo_redo_btns()
        self._render_mods()
        self.status_var.set("Undo applied.")

    def _redo(self):
        if not self._redo_stack:
            return
        batch = self._redo_stack.pop()
        for action in batch:
            set_mod_enabled(action.mod, action.after)
        self._undo_stack.append(batch)
        self._update_undo_redo_btns()
        self._render_mods()
        self.status_var.set("Redo applied.")

    def _update_undo_redo_btns(self):
        if hasattr(self, "_undo_btn"):
            self._undo_btn.configure(fg=TEXT if self._undo_stack else DISABLED)
            self._redo_btn.configure(fg=TEXT if self._redo_stack else DISABLED)

    # Smods version stuff
    def _smods_path(self) -> Path:
        return Path(self.cfg["mods_dir"]).parent / SMODS_VERSIONS_DIR

    def _active_smods(self) -> dict | None:
        mods_dir = Path(self.cfg["mods_dir"])
        if not mods_dir.exists():
            return None
        for folder in mods_dir.iterdir():
            if not folder.is_dir():
                continue
            if (folder / "version.lua").exists():
                ver = self._read_smods_ver(folder / "version.lua")
                if ver:
                    return {"folder_path": str(folder), "folder_name": folder.name, "version": ver}
        return None

    def _all_smods_versions(self) -> list[dict]:
        p = self._smods_path()
        if not p.exists():
            try: p.mkdir(parents=True, exist_ok=True)
            except: pass
            return []
        versions, seen = [], set()
        for folder in p.iterdir():
            if not folder.is_dir(): continue
            if not (folder / "version.lua").exists(): continue
            ver = self._read_smods_ver(folder / "version.lua")
            if ver and ver not in seen:
                seen.add(ver)
                versions.append({"folder_path": str(folder), "folder_name": folder.name, "version": ver})
        return versions

    @staticmethod
    def _read_smods_ver(path: Path) -> str | None:
        try:
            try:
                from luaparser import ast as luaast, astnodes
                tree = luaast.parse(path.read_text(encoding="utf-8"))
                for node in luaast.walk(tree):
                    if isinstance(node, astnodes.Return) and node.values and isinstance(node.values[0], astnodes.String):
                        raw = node.values[0].s
                        break
                else:
                    return None
            except ImportError:
                import re
                m = re.search(r'return\s+"([^"]+)"', path.read_text(encoding="utf-8"))
                if not m: return None
                raw = m.group(1)
            # turns "0.X.Y-SMODS-0.1.2" into "SMODS"
            after = raw[raw.find("-") + 1:]
            return after[:after.find("-")] if "-" in after else after
        except:
            return None

    def _switch_smods(self, target: dict):
        mods_dir = Path(self.cfg["mods_dir"])
        current = self._active_smods()

        if current:
            backup = self._smods_path() / current["folder_name"]
            if not backup.exists():
                try: shutil.copytree(current["folder_path"], str(backup))
                except Exception as e:
                    messagebox.showerror("JokerDeck", f"Couldn't back up current Smods:\n{e}"); return
            try: shutil.rmtree(current["folder_path"])
            except Exception as e:
                messagebox.showerror("JokerDeck", f"Couldn't remove current Smods:\n{e}"); return

        try: shutil.copytree(target["folder_path"], str(mods_dir / target["folder_name"]))
        except Exception as e:
            messagebox.showerror("JokerDeck", f"Couldn't install Smods {target['version']}:\n{e}"); return

        self._refresh_mods()
        self.status_var.set(f"Switched to Smods {target['version']}.")
        # If settings is currently open, redraw the selection panel instantly
        if hasattr(self, "_smods_panel_root") and self._smods_panel_root.winfo_exists():
            for child in self._smods_panel_root.winfo_children():
                child.destroy()
            self._attach_smods_selector(self._smods_panel_root)

    def _attach_smods_selector(self, parent_frame):
        versions = self._all_smods_versions()
        active = self._active_smods()
        active_ver = active["version"] if active else None

        def smods_sort_key(s):
            ver = s["version"]
            num = ''.join(c for c in ver if c.isdigit())
            letter = ''.join(c for c in ver if c.isalpha())
            return (int(num) if num else 0, letter)
        versions.sort(key=smods_sort_key)

        bar = tk.Frame(parent_frame, bg=PANEL)
        bar.pack(fill="x", pady=10)
        self._smods_bar = bar

        top = tk.Frame(bar, bg=BG)
        top.pack(fill="x", pady=(0, 4))
        tk.Label(top, text="Smods", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 16, "bold")).pack(side="left")
        if active_ver:
            tk.Label(top, text=f"  active: {active_ver}", bg=BG, fg=ENABLED, font=(FONT_FAMILY, 16)).pack(side="left")
        if not versions:
                # look for smods in the mods directory
                mods_dir = Path(self.cfg["mods_dir"])
                if mods_dir.exists():
                    for folder in mods_dir.iterdir():
                        if not folder.is_dir(): continue
                        if "smods" not in folder.name.lower(): continue
                        if not (folder / "version.lua").exists(): continue
                        ver = self._read_smods_ver(folder / "version.lua")
                        if ver:
                            versions.append({"folder_path": str(folder), "folder_name": folder.name, "version": ver})

        if not versions: # wtf do you wanna do with no smods 🙏
            tk.Label(top, text=f"  no versions found in '{SMODS_VERSIONS_DIR}/'", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 16)).pack(side="left")
            tk.Frame(bar, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))
            return

        card = tk.Frame(bar, bg=PANEL, bd=0, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        tk.Frame(card, bg=ENABLED if active_ver else DISABLED, height=3).pack(fill="x")

        btns = tk.Frame(card, bg=PANEL)
        btns.pack(fill="x", padx=12, pady=8)

        for s in versions:
            is_active = s["version"] == active_ver
            btn = tk.Button(
                btns, text=s["version"],
                bg=ACCENT if is_active else BG,
                fg=PANEL if is_active else TEXT,
                activebackground=HOVER, activeforeground=TEXT,
                font=(FONT_FAMILY, 16, "bold") if is_active else (FONT_FAMILY, 16),
                relief="flat", bd=0, padx=14, pady=6,
                cursor="arrow" if is_active else "hand2",
                command=(lambda sv=s: self._switch_smods(sv)) if not is_active else lambda: None
            )
            btn.pack(side="left", padx=(0, 6))

        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x", pady=(4, 6))
        
    # card cache & render
    def _load_icon(self, icon_path: Path) -> tk.PhotoImage | None:
        key = str(icon_path)
        if key in self._icon_cache:
            return self._icon_cache[key]
        try:
            if PIL_AVAILABLE:
                img = Image.open(icon_path).convert("RGBA").resize((34, 34), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=str(icon_path))
            self._icon_cache[key] = photo
            return photo
        except Exception:
            return None

    def _get_cached_card(self, index):
        while len(self._card_cache) <= index:
            card = tk.Frame(self.mod_frame, bg=PANEL, bd=0,
                             highlightbackground=BORDER, highlightthickness=1)
            accent_bar = tk.Frame(card, bg=DISABLED, height=3)
            accent_bar.pack(fill="x")

            top = tk.Frame(card, bg=PANEL)
            top.pack(fill="x", padx=12, pady=(10, 2))

            select_btn = tk.Label(top, text="⚪", bg=PANEL, font=(FONT_FAMILY, 14), cursor="hand2")
            select_btn.pack(side="right", padx=(4, 0))

            toggle = tk.Button(top, text="", font=(FONT_FAMILY, 18, "bold"), relief="flat", bd=0, cursor="hand2")
            toggle.pack(side="right")

            icon_lbl = tk.Label(top, bg=PANEL, bd=0, relief="flat")
            icon_lbl.pack(side="left", padx=(0, 8))

            name_lbl = tk.Label(top, text="", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18, "bold"), anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)
            
            meta_lbl = tk.Label(card, text="", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18), anchor="w")
            meta_lbl.pack(fill="x", padx=12, pady=(0, 4))

            desc_lbl = tk.Label(card, text="", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 18),
                                  justify="left", anchor="nw", wraplength=310)
            desc_lbl.pack(fill="both", expand=True, padx=12, pady=(2, 12))

            ui = {
                "card": card, "accent": accent_bar, "name": name_lbl,
                "toggle": toggle, "meta": meta_lbl, "desc": desc_lbl,
                "top": top, "icon": icon_lbl, "select_btn": select_btn,
            }

            # hover — only when not in select mode
            def make_hover(u):
                def on_enter(_, u=u):
                    if not self._select_mode or str(u.get("_mod_path","")) not in self._selected_mods:
                        u["card"].configure(bg=HOVER)
                def on_leave(_, u=u):
                    if str(u.get("_mod_path","")) not in self._selected_mods:
                        u["card"].configure(bg=PANEL)
                        u["top"].configure(bg=PANEL)
                        u["name"].configure(bg=PANEL)
                        u["desc"].configure(bg=PANEL)
                        u["meta"].configure(bg=PANEL)
                        u["icon"].configure(bg=PANEL)
                for w in (card, top, name_lbl, desc_lbl, meta_lbl, icon_lbl):
                    w.bind("<Enter>", on_enter)
                    w.bind("<Leave>", on_leave)
            make_hover(ui)

            self._card_cache.append(ui)
        return self._card_cache[index]

    def _render_mods(self):
        self.canvas.yview_moveto(0)

        for cache_item in self._card_cache:
            cache_item["card"].grid_forget()
        if self._empty_label:
            self._empty_label.pack_forget()

        query = self._search_var.get().strip().lower()
        sort_mode = self._sort_var.get()

        # uninstalled view pulls from a completely different pool, not self.mods
        if sort_mode == "Uninstalled":
            uninstalled = get_uninstalled_mods(self.cfg["mods_dir"])
            filtered = []
            for m in uninstalled:
                m_name = str(m.get("name", "")).lower()
                m_desc = str(m.get("description", "")).lower()
                if query and (query not in m_name and query not in m_desc):
                    continue
                filtered.append(m)
            self._finish_render(filtered, sort_mode)
            return

        filtered = []
        for m in self.mods:
            m_name = str(m.get("name", "")).lower()
            m_desc = str(m.get("description", "")).lower()
            if query and (query not in m_name and query not in m_desc):
                continue
            if sort_mode == "Enabled Only" and not m["enabled"]:
                continue
            if sort_mode == "Disabled Only" and m["enabled"]:
                continue
            if sort_mode == "Conflicting" and str(m["path"]) not in self._conflicting_paths:
                continue
            if sort_mode == "Only of author(s):" and self._selected_authors:
                mod_authors = [a.strip() for a in m["author"].replace(" & ", ", ").split(", ")]
                if not any(auth in self._selected_authors for auth in mod_authors):
                    continue
            filtered.append(m)

        self._finish_render(filtered, sort_mode)

    def _finish_render(self, filtered, sort_mode):
        if not filtered:
            if not self._empty_label:
                self._empty_label = tk.Label(self.mod_frame, text="No modifications found.",
                                              bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18), pady=40)
            self._empty_label.pack(fill="x")
            self.mod_count_var.set(f"0 / {len(self.mods)} active")
            return

        if sort_mode == "Name (Z-A)":
            filtered.sort(key=lambda m: m["name"].lower(), reverse=True)
        elif sort_mode == "Recently Toggled":
            filtered.sort(key=lambda m: self._toggle_times.get(str(m["path"]), 0), reverse=True)
        else:
            filtered.sort(key=lambda m: m["name"].lower())

        is_uninstalled_view = sort_mode == "Uninstalled"

        # Map all active mod instances by any identifiable token signature (normalized keys)
        active_registry = {}
        for m in self.mods:
            if not m["enabled"]:
                continue
            
            # Extract everything we can match on
            tokens = set()
            if m.get("id"): tokens.add(normalize_mod_token(str(m["id"])))
            if m.get("display_name"): tokens.add(normalize_mod_token(str(m["display_name"])))
            if m.get("name"): tokens.add(normalize_mod_token(str(m["name"])))
            if m.get("path"): tokens.add(normalize_mod_token(m["path"].name))

            v_str = str(m.get("version", "")).strip()
            if not v_str or v_str.lower() in ("unknown", "0.0.0"):
                # extract sequenece
                path_digits = re.search(r'\d+\.\d+\S*', m["path"].name)
                v_str = path_digits.group(0) if path_digits else "1.0.0" # idk why you wouldnt have a `version` key but just in case
                
            for token in tokens:
                active_registry[token] = v_str

        for idx, mod in enumerate(filtered):
            row_idx = idx // 2
            col_idx = idx % 2
            ui = self._get_cached_card(idx)
            ui["_mod_path"] = str(mod["path"])

            is_conflicting = str(mod["path"]) in getattr(self, "_conflicting_paths", set())
            is_on = mod["enabled"]
            is_selected = str(mod["path"]) in self._selected_mods

            # Evaluate dependency validity using normalized tokens
            missing_deps = []
            for dep in mod.get("dependencies", []):
                dep_tokens, op, req_version = parse_dependency_requirement(dep)

                # bypass structural system conditions like "Balatro"
                if dep_tokens == ["balatro"]:
                    continue

                # check if any of the OR tokens satisfies the dep
                satisfied = False
                found_version = None
                for dep_name in dep_tokens:
                    if dep_name in active_registry:
                        if op and req_version:
                            current_installed_version = active_registry[dep_name]
                            if compare_versions(current_installed_version, op, req_version):
                                satisfied = True
                                found_version = current_installed_version
                                break
                        else:
                            satisfied = True
                            break

                if not satisfied:
                    if found_version:
                        missing_deps.append(f"{dep} (Found v{found_version})")
                    else:
                        missing_deps.append(dep)

            # missing
            if is_on and missing_deps:
                card_bg = "#441111"
                bdr = "#ff3333"
                
                ui["card"].configure(bg=card_bg, highlightbackground=bdr, highlightthickness=2)
                ui["top"].configure(bg=card_bg)
                ui["accent"].configure(bg="#ff3333")
                ui["name"].configure(text=mod["name"], bg=card_bg, fg="#ff5555")

                dep_list_str = ", ".join(missing_deps)

                ui["desc"].configure(text=f"CRITICAL ERROR: Missing required dependencies:\n -> [ {dep_list_str} ]", bg=card_bg, fg="#ffaaaa")
                ui["meta"].configure(bg=card_bg, fg="#ff8888")
                ui["icon"].configure(bg=card_bg)

                ui["toggle"].configure(
                    text="Disable Mod", fg="#ff8888", bg="#220505", 
                    activebackground="#3a1111", activeforeground="#ffaaaa",
                    command=lambda m=mod, i=idx: [set_mod_enabled(m, False), self._refresh_mods()]
                )
                ui["toggle"].pack(side="right")
                
                def make_select_cmd(m=mod, u=ui):
                    return lambda e: self._toggle_card_selection(m, u)
                ui["select_btn"].bind("<Button-1>", make_select_cmd())
                
                meta_str = f"v{mod.get('version', '')} by {mod.get('author', 'unknown')}"
                ui["meta"].configure(text=meta_str)
                ui["meta"].pack(fill="x", padx=12, pady=(0, 4))
                
                ui["card"].grid(row=row_idx, column=col_idx, padx=8, pady=8, sticky="nsew")
                continue

            # Fall back to native appearance handling if safe
            if is_selected:
                card_bg = SEL_BG
                bdr = SEL_BDR
            elif is_conflicting:
                card_bg = "#fffbe6"
                bdr = "#e6c84a"
            else:
                card_bg = PANEL
                bdr = BORDER

            ui["card"].configure(bg=card_bg, highlightbackground=bdr, highlightthickness=1)
            ui["top"].configure(bg=card_bg)
            ui["accent"].configure(bg=ACCENT if is_on else DISABLED)
            ui["name"].configure(text=mod["name"], bg=card_bg, fg=TEXT) # Reset fg in case card was recycled
            ui["desc"].configure(text=mod["description"], bg=card_bg, fg=TEXT) # Reset fg
            ui["meta"].configure(bg=card_bg, fg=SUBTEXT) # Reset fg

            if mod.get("icon"):
                photo = self._load_icon(mod["icon"])
                if photo:
                    ui["icon"].configure(image=photo, bg=card_bg)
                    ui["icon"].image = photo
                else:
                    ui["icon"].configure(image="", bg=card_bg)
            else:
                ui["icon"].configure(image="", bg=card_bg)

            # in uninstalled view, hide the active/inactive toggle entirely
            if is_uninstalled_view:
                ui["toggle"].pack_forget()
            else:
                ui["toggle"].configure(
                    text="Active" if is_on else "Inactive",
                    fg=ENABLED if is_on else DISABLED,
                    bg=PANEL, activebackground=HOVER, activeforeground=TEXT,
                    command=lambda m=mod, i=idx: self._toggle_mod_fast(m, i)
                )
                ui["toggle"].pack(side="right")

            def make_select_cmd(m=mod, u=ui):
                return lambda e: self._toggle_card_selection(m, u)
            ui["select_btn"].bind("<Button-1>", make_select_cmd())

            meta_str = ""
            if mod["version"]: meta_str += f"v{mod['version']} "
            if mod["author"]:  meta_str += f"by {mod['author']}"
            meta_str = meta_str.strip()
            if meta_str:
                ui["meta"].configure(text=meta_str)
                ui["meta"].pack(fill="x", padx=12, pady=(0, 4))
            else:
                ui["meta"].pack_forget()

            ui["card"].grid(row=row_idx, column=col_idx, padx=8, pady=8, sticky="nsew")

        enabled_c = sum(1 for m in self.mods if m["enabled"])
        self.mod_count_var.set(f"{enabled_c} / {len(self.mods)} active")

    def _toggle_mod_fast(self, mod: dict, cache_index: int):
        try:
            import time
            before = mod["enabled"]
            set_mod_enabled(mod, not mod["enabled"])
            is_on = mod["enabled"]
            self._toggle_times[str(mod["path"])] = time.time()
            self._push_undo([ToggleAction(mod, before)])

            ui = self._card_cache[cache_index]
            ui["accent"].configure(bg=ACCENT if is_on else DISABLED)
            ui["toggle"].configure(text="Active" if is_on else "Inactive",
                                    fg=ENABLED if is_on else DISABLED)
            enabled_c = sum(1 for m in self.mods if m["enabled"])
            self.mod_count_var.set(f"{enabled_c} / {len(self.mods)} active")
            self.status_var.set(f"{mod['name']} → {'Active' if is_on else 'Inactive'}")
        except Exception as e:
            messagebox.showerror("JokerDeck", f"Could not toggle status:\n{e}")

    def _launch(self, vanilla: bool):
        mode = "Vanilla" if vanilla else "Modded"
        self.status_var.set(f"Launching {mode} environment…")
        self.update()
        launch_game(self.cfg["game_path"], vanilla=vanilla)

    def _refresh_mods(self):
        self.mods = get_mods(self.cfg["mods_dir"])
        self._conflicting_paths = find_conflicts(self.mods)
        found_authors = set()
        for m in self.mods:
            if m["author"]:
                for p in m["author"].replace(" & ", ", ").split(", "):
                    cleaned = p.strip()
                    if cleaned:
                        found_authors.add(cleaned)
        self._all_authors = sorted(list(found_authors))
        if hasattr(self, "sort_combo"):
            self._update_sort_options()

        if hasattr(self, "_smods_bar"):
            self._build_smods_bar()
            
        self._render_mods()
        self.status_var.set(f"Loaded {len(self.mods)} mod(s).")
        canvas.yview_moveto(0)

    # settings
    def _open_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("1080x720")
        #win.state("zoomed")
        self.minsize(700, 500)
        win.configure(bg=PANEL)
        win.grab_set()

        # reusable thing
        def section(label):
            tk.Label(win, text=label, bg=PANEL, fg=TEXT,
                     font=(FONT_FAMILY, 18, "bold")).pack(anchor="w", padx=20, pady=(14, 2))

        # another resuable field row thingamajgi
        def path_row(parent, var: tk.StringVar, pick_fn):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill="x", padx=20, pady=(0, 4))
            tk.Entry(f, textvariable=var, bg=BG, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=(FONT_FAMILY, 18), bd=5).pack(side="left", fill="x", expand=True)
            JokerDeck._btn(f, "Browse", pick_fn, bg=BORDER, fg=TEXT).pack(side="left", padx=(6, 0))

        # exe dir
        game_var = tk.StringVar(value=self.cfg["game_path"])
        section("Balatro Executable Directory")
        path_row(win, game_var,
            lambda: game_var.set(filedialog.askdirectory(title="Select Balatro Directory",
                initialdir=self.cfg["game_path"]) or game_var.get()))

        # path field for mods, 
        mods_var = tk.StringVar(value=self.cfg["mods_dir"])
        section("Mods Directory Path")
        path_row(win, mods_var,
            lambda: mods_var.set(filedialog.askdirectory(title="Select Mods Directory",
                initialdir=self.cfg["mods_dir"]) or mods_var.get()))
                                                               
        # so the buttons actually are visible
        btn_frame = tk.Frame(win, bg=PANEL) 
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=14)
        
        section("Appearance") # (fancy word, well it's nt that fnacyy but uh, typos go brr)
        dark_var = tk.BooleanVar(value=self.cfg.get("dark_mode", False))
        dark_frame = tk.Frame(win, bg=PANEL)
        dark_frame.pack(fill="x", padx=20, pady=(0, 4))
        tk.Checkbutton(dark_frame, text="Dark Mode", variable=dark_var, bg=PANEL, fg=TEXT,
            selectcolor=PANEL, activebackground=PANEL, activeforeground=TEXT,
            font=(FONT_FAMILY, 18), relief="flat").pack(side="left")

        def save():
            self.cfg["game_path"] = game_var.get().strip()
            self.cfg["mods_dir"]  = mods_var.get().strip()
            self.cfg["dark_mode"] = dark_var.get()
            save_config(self.cfg)
            apply_theme(dark_var.get())
            
            win.destroy()
            self.after(10, self._rebuild_ui)
            self.after(20, lambda: self.status_var.set("Saved and reloaded."))

        # SMODS Section Separator
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=15, pady=10)

        # SMODS Container Panel
        smods_panel = tk.Frame(win, bg=PANEL)
        smods_panel.pack(fill="x", padx=15)
        
        # Build the selector onto this sub-frame directly
        self._attach_smods_selector(smods_panel)

        self._btn(btn_frame, "Save", save,
                  bg=ACCENT, fg=PANEL, font=(FONT_FAMILY, 18, "bold")).pack(side="right")
        self._btn(btn_frame, "Cancel", win.destroy,
                  bg=BG, fg=SUBTEXT).pack(side="right", padx=(0, 8))
        self._btn(btn_frame, "Open Mods Folder", lambda: os.startfile(mods_var.get().strip()) if os.path.isdir(mods_var.get().strip()) else messagebox.showerror("JokerDeck", "Mods folder not found."),
                  bg=BG, fg=SUBTEXT).pack(side="left")

    def _open_browse(self):
        win = tk.Toplevel(self)
        win.title("Browse Online Mods")
        win.state('zoomed')
        win.configure(bg=BG)
        
        # loading state panel
        load_frame = tk.Frame(win, bg=BG)
        load_frame.pack(fill="both", expand=True)
        load_lbl = tk.Label(load_frame, text="loading...", bg=BG, fg=TEXT, font=(FONT_FAMILY, 24))
        load_lbl.pack(expand=True)

        # main display panel (hidden during load)
        main_frame = tk.Frame(win, bg=BG)

        card_widgets = []
        image_cache = {}  # Keeps PhotoImage references alive to prevent garbage collection
        downloading_icons = set()
        icon_threads_pool = [] # Track background workers

        # Create a tiny 32x32 transparent or solid placeholder block using PIL
        placeholder_img = None
        if PIL_AVAILABLE:
            try:
                from PIL import Image, ImageTk
                placeholder_img = ImageTk.PhotoImage(Image.new("RGBA", (32, 32), (0, 0, 0, 0)))
            except Exception:
                pass

        def fetch_index_thread():
            try:
                url = "https://raw.githubusercontent.com/Ch3rryC0d3r/JokerDeckIndex/refs/heads/main/mod.json"
                proxy_handler = urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(proxy_handler)
                
                req = urllib.request.Request(url, headers={"User-Agent": "JokerDeck-Manager"})
                with opener.open(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                win.after(10, lambda: setup_browser_ui(data))
            except Exception as e:
                err_msg = f"Connection Failed:\n\n{str(e)}\n\nCheck your internet connection, and try again."
                win.after(10, lambda msg=err_msg: show_error(msg))

        def show_error(msg):
            load_lbl.configure(text=f"Error\n\n{msg}", fg="#ff5555", justify="center", wraplength=600)

        def lazy_load_visible_icons(canvas, scroll_container):
            """Calculates which cards are on screen and kicks off background icon downloads instantly."""
            if not PIL_AVAILABLE:
                return

            try:
                canvas_height = canvas.winfo_height()
                v_start, v_end = canvas.yview()
                container_total_height = scroll_container.winfo_height()
                
                scroll_top_pixel = v_start * container_total_height
                scroll_bottom_pixel = v_end * container_total_height
            except Exception:
                return

            for item in card_widgets:
                mod_id = item["id"]
                if mod_id in image_cache or mod_id in downloading_icons:
                    continue
                
                card_frame = item["frame"]
                card_y = card_frame.winfo_y()
                card_h = card_frame.winfo_height()
                
                if (card_y + card_h >= scroll_top_pixel - 100) and (card_y <= scroll_bottom_pixel + 300):
                    downloading_icons.add(mod_id)
                    t = threading.Thread(
                        target=fetch_single_icon_thread, 
                        args=(item["git_url"], mod_id, item["icon_label"]), 
                        daemon=True
                    )
                    icon_threads_pool.append(t)
                    t.start()

        def fetch_single_icon_thread(repo_url, mod_id, target_label):
            loaded_successfully = False
            try:
                img_data = None
                chosen_branch = None
                chosen_file = None
                actual_filename = ""

                # non github platforms
                if "github.com" not in repo_url.lower():
                    for br in ["main", "master"]:
                        for fallback_name in ["Icon.png", "icon.png", "Icon-1x.png", "icon-1x.png", "HangedMan_modicon.png"]:
                            try:
                                raw_url = f"{repo_url.rstrip('/')}/raw/branch/{br}/assets/1x/{fallback_name}"
                                req = urllib.request.Request(raw_url, headers={"User-Agent": "JokerDeck-Manager"})
                                with urllib.request.urlopen(req, timeout=10) as resp: # Safe 10s timeout
                                    img_data = resp.read()
                                    if img_data:
                                        actual_filename = fallback_name
                                        break
                            except Exception:
                                continue
                        if img_data:
                            break

                # github scraper
                else:
                    clean_url = repo_url.replace("https://github.com/", "").strip("/")
                    parts = clean_url.split("/")
                    if len(parts) < 2:
                        return
                    owner, repo = parts[0], parts[1]

                    # try knwn
                    fnames_to_try = ["modicon.png", "Icon.png", "icon.png", "Icon-1x.png", "icon-1x.png"]
                    
                    # Generate smart guesses using both the repository name and mod_id
                    for identifier in [repo, mod_id]:
                        if identifier:
                            for casing in [identifier, identifier.lower(), identifier.capitalize()]:
                                c_clean = casing.replace("-", "").replace("_", "")
                                fnames_to_try.extend([
                                    f"{casing}_modicon.png", f"{c_clean}_modicon.png",
                                    f"{casing}icon.png", f"{c_clean}icon.png",
                                    f"{casing}_icon.png", f"{c_clean}_icon.png",
                                    f"{casing}_Mod_Icon.png", f"{c_clean}_Mod_Icon.png"
                                ])
                    
                    # Deduplicate list while keeping order intact
                    seen = set()
                    fnames_to_try = [x for x in fnames_to_try if not (x in seen or seen.add(x))]

                    for br in ["main", "master"]:
                        for fname in fnames_to_try:
                            try:
                                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{br}/assets/1x/{fname}"
                                req = urllib.request.Request(raw_url, headers={"User-Agent": "JokerDeck-Manager"})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    if resp.status == 200:
                                        img_data = resp.read()
                                        if img_data:
                                            actual_filename = fname
                                            break
                            except Exception:
                                continue
                        if img_data:
                            break

                    # fallbakc
                    if not img_data:
                        import re
                        for br in ["main", "master"]:
                            tree_url = f"https://github.com/{owner}/{repo}/tree/{br}/assets/1x"
                            try:
                                req = urllib.request.Request(tree_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    html_content = resp.read().decode("utf-8", errors="ignore")
                                    
                                    # Scan the HTML for filenames ending in .png inside an assets/1x context
                                    png_matches = re.findall(r'assets/1x/([^"\'\s>?&#]+?\.png)', html_content, re.IGNORECASE)
                                    if png_matches:
                                        # Clean potential subpath pieces and deduplicate
                                        cleaned_files = list(set(p.split('/')[-1] for p in png_matches))
                                        # Sort to prioritize filenames containing the word "icon"
                                        sorted_pngs = sorted(cleaned_files, key=lambda p: (0 if "icon" in p.lower() else 1, p))
                                        
                                        chosen_file = sorted_pngs[0]
                                        chosen_branch = br
                                        break
                            except Exception:
                                continue

                        if chosen_file:
                            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{chosen_branch}/assets/1x/{chosen_file}"
                            try:
                                req = urllib.request.Request(raw_url, headers={"User-Agent": "JokerDeck-Manager"})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    img_data = resp.read()
                                    if img_data:
                                        actual_filename = chosen_file
                            except Exception:
                                pass

                if img_data:
                    from io import BytesIO
                    from PIL import Image, ImageTk
                    
                    im = Image.open(BytesIO(img_data)).convert("RGBA")
                    w, h = im.size
                    
                    # Square and under 48x48, OR any square image with "icon" in the filename
                    if w == h and (w <= 48 or "icon" in actual_filename.lower()):
                        if 16 < w < 48:
                            im = im.resize((32, 32), Image.Resampling.NEAREST)
                        else:
                            im = im.resize((32, 32), Image.Resampling.LANCZOS)
                        tk_img = ImageTk.PhotoImage(im)
                        win.after(5, lambda: apply_icon(mod_id, tk_img, target_label))
                        loaded_successfully = True
            except Exception:
                pass
            finally:
                if mod_id in downloading_icons:
                    downloading_icons.remove(mod_id)
                
                # If we are 1000% sure it failed or the image exceeded 48x48, kill the loader on the main GUI thread
                if not loaded_successfully:
                    def _clear_loader_safely():
                        try:
                            if target_label.winfo_exists():
                                target_label.running = False
                                target_label.pack_forget()
                        except Exception:
                            pass
                    win.after(0, _clear_loader_safely)

        def apply_icon(mod_id, tk_img, target_label):
            image_cache[mod_id] = tk_img
            try:
                if target_label.winfo_exists():
                    target_label.running = False 
                    target_label.delete("all")
                    target_label.create_image(16, 16, image=tk_img, anchor="center")
            except Exception:
                pass

        def setup_browser_ui(mod_list):
            load_frame.pack_forget()
            main_frame.pack(fill="both", expand=True, padx=15, pady=15)

            local_status = {}
            target_dir = self.cfg.get("mods_dir", "")
            if target_dir and os.path.isdir(target_dir):
                for folder in os.listdir(target_dir):
                    f_path = os.path.join(target_dir, folder)
                    if os.path.isdir(f_path):
                        is_disabled = os.path.exists(os.path.join(f_path, IGNORE_FILE))
                        v_str = "0.0.0"
                        
                        satisfied_keys = {folder.strip().lower()}
                        if folder.lower().endswith("-main"):
                            satisfied_keys.add(folder[:-5].strip().lower())
                        if folder.lower().endswith("-master"):
                            satisfied_keys.add(folder[:-7].strip().lower())

                        m_j = os.path.join(f_path, "mod.json")
                        if os.path.exists(m_j):
                            try:
                                with open(m_j, "r", encoding="utf-8") as f:
                                    jd = json.load(f)
                                    if isinstance(jd, list) and len(jd) > 0: jd = jd[0]
                                    if isinstance(jd, dict):
                                        v_str = jd.get("version", "0.0.0")
                                        if jd.get("id"):
                                            satisfied_keys.add(str(jd["id"]).strip().lower())
                                        if jd.get("name"):
                                            satisfied_keys.add(str(jd["name"]).strip().lower())
                            except Exception: pass
                        else:
                            for loose_json in Path(f_path).glob("*.json"):
                                try:
                                    with open(loose_json, "r", encoding="utf-8") as lf:
                                        ld = json.load(lf)
                                        if isinstance(ld, dict):
                                            if "version" in ld:
                                                v_str = str(ld["version"])
                                            if ld.get("id"):
                                                satisfied_keys.add(str(ld["id"]).strip().lower())
                                            if ld.get("name"):
                                                satisfied_keys.add(str(ld["name"]).strip().lower())
                                            break
                                except Exception: pass
                        
                        status_payload = {"enabled": not is_disabled, "version": v_str, "actual_folder": folder}
                        for k in satisfied_keys:
                            local_status[k] = status_payload

            top_bar = tk.Frame(main_frame, bg=BG)
            top_bar.pack(fill="x", pady=(0, 10))
            tk.Label(top_bar, text="available mods", bg=BG, fg=ACCENT, font=(FONT_FAMILY, 24, "bold"), anchor="w").pack(side="left")
            browse_count_var = tk.StringVar(value="")

            search_frm = tk.Frame(main_frame, bg=PANEL, bd=0, highlightbackground=BORDER, highlightthickness=1)
            search_frm.pack(fill="x", pady=(0, 12))
            tk.Label(search_frm, text=" 🔍 ", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14)).pack(side="left", padx=(8, 2), pady=6)
            search_box = tk.Entry(search_frm, bg=PANEL, fg=TEXT, insertbackground=TEXT, font=(FONT_FAMILY, 16), bd=0, highlightthickness=0)
            search_box.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)

            shown_bar = tk.Frame(main_frame, bg=BG)
            shown_bar.pack(fill="x", pady=(0, 4))
            tk.Label(shown_bar, textvariable=browse_count_var, bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 16), anchor="w").pack(side="left")

            canvas = tk.Canvas(main_frame, bg=BG, bd=0, highlightthickness=0)
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            scroll_container = tk.Frame(canvas, bg=BG)
            canvas.create_window((0, 0), window=scroll_container, anchor="nw")
            
            def check_width(e):
                canvas.itemconfig(1, width=e.width)
            canvas.bind("<Configure>", check_width)
            
            scroll_container.bind("<Configure>", lambda _: [
                canvas.configure(scrollregion=canvas.bbox("all")),
                win.after(100, lambda: lazy_load_visible_icons(canvas, scroll_container))
            ])

            canvas.configure(yscrollcommand=lambda *args: [
                scrollbar.set(*args), 
                lazy_load_visible_icons(canvas, scroll_container)
            ])

            def _on_mouse_wheel(event):
                if event.delta: 
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4: 
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5: 
                    canvas.yview_scroll(1, "units")
                lazy_load_visible_icons(canvas, scroll_container)

            canvas.bind_all("<MouseWheel>", _on_mouse_wheel)
            canvas.bind_all("<Button-4>", _on_mouse_wheel)
            canvas.bind_all("<Button-5>", _on_mouse_wheel)

            win.bind("<Destroy>", lambda _: [
                canvas.unbind_all("<MouseWheel>"),
                canvas.unbind_all("<Button-4>"),
                canvas.unbind_all("<Button-5>")
            ])

            BROWSE_PAGE_SIZE = 10
            browse_page_state = {"page": 0, "filtered": []}

            # pagination bar (placed between search and canvas)
            page_bar = tk.Frame(main_frame, bg=BG)
            page_bar.pack(fill="x", pady=(0, 6))
            page_prev_btn = self._btn(page_bar, "◀", lambda: go_page(browse_page_state["page"] - 1), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 16), pad=(10, 4))
            page_prev_btn.pack(side="left", padx=(0, 4))
            page_label_var = tk.StringVar(value="Page 1 / 1")
            tk.Label(page_bar, textvariable=page_label_var, bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 16)).pack(side="left", padx=4)
            page_next_btn = self._btn(page_bar, "▶", lambda: go_page(browse_page_state["page"] + 1), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 16), pad=(10, 4))
            page_next_btn.pack(side="left", padx=(4, 0))

            def render_page():
                for item in card_widgets:
                    item["frame"].pack_forget()
                page = browse_page_state["page"]
                filtered = browse_page_state["filtered"]
                total_pages = max(1, (len(filtered) + BROWSE_PAGE_SIZE - 1) // BROWSE_PAGE_SIZE)
                page = max(0, min(page, total_pages - 1))
                browse_page_state["page"] = page
                start = page * BROWSE_PAGE_SIZE
                end = start + BROWSE_PAGE_SIZE
                for item in card_widgets:
                    item["frame"].pack_forget()
                for item in filtered[start:end]:
                    item["frame"].pack(fill="x", pady=4, padx=2)
                page_label_var.set(f"Page {page + 1} / {total_pages}")
                page_prev_btn.configure(fg=TEXT if page > 0 else DISABLED)
                page_next_btn.configure(fg=TEXT if page < total_pages - 1 else DISABLED)
                canvas.yview_moveto(0)
                canvas.configure(scrollregion=canvas.bbox("all"))
                browse_count_var.set(f"{len(filtered)} shown...")
                win.after(50, lambda: lazy_load_visible_icons(canvas, scroll_container))

            def go_page(new_page):
                browse_page_state["page"] = new_page
                render_page()

            def execute_live_search(evt=None):
                q = search_box.get().lower().strip()
                browse_page_state["filtered"] = [item for item in card_widgets if q in item["name"].lower() or q in item["description"].lower()]
                browse_page_state["page"] = 0
                render_page()
            search_box.bind("<KeyRelease>", execute_live_search)

            # load data cards
            for m in mod_list:
                m_id = m.get("id", "unknown")
                card = tk.Frame(scroll_container, bg=PANEL, bd=0, highlightbackground=BORDER, highlightthickness=1)
                tk.Frame(card, bg=DISABLED, height=3).pack(fill="x")

                top = tk.Frame(card, bg=PANEL)
                top.pack(fill="x", padx=12, pady=(8, 2))

                # Sleek inline loading canvas instead of an un-animated placeholder label
                icon_lbl = tk.Canvas(top, width=32, height=32, bg=PANEL, bd=0, highlightthickness=0)
                icon_lbl.pack(side="left", padx=(0, 8))
                icon_lbl.angle = 0
                icon_lbl.running = True
                
                def animate_spinner(c=icon_lbl):
                    if not c.winfo_exists() or not getattr(c, 'running', False):
                        return
                    c.delete("spinner")
                    c.create_arc(4, 4, 28, 28, start=c.angle, extent=280, outline=ACCENT, width=3, style="arc", tags="spinner")
                    c.angle = (c.angle + 8) % 360
                    win.after(20, lambda: animate_spinner(c))
                animate_spinner()

                tk.Label(top, text=m.get("name", "unknown"), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18, "bold")).pack(side="left")
                tk.Label(top, text=f"v{m.get('version', '0.0')}", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14)).pack(side="left", padx=8, pady=4)

                # normalize registry
                lookups = [
                    str(m_id).strip().lower(), 
                    str(m.get("name", "")).strip().lower()
                ]
                installed_locally = False
                matched_key = None
                
                for l_key in lookups:
                    if l_key in local_status:
                        installed_locally = True
                        matched_key = l_key
                        break

                rem_v = m.get("version", "0.0.0")
                loc_v = local_status[matched_key]["version"] if installed_locally else "0.0.0"
                active_locally = local_status[matched_key]["enabled"] if installed_locally else False
                resolved_folder = local_status[matched_key]["actual_folder"] if installed_locally else m_id

                if not installed_locally:
                    btn = self._btn(top, "Download", lambda mod=m: start_download(mod), bg=BG, fg=TEXT, font=(FONT_FAMILY, 14))
                    btn.pack(side="right", padx=(4, 0))
                elif loc_v != rem_v:
                    btn = self._btn(top, f"Update (v{rem_v})", lambda mod=m: start_download(mod), bg="#1e4620", fg="#a2ffa4", font=(FONT_FAMILY, 14))
                    btn.pack(side="right", padx=(4, 0))
                else:
                    lbl_inst = tk.Label(top, text=f"Installed (v{loc_v})", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14))
                    lbl_inst.pack(side="right", padx=(6, 0))

                    ref_arr = [None]
                    def trigger_browse_toggle(mod_target_folder=resolved_folder, b_widget=ref_arr):
                        f_dir = os.path.join(self.cfg["mods_dir"], mod_target_folder)
                        ign_file = os.path.join(f_dir, IGNORE_FILE)
                        if os.path.exists(ign_file):
                            try: os.unlink(ign_file)
                            except Exception: pass
                            b_widget[0].configure(text="Active", fg=ENABLED)
                        else:
                            try: Path(ign_file).touch()
                            except Exception: pass
                            b_widget[0].configure(text="Inactive", fg=DISABLED)
                        self._refresh_mods()

                    init_txt = "Active" if active_locally else "Inactive"
                    init_fg = ENABLED if active_locally else DISABLED
                    ref_arr[0] = self._btn(top, init_txt, trigger_browse_toggle, bg=BG, fg=init_fg, font=(FONT_FAMILY, 14))
                    ref_arr[0].pack(side="right", padx=(4, 0))

                import webbrowser
                repo_url = m.get("git_url", "")
                repo_btn = self._btn(top, "Repo", lambda url=repo_url: webbrowser.open(url) if url else None, bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14))
                repo_btn.pack(side="right", padx=4)

                mid = tk.Frame(card, bg=PANEL)
                mid.pack(fill="x", padx=12, pady=(0, 4))
                tk.Label(mid, text=f"by {m.get('author', 'unknown')}", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14)).pack(side="left")

                desc = tk.Label(card, text=m.get("description", ""), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 16), justify="left", anchor="w", wraplength=650)
                desc.pack(fill="x", padx=12, pady=(2, 10))

                card_widgets.append({
                    "id": m_id,
                    "name": m.get("name", "unknown"),
                    "description": m.get("description", ""),
                    "git_url": m.get("git_url", ""),
                    "frame": card,
                    "icon_label": icon_lbl
                })

            browse_page_state["filtered"] = card_widgets
            win.after(200, render_page)

        def start_download(mod):
            target_dir = Path(self.cfg["mods_dir"])
            final_folder_destination = target_dir / mod["id"]
            if final_folder_destination.exists():
                if not messagebox.askyesno("JokerDeck", f"you already have a folder named '{mod['id']}' installed.\n\ndo you want to overwrite it?"):
                    return

            load_frame.pack(fill="both", expand=True)
            main_frame.pack_forget()
            load_lbl.configure(text=f"downloading {mod['name']}...\n(starting connection)", fg=TEXT)
            
            threading.Thread(target=download_engine_thread, args=(mod,), daemon=True).start()

        def download_engine_thread(mod):
            try:
                repo_url = mod.get("git_url", "")
                if not repo_url:
                    raise Exception("missing github repository url field")
                
                target_dir = Path(self.cfg["mods_dir"])
                target_dir.mkdir(parents=True, exist_ok=True)
                tmp_zip = target_dir / f"temp_jokerdeck_{mod['id']}.zip"
                
                zip_url = None
                if "github.com" in repo_url.lower():
                    try:
                        clean_url = repo_url.replace("https://github.com/", "").strip("/")
                        parts = clean_url.split("/")
                        if len(parts) >= 2:
                            owner, repo = parts[0], parts[1]
                            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
                            
                            req = urllib.request.Request(api_url, headers={"User-Agent": "JokerDeck-Manager"})
                            with urllib.request.urlopen(req, timeout=10) as resp:
                                release_info = json.loads(resp.read().decode("utf-8"))
                                assets = release_info.get("assets", [])
                                zip_assets = [a["browser_download_url"] for a in assets if a.get("name", "").lower().endswith(".zip")]
                                
                                if zip_assets:
                                    zip_url = zip_assets[0]
                    except Exception:
                        pass

                if not zip_url:
                    if "github.com" not in repo_url.lower():
                        zip_url = repo_url.rstrip("/") + "/archive/main.zip"
                    else:
                        zip_url = repo_url.rstrip("/") + "/archive/refs/heads/main.zip"

                def run_chunk_download(url_target):
                    req = urllib.request.Request(url_target, headers={"User-Agent": "JokerDeck-Manager"})
                    with urllib.request.urlopen(req, timeout=15) as response, open(tmp_zip, "wb") as out_file:
                        total_bytes = 0
                        while True:
                            chunk = response.read(16 * 1024)
                            if not chunk:
                                break
                            out_file.write(chunk)
                            total_bytes += len(chunk)
                            mb_downloaded = total_bytes / (1024 * 1024)
                            win.after(10, lambda b=mb_downloaded: load_lbl.configure(text=f"downloading {mod['name']}...\n{b:.2f} mb fetched"))

                try:
                    run_chunk_download(zip_url)
                except Exception as e:
                    if "404" in str(e):
                        zip_url = repo_url.rstrip("/") + "/archive/refs/heads/main.zip"
                        run_chunk_download(zip_url)
                    else:
                        raise e

                win.after(10, lambda: load_lbl.configure(text=f"extracting {mod['name']}...\nplease wait..."))
                final_folder_destination = target_dir / mod["id"]
                if final_folder_destination.exists():
                    shutil.rmtree(final_folder_destination)
                final_folder_destination.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(tmp_zip, "r") as zip_ref:
                    for member in zip_ref.infolist():
                        parts = Path(member.filename).parts
                        if len(parts) <= 1:
                            continue
                        
                        target_path = final_folder_destination / Path(*parts[1:])
                        if member.is_dir():
                            target_path.mkdir(parents=True, exist_ok=True)
                        else:
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            with zip_ref.open(member) as source, open(target_path, "wb") as target_file:
                                shutil.copyfileobj(source, target_file)

                if tmp_zip.exists():
                    tmp_zip.unlink()

                ignore_flag = final_folder_destination / IGNORE_FILE
                ignore_flag.touch()

                try:
                    with open(final_folder_destination / "mod.json", "w", encoding="utf-8") as local_json:
                        json.dump(mod, local_json, indent=2)
                except Exception:
                    pass

                win.after(10, lambda: download_success(mod))

            except Exception as e:
                win.after(10, lambda: show_error(f"failed download:\n{e}"))

        def download_success(mod):
            messagebox.showinfo("JokerDeck", f"successfully installed {mod['name']}!\nit has been disabled by default so you can toggle it when ready.")
            self._refresh_mods()
            win.destroy()

        # kick off thread instantly
        threading.Thread(target=fetch_index_thread, daemon=True).start()

    # canvas layout
    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # widget factory
    @staticmethod
    def _btn(parent, text, command, bg=PANEL, fg=TEXT, font=None, pad=(12, 6)):
        if font is None:
            font = (FONT_FAMILY, 18)
        return tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=HOVER, activeforeground=TEXT,
            font=font, relief="flat", bd=0, padx=pad[0], pady=pad[1],
            cursor="hand2"
        )


if __name__ == "__main__":
    app = JokerDeck()
    app.mainloop()