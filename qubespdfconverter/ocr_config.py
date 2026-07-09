#!/usr/bin/python3
# -*- coding: utf-8 -*-

import configparser
import os

from pathlib import Path

from qubespdfconverter import ocr

CONFIG_DIR = "qubes-pdf-converter"
CONFIG_NAME = "ocr.conf"
SECTION = "ocr"
DEFAULT_LANGUAGE = "eng"


def config_path():
    """Return the OCR config path."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        base = Path(config_home)
    else:
        base = Path.home() / ".config"
    return base / CONFIG_DIR / CONFIG_NAME


def read_config(path=None):
    """Read OCR config from disk."""
    path = path or config_path()
    if not path.exists():
        return None

    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_section(SECTION):
        return None

    enabled = parser.getboolean(SECTION, "enabled", fallback=False)
    language = parser.get(SECTION, "language", fallback=DEFAULT_LANGUAGE)
    language = ocr.validate_language_code(language) or DEFAULT_LANGUAGE
    return enabled, language


def write_config(enabled, language=DEFAULT_LANGUAGE, path=None):
    """Write OCR config to disk."""
    path = path or config_path()
    language = ocr.validate_language_code(language) or DEFAULT_LANGUAGE

    parser = configparser.ConfigParser()
    parser[SECTION] = {
        "enabled": "yes" if enabled else "no",
        "language": language,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as config_file:
        parser.write(config_file)


def get_default_ocr_lang(path=None):
    """Return configured OCR language, or None if OCR is disabled/unconfigured."""
    config = read_config(path)
    if config is None:
        return None

    enabled, language = config
    if not enabled:
        return None
    return language


def config_exists(path=None):
    """Return whether OCR config exists."""
    path = path or config_path()
    return path.exists()
