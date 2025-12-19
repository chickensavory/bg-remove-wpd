# bg-remove-wpd (removebg-square-cli)

A tiny “drop images in a folder, run one command” tool that:

1) Normalizes images to PNG (includes some RAW formats via `rawpy`)  
2) Sends them to the **remove.bg** API  
3) Centers the cutout on a square canvas with padding (great for product shots / listings)
---

## What you need

- **Python 3.9+**
- A **remove.bg API key** (get it from remove.bg)

---

## Install (pip + GitHub)

This installs directly from this GitHub repo:

```bash
python3 -m pip install --user --upgrade pip
python3 -m pip install --user "git+https://github.com/chickensavory/bg-remove-wpd.git"
````

After installing, you should have the command:

```bash
removebg-square --help
```

### If `removebg-square` is “command not found”

That usually means your `--user` scripts folder isn’t on PATH.

* **macOS / Linux**: add this to `~/.bashrc` or `~/.zshrc` then reopen terminal:

  ```bash
  export PATH="$HOME/.local/bin:$PATH"
  ```
* **Windows (PowerShell)**: your user scripts are typically under:
  `C:\Users\<you>\AppData\Roaming\Python\Python3x\Scripts`
  Add that folder to your PATH.

---

## Super simple usage (non-developer mode)

1. Create an `input` folder and put images inside (jpg/png/webp/etc.)
2. Run:

```bash
removebg-square
```

### First run: it will ask for your API key once

On the first run, if no key is found, the tool will prompt:

* Paste your remove.bg API key
* It attempts to save it securely (OS keychain) so you don’t have to paste again 

Output files go to `output/` by default.

---

## What folders does it use?

* **Input:** `./input/`
* **Output:** `./output/`

If the folders don’t exist, the tool creates them. 

---

## Common commands

### Run with custom folders

```bash
removebg-square --input-dir my_photos --output-dir done
```

### Change output size and padding

```bash
removebg-square --out-size 1200 --padding 80
```

### Control remove.bg processing size

remove.bg supports a `size` option like `auto`, `preview`, `full`.

```bash
removebg-square --remove-size auto
```

---

## API key options (pick ONE)

### Option A: Paste once when prompted (recommended)

Just run `removebg-square` and paste the key when it asks. 

### Option B: Set an environment variable

Useful for servers / automation:

```bash
export REMOVEBG_API_KEY="YOUR_KEY"
removebg-square
```

The CLI checks `REMOVEBG_API_KEY` automatically. 

### Option C: Keychain commands (manual)

You can explicitly save/remove a key:

```bash
removebg-square login --api-key "YOUR_KEY"
removebg-square logout
```



### Option D: Pass the key just for one run

```bash
removebg-square --api-key "YOUR_KEY"
```



---

## Supported input formats

The tool looks for these extensions in the input folder:

* `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`
* RAW (via rawpy): `.nef`, `.arw`, `.cr3` 

---

## Notes / troubleshooting

### RAW support may require system libraries

`rawpy` can require native dependencies (often `libraw`).

* **macOS (Homebrew):**

  ```bash
  brew install libraw
  ```

### remove.bg errors / rate limits

If remove.bg returns an error (bad key, rate limit, etc.), the tool prints the HTTP status and error details. 

---

## Uninstall

```bash
python3 -m pip uninstall removebg-square-cli
```

(Project package name is `removebg-square-cli`.) 