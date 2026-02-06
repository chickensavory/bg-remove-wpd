from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, Union, Any

import requests
import typer
from rich import print

from uuid import uuid4
import time

from .core import process_folder, ProcessResult

app = typer.Typer(
    add_completion=False,
    help="Batch remove.bg + padded-canvas formatter.",
)

KEYRING_SERVICE = "removebg-square-cli"
KEYRING_USERNAME = "removebg_api_key"

TRACKRING_SERVICE = "removebg-square-tracker"
TRACK_HF_USERNAME = "hf_access_token"
TRACK_TOKEN_USERNAME = "tracker_token"

TRACK_ENDPOINT = os.environ.get(
    "REMOVEBG_SQUARE_TRACK_ENDPOINT",
    "https://sofiakris-bgremoval.hf.space/track",
)

TRACKING_ENABLED = os.environ.get("REMOVEBG_SQUARE_TRACKING", "1").strip() != "0"


def _get_key_from_keyring(service: str, username: str) -> Optional[str]:
    try:
        import keyring
    except Exception:
        return None
    try:
        return keyring.get_password(service, username)
    except Exception:
        return None


def _set_key_in_keyring(service: str, username: str, value: str) -> None:
    import keyring

    keyring.set_password(service, username, value)


def _delete_key_in_keyring(service: str, username: str) -> None:
    import keyring

    try:
        keyring.delete_password(service, username)
    except Exception:
        pass


def resolve_api_key(api_key: Optional[str], use_keyring: bool) -> Optional[str]:
    if api_key:
        return api_key

    env_key = os.environ.get("REMOVEBG_API_KEY")
    if env_key:
        return env_key

    if use_keyring:
        kr = _get_key_from_keyring(KEYRING_SERVICE, KEYRING_USERNAME)
        if kr:
            return kr

    return None


def _resolve_tracking_tokens(use_keyring: bool) -> tuple[Optional[str], Optional[str]]:
    if not TRACKING_ENABLED:
        return None, None

    env_hf = os.environ.get("HF_ACCESS_TOKEN")
    env_tracker = os.environ.get("TRACKER_TOKEN")

    hf = env_hf.strip() if env_hf else None
    tr = env_tracker.strip() if env_tracker else None

    if use_keyring:
        if not hf:
            hf = _get_key_from_keyring(TRACKRING_SERVICE, TRACK_HF_USERNAME)
        if not tr:
            tr = _get_key_from_keyring(TRACKRING_SERVICE, TRACK_TOKEN_USERNAME)

    if not hf:
        print("[yellow][TRACK][/yellow] Hugging Face token not found.")
        hf = typer.prompt(
            "Paste Hugging Face access token (hf_...)", hide_input=True
        ).strip()
        try:
            if use_keyring and hf:
                _set_key_in_keyring(TRACKRING_SERVICE, TRACK_HF_USERNAME, hf)
                print(
                    "[green][TRACK][/green] HF token saved to Keychain. You won’t be asked again."
                )
        except Exception:
            print("[red][TRACK][/red] Could not save HF token to Keychain.")

    if not tr:
        print("[yellow][TRACK][/yellow] Tracker token not found.")
        tr = typer.prompt("Paste tracker token (hex/random)", hide_input=True).strip()
        try:
            if use_keyring and tr:
                _set_key_in_keyring(TRACKRING_SERVICE, TRACK_TOKEN_USERNAME, tr)
                print(
                    "[green][TRACK][/green] Tracker token saved to Keychain. You won’t be asked again."
                )
        except Exception:
            print("[red][TRACK][/red] Could not save tracker token to Keychain.")

    if not hf or not tr:
        print("[yellow][TRACK][/yellow] Tracking disabled (missing token(s)).")
        return None, None

    return hf, tr


