"""Two-pass vision judge over recorded rollout mp4s.

Pass 1 (coarse_pass): cheap binary verdict + failure frame range.
Pass 2 (fine_pass):  windowed 2576px taxonomy label + pixel point.

Both passes are pure functions: input is a path to an mp4 (and a frame
range for Pass 2), output is a Pydantic model from src.schemas.
"""
