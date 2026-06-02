"""
JokerDeck - a balatro mod manager

A simple balatro mod manager made with Python!
"""

import os
import sys
import json
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from ctypes import windll, byref, create_unicode_buffer

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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
    font_path = Path(__file__).parent / font_filename
    if font_path.exists() and os.name == "nt":
        windll.gdi32.AddFontResourceExW(byref(create_unicode_buffer(str(font_path))), 0x10, 0)
        if "m6x11" in font_filename.lower():
            return "m6x11plus"
        return font_path.stem
    return "Arial"

# defaults
DEFAULT_MODS_DIR  = r"C:\Users\covec\AppData\Roaming\Balatro\Mods"
DEFAULT_GAME_PATH = r"C:\Users\covec\Desktop\Balatro"
GAME_EXE_NAME     = "Balatro.exe"
CONFIG_FILE       = Path(__file__).parent / "jokerdeck_config.json"
IGNORE_FILE       = ".lovelyignore"
UNINSTALLED_DIR   = "Uninstalled"

FONT_FAMILY = load_custom_font("m6x11plus.ttf")

BG       = "#f2f2f7"
PANEL    = "#ffffff"
ACCENT   = "#cc1b3b"
TEXT     = "#1c1c1e"
SUBTEXT  = "#68686e"
BORDER   = "#d1d1d6"
ENABLED  = "#1a7f37"
DISABLED = "#8e8e93"
HOVER    = "#fafdff"
SEL_BG   = "#fff0f3"
SEL_BDR  = "#cc1b3b"

# config i/o
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"mods_dir": DEFAULT_MODS_DIR, "game_path": DEFAULT_GAME_PATH}

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# mod helpers
def _has_valid_json(entry: Path) -> bool:
    """Returns True only if the folder has at least one valid, readable JSON file."""
    for jf in entry.glob("*.json"):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        # Skip folders with no valid JSON — not a real mod
        if not _has_valid_json(entry):
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
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                temp_name = data.get("display_name") or data.get("name") or data.get("id")
                temp_desc = data.get("description")
                temp_ver  = data.get("version")
                raw_author = data.get("author")

                if temp_name and not mod_name:
                    mod_name = temp_name
                if temp_desc and description == "No description provided.":
                    description = temp_desc
                if temp_ver and not version:
                    version = str(temp_ver)
                if raw_author and not author:
                    if isinstance(raw_author, list):
                        if len(raw_author) == 1:
                            author = str(raw_author[0])
                        elif len(raw_author) == 2:
                            author = f"{raw_author[0]} & {raw_author[1]}"
                        else:
                            author = ", ".join(map(str, raw_author[:-1])) + f" & {raw_author[-1]}"
                    else:
                        author = str(raw_author)

                # Once we have everything, stop early
                if mod_name and description != "No description provided." and version and author:
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

def set_mod_enabled(mod: dict, enabled: bool):
    ignore_path = mod["path"] / IGNORE_FILE
    if enabled:
        if ignore_path.exists():
            ignore_path.unlink()
    else:
        ignore_path.touch()
    mod["enabled"] = enabled

def uninstall_mod(mod: dict, mods_dir: str):
    """Moves mod folder from Mods/ into Mods/Uninstalled/."""
    uninstalled = Path(mods_dir) / UNINSTALLED_DIR
    uninstalled.mkdir(exist_ok=True)
    dest = uninstalled / mod["path"].name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(mod["path"]), str(dest))

# launch helpers
def launch_game(game_path: str, vanilla: bool = False):
    exe = Path(game_path) / GAME_EXE_NAME
    if not exe.exists():
        exe = Path(game_path)
    if not exe.exists():
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
        self.before = before   # state BEFORE the action
        self.after = not before

