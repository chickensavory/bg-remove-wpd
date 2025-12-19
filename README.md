````md
# bg-remove-wpd (removebg-square-cli)

A simple tool to remove backgrounds using **remove.bg** and output square, padded images  
(great for product photos and listings).

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

## Common options

Run with custom folders:

```bash
removebg-square run --input-dir my_photos --output-dir done
```

Change output size and padding:

```bash
removebg-square run --out-size 1200 --padding 80
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