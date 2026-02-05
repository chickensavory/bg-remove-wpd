````md
# bg-remove-wpd (removebg-square-cli)

A simple tool to remove backgrounds using **remove.bg** and output padded images  
(square, landscape, or custom sizes — great for product photos and listings).

---

## Requirements

- Python 3.9+
- A remove.bg API key (https://www.remove.bg)

---

## Install

```bash
python3 -m pip install --user --upgrade pip
python3 -m pip install --user "git+https://github.com/chickensavory/bg-remove-wpd.git"
````

Verify installation:

```bash
removebg-square --help
```

---

## One-time setup (required)

Before running the tool, you must save your remove.bg API key:

```bash
removebg-square login --api-key YOUR_API_KEY
```

This securely stores the key in your system keychain.

To remove the saved key:

```bash
removebg-square logout
```

Sometimes macOS doesn’t automatically look in the folder where Python installs commands.

Run:

```bash
python3 -m site --user-base
```

If it prints something like `/Users/YOURNAME/Library/Python/3.9`, then run:

```bash
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
hash -r
```

---

## Usage

1. Create a folder named `input`
2. Put your images inside it
3. Run:

```bash
removebg-square run
```

Processed images will appear in the `output` folder.

---

## Default folders

* Input: `./input`
* Output: `./output`

Folders are created automatically if they do not exist.

---

## Size control

You can control the output canvas size in two ways: **presets** or **manual sizes**.
Only one size is applied per run.

### Presets (recommended)

```bash
removebg-square run --preset square
removebg-square run --preset square-xl
removebg-square run --preset landscape
removebg-square run --preset portrait
```

Available presets:

* `square` → 1000 × 1000
* `square-xl` → 1400 × 1400
* `landscape` → 1920 × 1080 (16:9)
* `portrait` → 1080 × 1920 (9:16)

If `--preset` is provided, it takes priority over `--out-size`.

---

### Manual sizes

```bash
removebg-square run --out-size 1000
removebg-square run --out-size 1400x1400
removebg-square run --out-size 1920x1080
```

Accepted formats:

* `1000` → square (1000 × 1000)
* `WIDTHxHEIGHT` → rectangular (e.g. `1920x1080`)

---

## Margins (padding)

Padding is controlled per side using margins:

```bash
removebg-square run \
  --margin-left 80 \
  --margin-right 80 \
  --margin-top 80 \
  --margin-bottom 80
```

Margins define the safe area inside the output canvas where the subject is scaled and centered.

---

## Other common options

Run with custom folders:

```bash
removebg-square run --input-dir my_photos --output-dir done
```

Control remove.bg processing size:

```bash
removebg-square run --remove-size auto
```

---

## Supported input formats

* `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`
* RAW (via rawpy): `.nef`, `.arw`, `.cr3`

---

## Uninstall

```bash
python3 -m pip uninstall removebg-square-cli
```

---

## Update

```bash
python3 -m pip install --user --upgrade --no-cache-dir "git+https://github.com/chickensavory/bg-remove-wpd.git"
```