# main app
class JokerDeck(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        try:
            with open(Path(__file__).parent / "conf.json", "r") as f:
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
        self._selected_mods: set = set()   # set of mod paths (str)
        self._action_bar = None

        # undo/redo stacks
        self._undo_stack: list[list[ToggleAction]] = []
        self._redo_stack: list[list[ToggleAction]] = []

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

    # ── ui build ────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._style_ttk()
        self._build_header()
        self._build_toolbar()
        self._build_mod_grid()
        self._build_footer()

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

        self._btn(hdr, "⚙ Settings", self._open_settings, bg=PANEL, fg=SUBTEXT, pad=(12, 8)).pack(side="right", padx=15)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=BG, pady=12)
        bar.pack(fill="x", padx=20)

        self._btn(bar, "▶ Launch Modded", lambda: self._launch(vanilla=False), bg=ACCENT, fg=PANEL, font=(FONT_FAMILY, 18, "bold")).pack(side="left", padx=(0, 8))
        self._btn(bar, "Launch Vanilla",  lambda: self._launch(vanilla=True),  bg=BORDER, fg=TEXT, font=(FONT_FAMILY, 18)).pack(side="left", padx=(0, 20))

        # Undo / Redo / Reload — replacing old Enable All / Disable All
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
                                        values=["Name (A-Z)", "Name (Z-A)", "Only of author(s):", "Enabled Only", "Disabled Only"],
                                        state="readonly", font=(FONT_FAMILY, 18), width=18)
        self.sort_combo.pack(side="left")
        self.sort_combo.bind("<<ComboboxSelected>>", self._on_sort_change)
        self.author_btn = self._btn(sort_frame, "Select Authors…", self._toggle_author_popup, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18), pad=(10, 4))

        self._update_undo_redo_btns()

    def _on_sort_change(self, event=None):
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
        self._btn(inner, "🗑 Uninstall",  self._bulk_uninstall,  bg=BG,    fg=ACCENT,   font=(FONT_FAMILY, 18), pad=(12, 6)).pack(side="left", padx=(0, 6))
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

    # ── select mode ─────────────────────────────────────────────────────────
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
        else:
            self._action_bar.pack_forget()

    def _select_all(self):
            for m in self.mods:
                self._selected_mods.add(str(m["path"]))
            self._sel_count_lbl.configure(text=f"{len(self._selected_mods)} selected")
            self._action_bar.pack(fill="x")
            self._render_mods()

    def _deselect_all(self):
        self._selected_mods.clear()
        self._sel_count_lbl.configure(text="0 selected")
        self._action_bar.pack_forget()
        for ui in self._card_cache:
            ui["select_btn"].configure(text="⚪", bg=PANEL)
        self._render_mods()

    def _get_selected_mods(self) -> list[dict]:
        return [m for m in self.mods if str(m["path"]) in self._selected_mods]

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
        names = "\n".join(f"  • {m['name']}" for m in sel)
        if not messagebox.askyesno("Uninstall Mods", f"Move these mods to Uninstalled?\n\n{names}"):
            return
        for m in sel:
            try:
                uninstall_mod(m, self.cfg["mods_dir"])
            except Exception as e:
                messagebox.showerror("JokerDeck", f"Failed to uninstall {m['name']}:\n{e}")
        self._selected_mods.clear()
        self._refresh_mods()
        self.status_var.set(f"Uninstalled {len(sel)} mod(s).")

    # ── undo / redo ─────────────────────────────────────────────────────────
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

    # ── card cache & render ──────────────────────────────────────────────────
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
            if sort_mode == "Only of author(s):" and self._selected_authors:
                mod_authors = [a.strip() for a in m["author"].replace(" & ", ", ").split(", ")]
                if not any(auth in self._selected_authors for auth in mod_authors):
                    continue
            filtered.append(m)

        if not filtered:
            if not self._empty_label:
                self._empty_label = tk.Label(self.mod_frame, text="No modifications found.",
                                              bg=BG, fg=SUBTEXT, font=(FONT_FAMILY, 18), pady=40)
            self._empty_label.pack(fill="x")
            self.mod_count_var.set(f"0 / {len(self.mods)} active")
            return

        if sort_mode == "Name (Z-A)":
            filtered.sort(key=lambda m: m["name"].lower(), reverse=True)
        else:
            filtered.sort(key=lambda m: m["name"].lower())

        for idx, mod in enumerate(filtered):
            row_idx = idx // 2
            col_idx = idx % 2
            ui = self._get_cached_card(idx)
            ui["_mod_path"] = str(mod["path"])

            is_on = mod["enabled"]
            is_selected = str(mod["path"]) in self._selected_mods

            card_bg = SEL_BG if is_selected else PANEL
            bdr     = SEL_BDR if is_selected else BORDER
            ui["card"].configure(bg=card_bg, highlightbackground=bdr)
            ui["top"].configure(bg=card_bg)
            ui["accent"].configure(bg=ACCENT if is_on else DISABLED)
            ui["name"].configure(text=mod["name"], bg=card_bg)
            ui["desc"].configure(text=mod["description"], bg=card_bg)
            ui["meta"].configure(bg=card_bg)

            # Mod icon
            if mod.get("icon"):
                photo = self._load_icon(mod["icon"])
                if photo:
                    ui["icon"].configure(image=photo, bg=card_bg)
                    ui["icon"].image = photo
                else:
                    ui["icon"].configure(image="", bg=card_bg)
            else:
                ui["icon"].configure(image="", bg=card_bg)

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
            before = mod["enabled"]
            set_mod_enabled(mod, not mod["enabled"])
            is_on = mod["enabled"]
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
        self._render_mods()
        self.status_var.set(f"Loaded {len(self.mods)} mod(s).")

    # ── settings ────────────────────────────────────────────────────────────
    def _open_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.state("zoomed")
        self.minsize(700, 500)
        win.configure(bg=PANEL)
        win.grab_set()

        def section(label):
            tk.Label(win, text=label, bg=PANEL, fg=TEXT,
                     font=(FONT_FAMILY, 18, "bold")).pack(anchor="w", padx=20, pady=(14, 2))

        def path_row(parent, var: tk.StringVar, pick_fn):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill="x", padx=20, pady=(0, 4))
            tk.Entry(f, textvariable=var, bg=BG, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=(FONT_FAMILY, 18), bd=5).pack(side="left", fill="x", expand=True)
            JokerDeck._btn(f, "Browse", pick_fn, bg=BORDER, fg=TEXT).pack(side="left", padx=(6, 0))

        game_var = tk.StringVar(value=self.cfg["game_path"])
        section("Balatro Executable Directory")
        path_row(win, game_var,
                 lambda: game_var.set(filedialog.askdirectory(title="Select Balatro Directory",
                                                               initialdir=self.cfg["game_path"]) or game_var.get()))

        mods_var = tk.StringVar(value=self.cfg["mods_dir"])
        section("Mods Directory Path")
        path_row(win, mods_var,
                 lambda: mods_var.set(filedialog.askdirectory(title="Select Mods Directory",
                                                               initialdir=self.cfg["mods_dir"]) or mods_var.get()))

        btn_frame = tk.Frame(win, bg=PANEL)
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=14)

        def save():
            self.cfg["game_path"] = game_var.get().strip()
            self.cfg["mods_dir"]  = mods_var.get().strip()
            save_config(self.cfg)
            win.destroy()
            self._refresh_mods()
            self.status_var.set("Configurations saved.")

        self._btn(btn_frame, "Save Configurations", save,
                  bg=ACCENT, fg=PANEL, font=(FONT_FAMILY, 18, "bold")).pack(side="right")
        self._btn(btn_frame, "Cancel", win.destroy,
                  bg=BG, fg=SUBTEXT).pack(side="right", padx=(0, 8))

    # ── canvas layout ────────────────────────────────────────────────────────
    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if event.width > 10:
            self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.update_idletasks()

    # ── widget factory ───────────────────────────────────────────────────────
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