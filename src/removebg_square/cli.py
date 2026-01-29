from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests
import typer
from rich import print

from .core import process_folder, ProcessResult

app = typer.Typer(
    add_completion=False,
    help="Batch remove.bg + square-canvas formatter.",
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


def _post_counts(
    hf_token: str, tracker_token: str, processed: int, unprocessed: int
) -> None:
    try:
        resp = requests.post(
            TRACK_ENDPOINT,
            headers={
                "Authorization": f"Bearer {hf_token}",
                "X-Tracker-Token": tracker_token,
                "Content-Type": "application/json",
            },
            json={"processed": int(processed), "unprocessed": int(unprocessed)},
            timeout=6,
        )
        if resp.status_code >= 200 and resp.status_code < 300:
            print(
                f"[dim][TRACK][/dim] sent counts: processed={processed}, unprocessed={unprocessed}"
            )
            return

        body = (resp.text or "")[:200].strip()
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


def run_impl(
    input_dir: Path = Path("input"),
    output_dir: Path = Path("output"),
    out_size: int = 1000,
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
        out_ext=".png",
        xmp_tool="removebg-square-cli",
        embed_png_xmp=embed_xmp,
        also_write_xmp_sidecar=xmp_sidecar,
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
        _post_counts(hf_token, tracker_token, result.processed, result.unprocessed)


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
    out_size: int = typer.Option(1000, "--out-size", min=1),
    margin_left: int = typer.Option(111, "--margin-left", min=0),
    margin_right: int = typer.Option(111, "--margin-right", min=0),
    margin_top: int = typer.Option(111, "--margin-top", min=0),
    margin_bottom: int = typer.Option(111, "--margin-bottom", min=0),
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
    run_impl(
        input_dir=input_dir,
        output_dir=output_dir,
        out_size=out_size,
        margin_left=margin_left,
        margin_right=margin_right,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
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
