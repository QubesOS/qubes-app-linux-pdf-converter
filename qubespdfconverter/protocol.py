#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later

"""Shared qrexec protocol helpers."""

from dataclasses import dataclass


MAX_PAGES = 10000
MAX_OUTPUT_SIZE = 10 * 1024 * 1024 * 1024


class OutputFileError(Exception):
    """Raised if an invalid trusted file header was received."""


class PageError(Exception):
    """Raised if an invalid number of pages was received."""


@dataclass(frozen=True)
class TrustedOutput:
    suffix: str
    size: int


def parse_output_header(untrusted_header):
    """Parse the first server response line."""
    if untrusted_header.startswith("FILE "):
        try:
            _, suffix, size = untrusted_header.split(" ", 2)
            size = int(size)
        except ValueError as e:
            raise OutputFileError("Invalid trusted file header") from e

        if not suffix.isalnum() or not 1 <= size <= MAX_OUTPUT_SIZE:
            raise OutputFileError("Invalid trusted file header")

        return TrustedOutput(suffix, size)

    try:
        pagenums = int(untrusted_header)
    except ValueError as e:
        raise ValueError("Failed to receive page count") from e

    if 1 <= pagenums <= MAX_PAGES:
        return pagenums

    raise PageError("Invalid page count")
