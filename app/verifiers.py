from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .providers import Completion

SEARCH_RE = re.compile(r"^<{5,9} SEARCH\s*$")
DIVIDER_RE = re.compile(r"^={5,9}\s*$")
REPLACE_RE = re.compile(r"^>{5,9} REPLACE\s*$")
FENCE_RE = re.compile(r"^```(\w*)\s*$")


@dataclass
class Verdict:
    passed: bool
    evidence: str
    name: str
    ms: float = 0.0


class Verifier(Protocol):
    name: str

    def check(self, completion: Completion, request: dict[str, Any]) -> Verdict: ...


def _check_diff_blocks(lines: list[str]) -> str | None:
    """Return an error message if SEARCH/REPLACE blocks are malformed, else None."""
    state = "outside"
    for i, line in enumerate(lines, 1):
        if SEARCH_RE.match(line):
            if state != "outside":
                return f"line {i}: SEARCH marker inside an open block"
            state = "search"
        elif DIVIDER_RE.match(line):
            if state == "search":
                state = "replace"
            elif state == "replace":
                return f"line {i}: second divider inside one block"
        elif REPLACE_RE.match(line):
            if state != "replace":
                return f"line {i}: REPLACE marker without a SEARCH and divider before it"
            state = "outside"
    if state != "outside":
        return "unterminated SEARCH/REPLACE block (reply looks cut off or malformed)"
    return None


def _python_fences_outside_diffs(lines: list[str]) -> tuple[list[tuple[int, str]], bool]:
    """Collect fenced python blocks that are not SEARCH/REPLACE fragments.
    Returns (blocks, fences_balanced)."""
    blocks: list[tuple[int, str]] = []
    in_fence = False
    lang = ""
    buf: list[str] = []
    start = 0
    for i, line in enumerate(lines, 1):
        m = FENCE_RE.match(line)
        if m and not in_fence:
            in_fence, lang, buf, start = True, m.group(1).lower(), [], i
        elif line.strip() == "```" and in_fence:
            body = "\n".join(buf)
            if lang in ("python", "py") and "<<<<<<< SEARCH" not in body:
                blocks.append((start, body))
            in_fence = False
        elif in_fence:
            buf.append(line)
    return blocks, not in_fence


class EditFormatVerifier:
    """Checks what can be checked from the reply alone (no access to the user's repo):
    not truncated, not empty, SEARCH/REPLACE blocks well-formed, fenced python parses."""

    name = "edit_format"

    def __init__(self, check_python_syntax: bool = True):
        self.check_python_syntax = check_python_syntax

    def check(self, completion: Completion, request: dict[str, Any]) -> Verdict:
        t0 = time.perf_counter()
        verdict = self._check(completion)
        verdict.ms = (time.perf_counter() - t0) * 1000
        return verdict

    def _check(self, completion: Completion) -> Verdict:
        text = completion.text
        if completion.finish_reason == "length":
            return Verdict(False, "reply was truncated (finish_reason=length)", self.name)
        if not text.strip():
            return Verdict(False, "reply was empty", self.name)
        lines = text.splitlines()
        err = _check_diff_blocks(lines)
        if err:
            return Verdict(False, err, self.name)
        blocks, balanced = _python_fences_outside_diffs(lines)
        if not balanced:
            return Verdict(False, "unclosed code fence (reply looks cut off)", self.name)
        if self.check_python_syntax:
            for start, body in blocks:
                try:
                    ast.parse(body)
                except SyntaxError as exc:
                    return Verdict(False, f"python code block at line {start} has a syntax error: {exc.msg}", self.name)
        return Verdict(True, "format checks passed", self.name)


class JsonVerifier:
    """Applies only when the request asked for JSON output."""

    name = "json"

    def check(self, completion: Completion, request: dict[str, Any]) -> Verdict:
        t0 = time.perf_counter()
        fmt = (request.get("response_format") or {}).get("type")
        if fmt not in ("json_object", "json_schema"):
            return Verdict(True, "not applicable", self.name, 0.0)
        try:
            json.loads(completion.text)
            ok, ev = True, "valid JSON"
        except json.JSONDecodeError as exc:
            ok, ev = False, f"invalid JSON: {exc.msg}"
        return Verdict(ok, ev, self.name, (time.perf_counter() - t0) * 1000)


class VerifierChain:
    name = "chain"

    def __init__(self, verifiers: list[Verifier]):
        self.verifiers = verifiers

    def check(self, completion: Completion, request: dict[str, Any]) -> Verdict:
        total_ms = 0.0
        for v in self.verifiers:
            verdict = v.check(completion, request)
            total_ms += verdict.ms
            if not verdict.passed:
                verdict.ms = total_ms
                return verdict
        return Verdict(True, "all checks passed", self.name, total_ms)


def default_verifier() -> VerifierChain:
    return VerifierChain([EditFormatVerifier(), JsonVerifier()])
