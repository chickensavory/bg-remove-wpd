from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .core import process_folder

app = typer.Typer(
    add_completion=False,
    help="Batch remove backgrounds with remove.bg and output squared images.",
)


def run_impl(
    input_dir: Path = Path("input"),
    output_dir: Path = Path("output"),
    out_size: int = 1000,
    padding: int = 50,
    remove_size: str = "auto",
    api_key: Optional[str] = None,
) -> None:
    written = process_folder(
        input_dir=input_dir,
        output_dir=output_dir,
        api_key=api_key,
        out_size=out_size,
        padding=padding,
        remove_size=remove_size,
    )
    typer.echo(f"Wrote {len(written)} file(s) to: {output_dir}")


@app.command()
def run(
    input_dir: Path = typer.Option(
        Path("input"),
        "--input-dir",
        "-i",
        help="Folder of input images.",
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        "-o",
        help="Folder for output images.",
        file_okay=False,
        dir_okay=True,
        writable=True,
    ),
    out_size: int = typer.Option(
        1000,
        "--out-size",
        help="Final output square size in pixels.",
        min=1,
    ),
    padding: int = typer.Option(
        50,
        "--padding",
        help="Padding around the subject (in pixels) after background removal.",
        min=0,
    ),
    remove_size: str = typer.Option(
        "auto",
        "--remove-size",
        help='remove.bg "size" parameter (e.g. auto, preview, full).',
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="remove.bg API key (overrides env var).",
    ),
) -> None:
    run_impl(
        input_dir=input_dir,
        output_dir=output_dir,
        out_size=out_size,
        padding=padding,
        remove_size=remove_size,
        api_key=api_key,
    )


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_impl()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
