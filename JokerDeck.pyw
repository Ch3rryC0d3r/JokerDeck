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
CONFIG_FILE       = Path(__file__).parent / "jokerdeck_config.json"
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
# sorry ill have to burn your eyes just until you can make it to settings
apply_theme(False)

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
            "enabled":     not ignore.exists(),
            "description": description.strip(),
            "version":     str(version).strip(),
            "author":      str(author).strip(),
            "icon":        icon_path,
        })
    return mods

def parse_conflict_id(conflict_str: str) -> str:
    # pull just the mod id out of something like "Talisman (>=1.1) (<<2~)"
    return conflict_str.strip().split("(")[0].strip()

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
        apply_theme(self.cfg.get("dark_mode", False)) # light mode
        try:
            with open(Path(__file__).parent / "ver.json", "r") as f:
                self._version = json.load(f).get("version", "")
        except Exception:
            self._version = ""
        self.mods = []
        self._search_timer = None
        self._search_var = tk.StringVar()
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
        self._build_ui()
        self._refresh_mods()

    def _on_search_change(self, *args):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(150, self._render_mods)
        
    # "re" build.. haha get it? no..? oh ok
    def _rebuild_ui(self):
        for widget in self.winfo_children():
            widget.destroy()
        self._card_cache = []
        self._empty_label = None
        self._icon_cache = {}
        self.configure(bg=BG)
        self._build_ui()
        self._refresh_mods()
        
    # ui build
    def _build_ui(self):
        self._style_ttk()
        self._build_header()
        self._build_toolbar()
        self._build_mod_grid()
        self._build_footer()
        self._bind_shortcuts()

    def _bind_shortcuts(self):
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())
        self.bind_all("<Control-a>", lambda e: self._select_all())
        self.bind_all("<Escape>",    lambda e: self._deselect_all())

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
        tk.Entry(search_frame, textvariable=self._search_var, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 18), width=14, bd=4).pack(side="left", padx=(0, 2))

        # Sort
        sort_frame = tk.Frame(bar, bg=BG)
        sort_frame.pack(side="right", padx=(0, 15))
        tk.Label(sort_frame, text="Sort: ", bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18)).pack(side="left")
        self.sort_combo = ttk.Combobox(sort_frame, textvariable=self._sort_var,
                                        state="readonly", font=(FONT_FAMILY, 18), width=18)
        self.sort_combo.pack(side="left")
        self.sort_combo.bind("<<ComboboxSelected>>", self._on_sort_change)
        self.author_btn = self._btn(sort_frame, "Select Authors...", self._toggle_author_popup, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18), pad=(10, 4)) # author selection

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
        self._build_smods_bar()  # smods strip at the top :3
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
            # same slicing as the original — "0.X.Y-SMODS-0.1.2" → "SMODS"
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

    def _build_smods_bar(self):
        if hasattr(self, "_smods_bar") and self._smods_bar.winfo_exists():
            self._smods_bar.destroy()

        versions = self._all_smods_versions()
        active = self._active_smods()
        active_ver = active["version"] if active else None

        # sort by the number then the letter
        def smods_sort_key(s):
            ver = s["version"]
            num = ''.join(c for c in ver if c.isdigit())
            letter = ''.join(c for c in ver if c.isalpha())
            return (int(num) if num else 0, letter)
        versions.sort(key=smods_sort_key) # could probably js like put it in one line, but i'd rather read it

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=20, pady=(0, 6))
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

        for idx, mod in enumerate(filtered):
            row_idx = (idx // 2) + 1
            col_idx = idx % 2
            ui = self._get_cached_card(idx)
            ui["_mod_path"] = str(mod["path"])

            is_conflicting = str(mod["path"]) in getattr(self, "_conflicting_paths", set())
            is_on = mod["enabled"]
            is_selected = str(mod["path"]) in self._selected_mods

            # conflicting cards get a yellow wash, selected cards get the red tint, otherwise normal
            if is_selected:
                card_bg = SEL_BG
                bdr = SEL_BDR
            elif is_conflicting:
                card_bg = "#fffbe6"
                bdr = "#e6c84a"
            else:
                card_bg = PANEL
                bdr = BORDER

            ui["card"].configure(bg=card_bg, highlightbackground=bdr)
            ui["top"].configure(bg=card_bg)
            ui["accent"].configure(bg=ACCENT if is_on else DISABLED)
            ui["name"].configure(text=mod["name"], bg=card_bg)
            ui["desc"].configure(text=mod["description"], bg=card_bg)
            ui["meta"].configure(bg=card_bg)

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
            self.cfg["dark_mode"] = dark_var.get() # save if the user is a Sith- i mean if they selected Dark mode
            save_config(self.cfg)
            apply_theme(dark_var.get()) # actually apply it
            win.destroy()
            self._rebuild_ui()
            self.status_var.set("Saved.")

        self._btn(btn_frame, "Save", save,
                  bg=ACCENT, fg=PANEL, font=(FONT_FAMILY, 18, "bold")).pack(side="right")
        self._btn(btn_frame, "Cancel", win.destroy,
                  bg=BG, fg=SUBTEXT).pack(side="right", padx=(0, 8))

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
                req = urllib.request.Request(url, headers={"User-Agent": "JokerDeck-Manager"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                win.after(10, lambda: setup_browser_ui(data))
            except Exception as e:
                win.after(10, lambda: show_error(f"failed to load index:\n{e}"))

        def show_error(msg):
            load_lbl.configure(text=msg, fg=ACCENT)

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
                
                # Check if card is visible or right below the fold (buffer for smooth scrolling)
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
            try:
                clean_url = repo_url.replace("https://github.com/", "").strip("/")
                parts = clean_url.split("/")
                if len(parts) < 2:
                    return
                owner, repo = parts[0], parts[1]
                
                img_data = None
                chosen_branch = None
                chosen_file = None

                # Query the official API endpoint to get a guaranteed directory file list
                for br in ["master", "main"]:
                    dir_url = f"https://api.github.com/repos/{owner}/{repo}/contents/assets/1x?ref={br}"
                    try:
                        req = urllib.request.Request(dir_url, headers={"User-Agent": "JokerDeck-Manager"})
                        with urllib.request.urlopen(req, timeout=2) as resp:
                            items = json.loads(resp.read().decode("utf-8"))
                            
                            # Safely extract names from the standard API list format
                            png_files = [i.get("name", "") for i in items if isinstance(i, dict) and i.get("name", "").lower().endswith(".png")]
                            
                            if png_files:
                                # Run your exact local prioritization sorting method
                                sorted_pngs = sorted(png_files, key=lambda p: (0 if "icon" in p.lower() else 1, p))
                                chosen_file = sorted_pngs[0]
                                chosen_branch = br
                                break
                    except Exception:
                        continue

                # Download file utilizing the discovered filename
                if chosen_file:
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{chosen_branch}/assets/1x/{chosen_file}"
                    try:
                        req = urllib.request.Request(raw_url, headers={"User-Agent": "JokerDeck-Manager"})
                        with urllib.request.urlopen(req, timeout=1.5) as resp:
                            img_data = resp.read()
                    except Exception:
                        pass

                if img_data:
                    from io import BytesIO
                    from PIL import Image, ImageTk
                    
                    im = Image.open(BytesIO(img_data)).convert("RGBA")
                    w, h = im.size
                    if w == h and 16 < w < 48:
                        im = im.resize((32, 32), Image.Resampling.NEAREST)
                        tk_img = ImageTk.PhotoImage(im)
                        win.after(5, lambda: apply_icon(mod_id, tk_img, target_label))
            except Exception:
                pass
            finally:
                if mod_id in downloading_icons:
                    downloading_icons.remove(mod_id)

        def apply_icon(mod_id, tk_img, target_label):
            image_cache[mod_id] = tk_img
            try:
                if target_label.winfo_exists():
                    target_label.configure(image=tk_img)
            except Exception:
                pass

        def apply_icon(mod_id, tk_img, target_label):
            image_cache[mod_id] = tk_img
            if target_label.winfo_exists():
                target_label.configure(image=tk_img)

        def setup_browser_ui(mod_list):
            load_frame.pack_forget()
            main_frame.pack(fill="both", expand=True, padx=15, pady=15)

            # title
            tk.Label(main_frame, text="available mods", bg=BG, fg=ACCENT, font=(FONT_FAMILY, 24, "bold"), anchor="w").pack(fill="x", pady=(0, 10))

            # scrollable window setup
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
            
            # Update scroll region bounding frames and run lazy loader updates immediately on viewport config adjustments
            scroll_container.bind("<Configure>", lambda _: [
                canvas.configure(scrollregion=canvas.bbox("all")),
                win.after(100, lambda: lazy_load_visible_icons(canvas, scroll_container))
            ])

            # Hook the lazy icon display calculator straight into your scrolling behavior loops
            canvas.configure(yscrollcommand=lambda *args: [
                scrollbar.set(*args), 
                lazy_load_visible_icons(canvas, scroll_container)
            ])

            # load data cards
            for m in mod_list:
                card = tk.Frame(scroll_container, bg=PANEL, bd=0, highlightbackground=BORDER, highlightthickness=1)
                card.pack(fill="x", pady=4, padx=2)
                tk.Frame(card, bg=DISABLED, height=3).pack(fill="x")

                top = tk.Frame(card, bg=PANEL)
                top.pack(fill="x", padx=12, pady=(8, 2))

                # Inject the icon label container right next to the title text component frame element
                icon_lbl = tk.Label(top, bg=PANEL, image=placeholder_img)
                icon_lbl.pack(side="left", padx=(0, 8))

                tk.Label(top, text=m.get("name", "unknown"), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18, "bold")).pack(side="left")
                tk.Label(top, text=f"v{m.get('version', '0.0')}", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14)).pack(side="left", padx=8, pady=4)

                # Download Button
                btn = self._btn(top, "Download", lambda mod=m: start_download(mod), bg=BG, fg=TEXT, font=(FONT_FAMILY, 14))
                btn.pack(side="right", padx=(4, 0))

                # Repo Button (Opens the GitHub link in the user's browser)
                import webbrowser
                repo_url = m.get("git_url", "")
                repo_btn = self._btn(
                    top, 
                    "Repo", 
                    lambda url=repo_url: webbrowser.open(url) if url else None, 
                    bg=PANEL, 
                    fg=SUBTEXT, 
                    font=(FONT_FAMILY, 14)
                )
                repo_btn.pack(side="right", padx=4)

                mid = tk.Frame(card, bg=PANEL)
                mid.pack(fill="x", padx=12, pady=(0, 4))
                tk.Label(mid, text=f"by {m.get('author', 'unknown')}", bg=PANEL, fg=SUBTEXT, font=(FONT_FAMILY, 14)).pack(side="left")

                desc = tk.Label(card, text=m.get("description", ""), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 16), justify="left", anchor="w", wraplength=650)
                desc.pack(fill="x", padx=12, pady=(2, 10))

                # Append metadata references to tracking arrays for execution management tracking hooks
                card_widgets.append({
                    "id": m.get("id", "unknown"),
                    "git_url": m.get("git_url", ""),
                    "frame": card,
                    "icon_label": icon_lbl
                })

            # Instantly load the first batch of visible ones on screen without delay
            win.after(10, lambda: lazy_load_visible_icons(canvas, scroll_container))
            win.after(100, lambda: lazy_load_visible_icons(canvas, scroll_container))

        def start_download(mod):
            target_dir = Path(self.cfg["mods_dir"])
            final_folder_destination = target_dir / mod["id"]
            if final_folder_destination.exists():
                if not messagebox.askyesno("JokerDeck", f"you already have a folder named '{mod['id']}' installed.\n\ndo you want to overwrite it?"):
                    return

            # lock layout down for visual feedback
            load_frame.pack(fill="both", expand=True)
            main_frame.pack_forget()
            load_lbl.configure(text=f"downloading {mod['name']}...\n(starting connection)", fg=TEXT)
            
            threading.Thread(target=download_engine_thread, args=(mod,), daemon=True).start()

        def download_engine_thread(mod):
            try:
                repo_url = mod.get("git_url", "")
                if not repo_url:
                    raise Exception("missing github repository url field")
                
                zip_url = repo_url.rstrip("/") + "/archive/refs/heads/master.zip"
                target_dir = Path(self.cfg["mods_dir"])
                target_dir.mkdir(parents=True, exist_ok=True)
                tmp_zip = target_dir / f"temp_jokerdeck_{mod['id']}.zip"

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

                # extraction step
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
    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if event.width > 10:
            self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.update_idletasks()

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