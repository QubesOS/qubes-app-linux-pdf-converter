#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import subprocess
import sys

from qubespdfconverter import ocr, ocr_config


def zenity_question(text):
    cmd = ["zenity", "--question", f"--text={text}"]
    return subprocess.run(cmd, check=False).returncode


def zenity_language(default):
    cmd = [
        "zenity",
        "--entry",
        "--title=OCR settings",
        "--text=Tesseract language code",
        f"--entry-text={default}",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="ignore").strip()


def configure():
    current = ocr_config.read_config()
    if current is None:
        language = ocr_config.DEFAULT_LANGUAGE
    else:
        _enabled, language = current

    question = (
        "Enable OCR for converted PDFs?\n\n"
        "OCR adds a searchable text layer when Tesseract language data is "
        "installed."
    )
    rc = zenity_question(question)
    if rc == 1:
        ocr_config.write_config(False, language)
        return 0
    if rc != 0:
        return rc

    language = zenity_language(language)
    if language is None:
        return 1

    try:
        ocr.validate_language_code(language)
    except ValueError:
        subprocess.run(
            ["zenity", "--error", "--text=Invalid OCR language code."],
            check=False,
        )
        return 1

    ocr_config.write_config(True, language)
    return 0


def print_args(configure_missing=False):
    if not ocr_config.config_exists():
        if not configure_missing:
            return 1
        if configure() != 0:
            return 1

    language = ocr_config.get_default_ocr_lang()
    if language:
        print(f"--ocr-lang\n{language}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Configure PDF converter OCR")
    parser.add_argument("--print-args", action="store_true")
    parser.add_argument("--configure-missing", action="store_true")
    args = parser.parse_args()

    if args.print_args:
        return print_args(args.configure_missing)

    return configure()


if __name__ == "__main__":
    sys.exit(main())
