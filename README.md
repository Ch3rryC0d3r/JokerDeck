![](previews/banner.png)
### a balatro mod manager that doesn't suck

tired of digging through your `AppData` folder like a raccoon every time you want to swap mods? yeah. me too. 
JokerDeck is a simple, clean mod manager for Balatro. (Reads your local mods, and allows you to download mods from an all-new JokerDeck index)

---

## current features

- **a great (probably) mod browser**
- **enable/disable mods with a click**
- **bulk select (gotta love efficiency)**
- **undo/redo**
- **mod icons, locally and on the mod browser**
- **launch modded or vanilla**
- **auto-detects mod info**

---

## getting started

### requirements
before anything, you need:
- **Balatro** (Xbox Game Pass version is **not** supported, sorry)
- **Lovely Injector** — [download here](https://github.com/ethangreen-dev/lovely-injector/releases/tag/v0.9.0)
- **Steamodded** — [download here](https://github.com/Steamodded/smods/releases/tag/1.0.0-beta-1620a)

set those up first, then grab JokerDeck.

### installation
1. download the latest `.exe` from [Releases](../../releases)
2. drop it anywhere you want
3. run it, go to Settings (top right) and point it in the right direction
4. you're done!

---

## running from source

if you want to run the `.pyw` directly instead of the exe, you'll need:
- Python 3.1*+
- Pillow (run `pip install pillow` after Python in a console) - for mod icons, optional but recommended

then just run `JokerDeck.pyw` and you're good.

---

## mod index and guidelines

Want to **submit a mod**?
You can do so **[here](https://github.com/Ch3rryC0d3r/JokerDeckIndex/issues)**. It only takes 4 clicks! Wait time (to be approved) is usually within 24 hours.
There's also a simple guide for submission **[here](https://github.com/Ch3rryC0d3r/JokerDeck/releases/tag/v1.0.5)**

The mod index is a brand new ([repo](https://github.com/Ch3rryC0d3r/JokerDeckIndex/)) balatro mod index/list, meant just for the JokerDeck app.
Submitting a mod will only scrape your repo for a json manifest and an icon (if it has) completely automatically,
downloading a mod in the browser downloads straight from your repo and takes the latest (stable) release. (if there is none, it will take the default branch)

You must follow the **Guidelines** below for your mod to be approved.

### guidelines
- Mod must be for Balatro (nothing unrelated)
- Must have a public repository (GitHub or similar)
- Repo must contain a valid JSON manifest (mod.json or similar) with at least: `id`, `name`, `description`, `version`
- No malicious, harmful, or illegal content
- Mods in early states are fine, but must be functional enough to install and load
- Must be of reasonable quality (i.e. a single throwaway joker with no effort put in wouldn't be approved)
- If your mod gets taken down from the index, for information, you can check [this forum](https://discord.com/channels/1116389027176787968/1511415120515956797), as I may post what/why I took X down.

---

## notes

- mods are managed via Lovely Injector's `.lovelyignore` system - disabling a mod just drops a file in its folder, nothing gets deleted
- uninstalled mods get moved to a `Uninstalled` folder, not permanently deleted
- config is saved locally, so nothing weird going on

---

![](previews/preview_01.png)
![](previews/preview_02.png)
![](previews/preview_03.png)
![](previews/preview_04.png)

---

made with ❤ and way too much free time
