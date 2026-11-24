import pytest

from app.providers import Completion
from app.router import RuleRouter
from app.verifiers import EditFormatVerifier, JsonVerifier


def comp(text, finish="stop"):
    return Completion(text=text, finish_reason=finish, tokens_in=1, tokens_out=1, model="m")


V = EditFormatVerifier()

VALID_DIFF = "```python\nfile.py\n<<<<<<< SEARCH\na = 1\n=======\na = 2\n>>>>>>> REPLACE\n```\n"


@pytest.mark.parametrize("text,ok", [
    (VALID_DIFF, True),
    ("Just an explanation with no code.", True),
    ("```python\nx = 1\n```\n", True),
    ("```python\ndef broken(:\n```\n", False),
    ("<<<<<<< SEARCH\na\n=======\nb\n", False),
    ("a\n=======\nb\n>>>>>>> REPLACE\n", False),
    ("```python\nx = 1\n", False),
    ("   \n", False),
])
def test_edit_format_verifier(text, ok):
    assert V.check(comp(text), {}).passed is ok


def test_truncated_reply_fails():
    assert V.check(comp("fine", finish="length"), {}).passed is False


def test_json_verifier_only_applies_when_requested():
    j = JsonVerifier()
    assert j.check(comp("not json"), {}).passed is True
    req = {"response_format": {"type": "json_object"}}
    assert j.check(comp("not json"), req).passed is False
    assert j.check(comp('{"a": 1}'), req).passed is True


def test_router_uses_last_user_message_not_giant_system_prompt():
    r = RuleRouter()
    huge_system = {"role": "system", "content": "refactor architecture race condition " * 500}
    easy = r.decide([huge_system, {"role": "user", "content": "fix typo"}], 2, 0.45)
    assert easy.tier_index == 0


def test_router_exposes_reason_and_features():
    d = RuleRouter().decide([{"role": "user", "content": "Refactor this"}], 2, 0.45)
    assert d.tier_index == 1 and "hard words" in d.reason and d.features["hard_hits"] == ["refactor"]
