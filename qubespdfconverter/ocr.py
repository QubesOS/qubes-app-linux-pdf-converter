#!/usr/bin/python3
# -*- coding: utf-8 -*-

import importlib
import re

from pathlib import Path

LANG_RE = re.compile(r"^[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*$")

TESSDATA_DIRS = (
    Path("/usr/share/tessdata"),
    Path("/usr/share/tesseract/tessdata"),
    Path("/usr/share/tesseract-ocr/tessdata"),
    Path("/usr/share/tesseract-ocr/4.00/tessdata"),
    Path("/usr/share/tesseract-ocr/5/tessdata"),
)


class OcrDependencyError(RuntimeError):
    """Raised if optional OCR dependencies are missing."""


def validate_language_code(language):
    """Return a validated Tesseract language code."""
    if not language:
        return None

    if not LANG_RE.match(language):
        raise ValueError("OCR language must be a Tesseract language code")

    return language


def get_tessdata_dir():
    """Return a system tessdata directory."""
    for path in TESSDATA_DIRS:
        if path.is_dir():
            return path

    raise OcrDependencyError("Tesseract language data is required for OCR")


def check_language_data(language, tessdata_dir):
    """Check that all requested Tesseract language data files are available."""
    for lang in language.split("+"):
        if not (tessdata_dir / f"{lang}.traineddata").is_file():
            raise OcrDependencyError(
                f"Tesseract language data for {lang!r} is required for OCR"
            )


def import_fitz():
    """Import PyMuPDF lazily so OCR remains optional."""
    try:
        return importlib.import_module("fitz")
    except ImportError as exc:
        raise OcrDependencyError("PyMuPDF is required for OCR") from exc


def check_available(language):
    """Validate optional OCR dependencies before starting conversion."""
    validate_language_code(language)
    import_fitz()
    tessdata_dir = get_tessdata_dir()
    check_language_data(language, tessdata_dir)
    return tessdata_dir


def create_document():
    """Create a PyMuPDF document for OCR output."""
    fitz = import_fitz()
    return fitz.Document()


def png_to_pdf_page(path, language, tessdata_dir, resolution):
    """Convert a sanitized PNG page to a searchable PDF page."""
    fitz = import_fitz()
    pixmap = fitz.Pixmap(str(path))
    pixmap.set_dpi(resolution, resolution)
    pdf_bytes = pixmap.pdfocr_tobytes(
        compress=True,
        language=language,
        tessdata=str(tessdata_dir),
    )
    return fitz.open("pdf", pdf_bytes)
