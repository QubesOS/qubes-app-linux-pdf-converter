#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later

"""Shared qrexec protocol helpers."""

from dataclasses import dataclass


MAX_PAGES = 10000
MAX_OUTPUT_SIZE = 10 * 1024 * 1024 * 1024
MAX_VIDEO_RATE_PART = 1000000


class OutputFileError(Exception):
    """Raised if an invalid trusted file header was received."""


class PageError(Exception):
    """Raised if an invalid number of pages was received."""


@dataclass(frozen=True)
class VideoOutput:
    """Raw video stream metadata received from the server."""

    pixel_format: str
    width: int
    height: int
    fps_num: int
    fps_den: int
    frames: int
    size: int


def _parse_video_header(untrusted_header):
    # pylint: disable=too-many-boolean-expressions
    try:
        (
            _,
            pixel_format,
            width,
            height,
            fps_num,
            fps_den,
            frames,
            size,
        ) = untrusted_header.split(" ", 7)
        width = int(width)
        height = int(height)
        fps_num = int(fps_num)
        fps_den = int(fps_den)
        frames = int(frames)
        size = int(size)
    except ValueError as e:
        raise OutputFileError("Invalid video output header") from e

    if (
        pixel_format != "rgb24"
        or not 1 <= width <= 10000
        or not 1 <= height <= 10000
        or not 1 <= fps_num <= MAX_VIDEO_RATE_PART
        or not 1 <= fps_den <= MAX_VIDEO_RATE_PART
        or not 1 <= frames <= MAX_PAGES
    ):
        raise OutputFileError("Invalid video output header")

    expected_size = width * height * 3 * frames
    if size != expected_size or not 1 <= size <= MAX_OUTPUT_SIZE:
        raise OutputFileError("Invalid video output header")

    return VideoOutput(
        pixel_format,
        width,
        height,
        fps_num,
        fps_den,
        frames,
        size,
    )


def parse_output_header(untrusted_header):
    """Parse the first server response line."""
    if untrusted_header.startswith("VIDEO "):
        return _parse_video_header(untrusted_header)

    try:
        pagenums = int(untrusted_header)
    except ValueError as e:
        raise ValueError("Failed to receive page count") from e

    if 1 <= pagenums <= MAX_PAGES:
        return pagenums

    raise PageError("Invalid page count")