def _post_run(
    hf_token: str,
    tracker_token: str,
    *,
    run_id: str,
    processed: int,
    unprocessed: int,
    processed_files: list[dict[str, Any]],
    unprocessed_files: list[dict[str, Any]],
    elapsed_s: float,
    tool: str,
) -> None:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "tool": tool,
        "processed": int(processed),
        "unprocessed": int(unprocessed),
        "elapsed_s": float(elapsed_s),
        "processed_files": processed_files,
        "unprocessed_files": unprocessed_files,
    }

    try:
        resp = requests.post(
            TRACK_ENDPOINT,
            headers={
                "Authorization": f"Bearer {hf_token}",
                "X-Tracker-Token": tracker_token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=12,
        )

        if 200 <= resp.status_code < 300:
            print(
                f"[dim][TRACK][/dim] sent run {run_id}: "
                f"processed={processed}, unprocessed={unprocessed}, "
                f"files={len(processed_files) + len(unprocessed_files)}"
            )
            return

        body = (resp.text or "")[:800].strip()
        print(f"[yellow][TRACK][/yellow] failed ({resp.status_code}): {body}")
    except Exception as e:
        print(f"[yellow][TRACK][/yellow] failed: {type(e).__name__}: {e}")


@app.command()
def login(
    api_key: str = typer.Option(..., "--api-key", help="Your remove.bg API key."),
):
    try:
        _set_key_in_keyring(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[green]Saved remove.bg API key to Keychain.[/green]")


@app.command()
def logout():
    try:
        _delete_key_in_keyring(KEYRING_SERVICE, KEYRING_USERNAME)
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[yellow]Removed remove.bg API key from Keychain (if it existed).[/yellow]")


@app.command()
def tracker_login(
    hf_token: str = typer.Option(
        ..., "--hf-token", help="Hugging Face access token (hf_...)."
    ),
    tracker_token: str = typer.Option(
        ..., "--tracker-token", help="Tracker token (hex/random)."
    ),
):
    try:
        _set_key_in_keyring(TRACKRING_SERVICE, TRACK_HF_USERNAME, hf_token)
        _set_key_in_keyring(TRACKRING_SERVICE, TRACK_TOKEN_USERNAME, tracker_token)
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[green]Saved tracking tokens to Keychain.[/green]")


@app.command()
def tracker_logout():
    try:
        _delete_key_in_keyring(TRACKRING_SERVICE, TRACK_HF_USERNAME)
        _delete_key_in_keyring(TRACKRING_SERVICE, TRACK_TOKEN_USERNAME)
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[yellow]Removed tracking tokens from Keychain (if they existed).[/yellow]")


Size = Union[int, Tuple[int, int]]

PRESETS: dict[str, dict[str, object]] = {
    "square": {"size": (1000, 1000), "margins": (111, 111, 111, 111)},
    "square-xl": {"size": (1400, 1400), "margins": (155, 155, 155, 155)},
    "landscape": {
        "size": (1920, 1080),
        "margins": (120, 120, 120, 120),
    },
    "portrait": {
        "size": (1080, 1920),
        "margins": (120, 120, 120, 120),
    },
}


def parse_out_size(value: str) -> Size:
    s = (value or "").strip().lower()
    if not s:
        raise typer.BadParameter("out-size cannot be empty")

    if "x" in s:
        w_str, h_str = s.split("x", 1)
        try:
            w, h = int(w_str.strip()), int(h_str.strip())
        except ValueError:
            raise typer.BadParameter('out-size must look like "1000" or "1000x1000"')
        if w < 1 or h < 1:
            raise typer.BadParameter("out-size width/height must be >= 1")
        return (w, h)

    try:
        n = int(s)
    except ValueError:
        raise typer.BadParameter('out-size must look like "1000" or "1000x1000"')
    if n < 1:
        raise typer.BadParameter("out-size must be >= 1")
    return n


def _size_to_wh(size: Size) -> tuple[int, int]:
    if isinstance(size, int):
        return size, size
    return int(size[0]), int(size[1])


def default_margins_for_size(size: Size) -> tuple[int, int, int, int]:
    w, h = _size_to_wh(size)
    if w == 1000 and h == 1000:
        return (111, 111, 111, 111)

    base_ratio = 111 / 1000.0
    m = int(round(min(w, h) * base_ratio))
    m = max(0, m)
    return (m, m, m, m)


def resolve_size_and_margins(
    preset: Optional[str],
    out_size: str,
    margin_left: Optional[int],
    margin_right: Optional[int],
    margin_top: Optional[int],
    margin_bottom: Optional[int],
) -> tuple[Size, int, int, int, int]:
    user_set_any = any(
        v is not None for v in (margin_left, margin_right, margin_top, margin_bottom)
    )
    user_set_all = all(
        v is not None for v in (margin_left, margin_right, margin_top, margin_bottom)
    )
    if user_set_any and not user_set_all:
        raise typer.BadParameter(
            "If you set any margin, you must set all four: "
            "--margin-left/--margin-right/--margin-top/--margin-bottom"
        )

    if preset:
        key = preset.strip().lower()
        if key not in PRESETS:
            valid = ", ".join(PRESETS.keys())
            raise typer.BadParameter(
                f"Unknown preset '{preset}'. Valid presets: {valid}"
            )

        size = PRESETS[key]["size"]
        if user_set_all:
            ml, mr, mt, mb = (
                int(margin_left),
                int(margin_right),
                int(margin_top),
                int(margin_bottom),
            )
        else:
            ml, mr, mt, mb = PRESETS[key]["margins"]
        return size, int(ml), int(mr), int(mt), int(mb)

    size = parse_out_size(out_size)
    if user_set_all:
        return (
            size,
            int(margin_left),
            int(margin_right),
            int(margin_top),
            int(margin_bottom),
        )

    ml, mr, mt, mb = default_margins_for_size(size)
    return size, ml, mr, mt, mb


def run_impl(
    input_dir: Path = Path("input"),
    output_dir: Path = Path("output"),
    out_size: Size = 1000,
    margin_left: int = 111,
    margin_right: int = 111,
    margin_top: int = 111,
    margin_bottom: int = 111,
    remove_size: str = "auto",
    api_key: Optional[str] = None,
    use_keyring: bool = True,
    embed_xmp: bool = True,
    xmp_sidecar: bool = False,
) -> None:
    hf_token, tracker_token = _resolve_tracking_tokens(use_keyring=use_keyring)

    key = resolve_api_key(api_key, use_keyring=use_keyring)
    if not key:
        print("[yellow]No remove.bg API key found.[/yellow]")
        api_key = typer.prompt(
            "Paste your remove.bg API key (this will be saved securely)",
            hide_input=True,
        )
        try:
            _set_key_in_keyring(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
            print("[green]API key saved. You won’t be asked again.[/green]")
            key = api_key
        except Exception:
            print("[red]Could not save key automatically.[/red]")
            raise typer.Exit(code=2)

    run_id = str(uuid4())
    t0 = time.time()

    result: ProcessResult = process_folder(
        input_dir=input_dir,
        output_dir=output_dir,
        api_key=key,
        out_size=out_size,
        margin_left=margin_left,
        margin_right=margin_right,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        remove_size=remove_size,
        out_ext=".jpg",
        xmp_tool="removebg-square-cli",
        embed_png_xmp=embed_xmp,
        also_write_xmp_sidecar=xmp_sidecar,
        run_id=run_id,
    )

    if result.processed == 0 and result.unprocessed == 0:
        print(f"[yellow]No images found in:[/yellow] {input_dir.resolve()}")
        raise typer.Exit(code=1)

    print(
        f"[green]Done.[/green] Wrote {len(result.written)} file(s) to {output_dir.resolve()}"
    )
    print(
        f"[cyan]Counts:[/cyan] processed={result.processed}, unprocessed={result.unprocessed}"
    )

    if hf_token and tracker_token:
        _post_run(
            hf_token,
            tracker_token,
            run_id=run_id,
            processed=result.processed,
            unprocessed=result.unprocessed,
            processed_files=result.processed_files,
            unprocessed_files=result.unprocessed_files,
            elapsed_s=(time.time() - t0),
            tool="removebg-square-cli",
        )


@app.command()
def run(
    input_dir: Path = typer.Option(
        Path("input"),
        "--input-dir",
        "-i",
        exists=False,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        "-o",
        exists=False,
        file_okay=False,
        dir_okay=True,
    ),
    preset: Optional[str] = typer.Option(
        None,
        "--preset",
        help="Size preset: square, square-xl, landscape, portrait",
    ),
    out_size: str = typer.Option(
        "1000x1000",
        "--out-size",
        help='Manual canvas size: "1000" or "WxH" like "1920x1080". Ignored if --preset is set.',
    ),
    margin_left: Optional[int] = typer.Option(
        None,
        "--margin-left",
        min=0,
        help="Left margin (set all four to override defaults).",
    ),
    margin_right: Optional[int] = typer.Option(
        None,
        "--margin-right",
        min=0,
        help="Right margin (set all four to override defaults).",
    ),
    margin_top: Optional[int] = typer.Option(
        None,
        "--margin-top",
        min=0,
        help="Top margin (set all four to override defaults).",
    ),
    margin_bottom: Optional[int] = typer.Option(
        None,
        "--margin-bottom",
        min=0,
        help="Bottom margin (set all four to override defaults).",
    ),
    remove_size: str = typer.Option(
        "auto",
        "--remove-size",
        help='remove.bg "size" param, e.g. auto, preview, full.',
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="remove.bg API key (overrides env/keychain).",
    ),
    use_keyring: bool = typer.Option(
        True,
        "--use-keyring/--no-keyring",
        help="Allow using Keychain if available.",
    ),
    embed_xmp: bool = typer.Option(
        True,
        "--embed-xmp/--no-embed-xmp",
        help="Embed XMP into output PNG via iTXt XML:com.adobe.xmp.",
    ),
    xmp_sidecar: bool = typer.Option(
        False,
        "--xmp-sidecar/--no-xmp-sidecar",
        help="Also write a .png.xmp sidecar file.",
    ),
):
    resolved_size, ml, mr, mt, mb = resolve_size_and_margins(
        preset=preset,
        out_size=out_size,
        margin_left=margin_left,
        margin_right=margin_right,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
    )

    run_impl(
        input_dir=input_dir,
        output_dir=output_dir,
        out_size=resolved_size,
        margin_left=ml,
        margin_right=mr,
        margin_top=mt,
        margin_bottom=mb,
        remove_size=remove_size,
        api_key=api_key,
        use_keyring=use_keyring,
        embed_xmp=embed_xmp,
        xmp_sidecar=xmp_sidecar,
    )


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        run_impl()
