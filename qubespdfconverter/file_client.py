#!/usr/bin/python3
# -*- coding: utf-8 -*-

import asyncio
import click
import logging
import sys

from pathlib import Path

from qubespdfconverter import client as pdf_client


@click.command()
@click.option(
    "-b",
    "--batch",
    type=click.IntRange(1),
    default=50,
    metavar="SIZE",
    help="Maximum number of conversion tasks"
)
@click.option(
    "-a",
    "--archive",
    type=Path,
    default=Path(Path.home(), "QubesUntrustedPDFs"),
    metavar="PATH",
    help="Directory for storing archived files"
)
@click.option(
    "-i",
    "--in-place",
    is_flag=True,
    help="Replace original files instead of archiving them"
)
@click.option(
    "-r",
    "--resolution",
    type=click.IntRange(75, 4800),
    nargs=1,
    default=pdf_client.RESOLUTION,
    metavar="RESOLUTION",
    help="Resolution of output. default is 300 ppi"
)
@click.option(
    "-p",
    "--password",
    default="",
    metavar="PASSWORD",
    help="Password for encrypted PDF files"
)
@click.option(
    "--ocr-lang",
    default=None,
    callback=pdf_client.validate_ocr_lang,
    metavar="LANGUAGE",
    help="Tesseract language code for OCR output"
)
@click.argument(
    "files",
    type=Path,
    nargs=-1,
    callback=pdf_client.validate_paths,
    metavar="[FILES ...]"
)
@pdf_client.modify_click_errors
def main(**params):
    logging.basicConfig(format="error: %(message)s")

    if not params["files"]:
        print("No files to sanitize.")
        return

    sys.exit(asyncio.run(pdf_client.run(params)))


if __name__ == "__main__":
    main()
