from pydantic import BaseModel


class _Probe(BaseModel):
    name: str


def test_pydantic_v2_is_importable_and_validates() -> None:
    assert _Probe(name="ok").name == "ok"
