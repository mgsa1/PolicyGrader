"""Pure tests for src.vision.frames — no video files, no API."""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from src.vision.frames import encode_png_b64, resize_long_edge, sample_indices


class TestSampleIndices:
    def test_empty(self) -> None:
        assert sample_indices(0, 5) == []

    def test_fewer_than_count_returns_all(self) -> None:
        assert sample_indices(3, 10) == [0, 1, 2]

    def test_evenly_spaced(self) -> None:
        # 10 frames, 5 samples -> first and last are pinned, middle is even.
        out = sample_indices(10, 5)
        assert out[0] == 0
        assert out[-1] == 9
        assert len(out) == 5
        assert out == sorted(out)


class TestResizeLongEdge:
    def test_no_change_when_target_matches(self) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out = resize_long_edge(frame, 640)
        assert out.shape == (480, 640, 3)

    def test_landscape_long_edge(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        out = resize_long_edge(frame, 50)
        # long edge = 200 -> 50; aspect 2:1 -> short edge ~25
        assert out.shape[1] == 50
        assert out.shape[0] == 25

    def test_portrait_long_edge(self) -> None:
        frame = np.zeros((200, 100, 3), dtype=np.uint8)
        out = resize_long_edge(frame, 50)
        assert out.shape[0] == 50
        assert out.shape[1] == 25


class TestEncodePngB64:
    def test_roundtrip(self) -> None:
        frame = (np.random.default_rng(0).integers(0, 256, size=(8, 8, 3))).astype(np.uint8)
        encoded = encode_png_b64(frame)
        # Decodes as a valid PNG of the right size.
        raw = base64.standard_b64decode(encoded)
        img = Image.open(io.BytesIO(raw))
        assert img.size == (8, 8)
        assert img.mode == "RGB"
        assert np.array_equal(np.asarray(img), frame)
