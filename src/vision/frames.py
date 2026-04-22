"""Frame-IO helpers shared by both vision passes.

Reads an mp4 with imageio, samples frames at requested indices, resizes to a
target long-edge while preserving aspect, and base64-encodes as PNG for the
Anthropic Messages API. Kept separate so coarse_pass and fine_pass don't each
re-implement video loading.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import imageio.v3 as iio
import numpy as np
from PIL import Image


def read_frames(video_path: Path) -> list[np.ndarray[Any, Any]]:
    """Decode every frame of an mp4 into a list of HxWx3 uint8 arrays.

    Rollouts are short (≤ a few hundred frames at 20 fps -> ~10s) so loading
    everything into memory keeps the sampling code trivial.
    """
    return list(iio.imiter(str(video_path)))


def sample_indices(num_frames: int, count: int) -> list[int]:
    """Pick `count` evenly-spaced indices from a `num_frames`-long video.

    Returns a strictly-increasing list; clamped to `num_frames - 1` so it works
    on very short clips. If num_frames <= count, returns [0..num_frames-1].
    """
    if num_frames <= 0:
        return []
    if num_frames <= count:
        return list(range(num_frames))
    return [int(round(i * (num_frames - 1) / (count - 1))) for i in range(count)]


def resize_long_edge(frame: np.ndarray[Any, Any], target: int) -> np.ndarray[Any, Any]:
    """Resize so the longer edge equals `target`. Returns a fresh uint8 array."""
    h, w = frame.shape[:2]
    long_edge = max(h, w)
    if long_edge == target:
        return frame
    scale = target / long_edge
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    img = Image.fromarray(frame)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.asarray(img)


def encode_png_b64(frame: np.ndarray[Any, Any]) -> str:
    """Encode a HxWx3 uint8 frame as base64-encoded PNG (no data: prefix)."""
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")
