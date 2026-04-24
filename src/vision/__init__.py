"""Single-call CoT vision judge over recorded rollout mp4s.

`judge(video_path) -> JudgeAnnotation` is the entry point. See
src/vision/judge.py for the sampling shape, prompt, and abstention semantics.
Frame IO + sampling helpers live in src/vision/frames.py.
"""
