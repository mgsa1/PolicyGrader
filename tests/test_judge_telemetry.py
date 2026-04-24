"""Mocked-client tests for the judge's telemetry-block wiring.

Verifies the user-message shape: telemetry path provided AND file exists
→ a final text block containing "Sim telemetry"; otherwise → no such block.
The Anthropic client is mocked, so no API tokens are spent.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.schemas import RolloutTelemetry, TelemetryRow
from src.vision import judge as judge_mod


def _canned_image_blocks(n: int) -> tuple[list[dict[str, object]], list[int]]:
    blocks: list[dict[str, object]] = []
    for i in range(n):
        blocks.append({"type": "text", "text": f"Frame {i}:"})
        blocks.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": "x"},
            }
        )
    return blocks, list(range(n))


def _canned_response_json() -> str:
    return (
        '{"per_frame_observations": [],'
        ' "frame_index": 0,'
        ' "taxonomy_label": "approach_miss",'
        ' "point": null,'
        ' "description": "test"}'
    )


class _MockMessages:
    def __init__(self) -> None:
        self.last_call_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.last_call_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=_canned_response_json())],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


class _MockClient:
    def __init__(self) -> None:
        self.messages = _MockMessages()


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> _MockClient:
    """Patch _build_image_blocks so we don't need a real mp4 on disk."""
    monkeypatch.setattr(judge_mod, "_build_image_blocks", lambda *_a, **_k: _canned_image_blocks(4))
    return _MockClient()


def _write_telemetry(path: Path, n_rows: int) -> None:
    rows = [
        TelemetryRow(
            step_index=i,
            gripper_aperture=1.0 - i * 0.2,
            ee_to_cube_m=0.18 - i * 0.04,
            cube_z_above_table_m=i * 0.005,
            cube_xy_drift_m=i * 0.002,
            contact_flag=(i >= 2),
        )
        for i in range(n_rows)
    ]
    tel = RolloutTelemetry(rollout_id="t", fps=20, rows=rows)
    path.write_text(tel.model_dump_json())


class TestJudgeTelemetryWiring:
    def test_no_telemetry_path_omits_block(self, mock_client: _MockClient) -> None:
        judge_mod.judge(Path("/dev/null/video.mp4"), client=mock_client)  # type: ignore[arg-type]

        content = mock_client.messages.last_call_kwargs["messages"][0]["content"]
        assert not any(
            block.get("type") == "text" and "Sim telemetry" in block.get("text", "")
            for block in content
        )
        # And the system prompt should NOT mention telemetry either.
        assert "telemetry" not in mock_client.messages.last_call_kwargs["system"].lower()

    def test_telemetry_file_appended_as_text_block(
        self, mock_client: _MockClient, tmp_path: Path
    ) -> None:
        tel_path = tmp_path / "r1.telemetry.json"
        _write_telemetry(tel_path, n_rows=4)

        judge_mod.judge(
            Path("/dev/null/video.mp4"),  # type: ignore[arg-type]
            client=mock_client,
            telemetry_path=tel_path,
        )

        content = mock_client.messages.last_call_kwargs["messages"][0]["content"]
        # Last block must be the telemetry text block.
        assert content[-1]["type"] == "text"
        assert "Sim telemetry" in content[-1]["text"]
        # All five channel columns should appear in the rendered table.
        for col in ["gripper", "ee→cube", "cube_z", "cube_xy", "contact"]:
            assert col in content[-1]["text"]
        # System prompt should now reference telemetry as anchoring evidence.
        assert "telemetry" in mock_client.messages.last_call_kwargs["system"].lower()

    def test_missing_telemetry_file_falls_back_silently(
        self, mock_client: _MockClient, tmp_path: Path
    ) -> None:
        """Pointing at a nonexistent telemetry file must NOT crash — judge degrades."""
        judge_mod.judge(
            Path("/dev/null/video.mp4"),  # type: ignore[arg-type]
            client=mock_client,
            telemetry_path=tmp_path / "does-not-exist.telemetry.json",
        )

        content = mock_client.messages.last_call_kwargs["messages"][0]["content"]
        assert not any(
            block.get("type") == "text" and "Sim telemetry" in block.get("text", "")
            for block in content
        )


class TestRenderTelemetryBlock:
    def test_renders_only_sampled_rows(self) -> None:
        rows = [
            TelemetryRow(
                step_index=i,
                gripper_aperture=1.0,
                ee_to_cube_m=0.1,
                cube_z_above_table_m=0.0,
                cube_xy_drift_m=0.0,
                contact_flag=(i == 5),
            )
            for i in range(10)
        ]
        tel = RolloutTelemetry(rollout_id="t", fps=20, rows=rows)
        out = judge_mod._render_telemetry_block(tel, [0, 5, 9])

        # Three data rows (sampled indices 0/1/2) plus header + title = 5 lines.
        assert len(out.splitlines()) == 5
        # The contact mark must appear on the row sourced from step_index=5
        # (sampled index 1 → second data line).
        data_lines = out.splitlines()[2:]
        assert "✓" in data_lines[1]
        assert "-" in data_lines[0]
        assert "-" in data_lines[2]

    def test_out_of_bounds_step_indices_skipped(self) -> None:
        rows = [
            TelemetryRow(
                step_index=0,
                gripper_aperture=1.0,
                ee_to_cube_m=0.1,
                cube_z_above_table_m=0.0,
                cube_xy_drift_m=0.0,
                contact_flag=False,
            )
        ]
        tel = RolloutTelemetry(rollout_id="t", fps=20, rows=rows)
        # original_indices includes 5, but telemetry only has row 0 → row 5 is silently skipped.
        out = judge_mod._render_telemetry_block(tel, [0, 5])
        assert len(out.splitlines()) == 3  # title + header + 1 data row
