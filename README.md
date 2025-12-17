# removebg-square-cli

Batch:
1) Normalize to PNG (including RAW: .nef/.arw/.cr3 via rawpy)
2) Call remove.bg
3) Center the cutout on a square canvas with padding

## Install (recommended via pipx)

```bash
python -m pip install --upgrade pip
pipx install .
Optional Keychain support:

bash
Copy code
pipx install ".[keyring]"
API key (choose one)
Env var
bash
Copy code
export REMOVEBG_API_KEY="YOUR_KEY"
removebg-square --input-dir input --output-dir output
Keychain (macOS)
bash
Copy code
removebg-square login --api-key "YOUR_KEY"
removebg-square --input-dir input --output-dir output
Usage
bash
Copy code
removebg-square \
  --input-dir input \
  --output-dir output \
  --out-size 1000 \
  --padding 50 \
  --remove-size auto
Notes
rawpy may require native dependencies (libraw). On macOS you can usually:
brew install libraw
---

## `.gitignore`

```gitignore
__pycache__/
*.pyc
.venv/
dist/
build/
*.egg-info/
output/
input/