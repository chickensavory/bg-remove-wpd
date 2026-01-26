from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import print

from .core import process_folder

app = typer.Typer(
    add_completion=False,
    help="Batch remove.bg + square-canvas formatter.",
)

KEYRING_SERVICE = "removebg-square-cli"
KEYRING_USERNAME = "removebg_api_key"


def _get_key_from_keyring() -> Optional[str]:
    try:
        import keyring
    except Exception:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None


def _set_key_in_keyring(api_key: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)


def _delete_key_in_keyring() -> None:
    import keyring

    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass


def resolve_api_key(api_key: Optional[str], use_keyring: bool) -> Optional[str]:
    if api_key:
        return api_key

    env_key = os.environ.get("REMOVEBG_API_KEY")
    if env_key:
        return env_key

    if use_keyring:
        kr = _get_key_from_keyring()
        if kr:
            return kr

    return None


@app.command()
def login(
    api_key: str = typer.Option(..., "--api-key", help="Your remove.bg API key."),
):
    try:
        _set_key_in_keyring(api_key)
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[green]Saved API key to Keychain.[/green]")


@app.command()
def logout():
    try:
        _delete_key_in_keyring()
    except ModuleNotFoundError:
        raise typer.Exit(code=2)
    print("[yellow]Removed API key from Keychain (if it existed).[/yellow]")


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
    key = resolve_api_key(api_key, use_keyring=use_keyring)
    if not key:
        print("[yellow]No API key found.[/yellow]")
        api_key = typer.prompt(
            "Paste your remove.bg API key (this will be saved securely)",
            hide_input=True,
        )
        try:
            _set_key_in_keyring(api_key)
            print("[green]API key saved. You won’t be asked again.[/green]")
            key = api_key
        except Exception:
            print("[red]Could not save key automatically.[/red]")
            raise typer.Exit(code=2)

    written = process_folder(
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

    if not written:
        print(f"[yellow]No images found in:[/yellow] {input_dir.resolve()}")
        raise typer.Exit(code=1)

    print(
        f"[green]Done.[/green] Wrote {len(written)} file(s) to {output_dir.resolve()}"
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