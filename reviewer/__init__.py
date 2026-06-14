"""Smart Code Reviewer — review engine package.

Public surface:
    review(source, language, *, use_ai, api_key, model) -> ReviewResult
    detect_language(filename, source) -> str
    SUPPORTED_LANGUAGES
"""
from __future__ import annotations

from . import ai_reviewer
from .analyzer import analyze
from .models import (
    Dimension,
    DimensionScore,
    Finding,
    ReviewResult,
    SEVERITY_COLOR,
    SEVERITY_RANK,
    SEVERITY_WEIGHT,
    Severity,
)
from .scoring import grade_label, score_review, score_to_grade

SUPPORTED_LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Java", "Go", "C", "C++", "C#",
    "Ruby", "PHP", "Rust", "Kotlin", "Swift",
]

_EXT_MAP = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".go": "Go",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".rs": "Rust",
    ".kt": "Kotlin", ".swift": "Swift",
}


def detect_language(filename: str = "", source: str = "") -> str:
    """Guess the language from a filename extension, falling back to content."""
    name = (filename or "").lower()
    for ext, lang in _EXT_MAP.items():
        if name.endswith(ext):
            return lang
    # Content sniff as a last resort.
    head = source[:2000]
    if "def " in head and ("import " in head or "self" in head):
        return "Python"
    if "function " in head or "const " in head or "=>" in head:
        return "JavaScript"
    if "public class" in head or "System.out" in head:
        return "Java"
    if "package main" in head or "func " in head:
        return "Go"
    return "Python"


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Drop near-duplicate findings (same line + rule, or AI echoing a static hit)."""
    seen: set[tuple] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f.line, f.title.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def review(
    source: str,
    language: str,
    *,
    use_ai: bool = False,
    api_key: str = "",
    model: str = ai_reviewer.DEFAULT_MODEL,
) -> ReviewResult:
    """Run the full review pipeline and return a scored ReviewResult."""
    static_findings, metrics = analyze(source, language)

    result = ReviewResult(language=language, metrics=metrics)
    findings = list(static_findings)

    if use_ai and api_key:
        ai_findings, summary, refactor = ai_reviewer.review_with_ai(
            source, language, api_key=api_key, model=model
        )
        findings.extend(ai_findings)
        result.summary = summary
        result.refactor = refactor
        result.ai_used = True

    findings = _dedupe(findings)
    findings.sort(key=lambda f: f.sort_key())
    result.findings = findings

    score_review(result)
    return result


__all__ = [
    "review", "detect_language", "SUPPORTED_LANGUAGES",
    "ReviewResult", "Finding", "Dimension", "DimensionScore", "Severity",
    "SEVERITY_COLOR", "SEVERITY_RANK", "SEVERITY_WEIGHT",
    "score_to_grade", "grade_label", "ai_reviewer",
]
