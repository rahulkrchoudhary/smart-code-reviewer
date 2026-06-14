"""Claude-powered deep review layer (optional).

The static engine catches mechanical issues; Claude catches the things that need
*understanding* — unclear intent, misleading names, missing edge cases, a function
that's "fine" mechanically but does three unrelated things. It returns structured
findings (validated against a schema) plus a human summary and a suggested
refactor of the worst offender.

This layer is optional: if the `anthropic` package isn't installed or no API key
is configured, the app runs on the static engine alone.
"""
from __future__ import annotations

from typing import Literal, Optional

from .models import Dimension, Finding, Severity

DEFAULT_MODEL = "claude-opus-4-8"

# Map the model's string outputs back onto our enums.
_DIM_MAP = {
    "Readability": Dimension.READABILITY,
    "Structure": Dimension.STRUCTURE,
    "Maintainability": Dimension.MAINTAINABILITY,
}
_SEV_MAP = {
    "Critical": Severity.CRITICAL,
    "Major": Severity.MAJOR,
    "Minor": Severity.MINOR,
    "Info": Severity.INFO,
}


def is_available() -> bool:
    """True if the anthropic SDK is importable."""
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _build_schema_models():
    """Defined lazily so the module imports even without pydantic installed."""
    from pydantic import BaseModel, Field

    class AIFinding(BaseModel):
        dimension: Literal["Readability", "Structure", "Maintainability"]
        severity: Literal["Critical", "Major", "Minor", "Info"]
        title: str = Field(description="Short, specific headline for the issue")
        message: str = Field(description="What the problem is and why it matters")
        suggestion: str = Field(description="Concrete, actionable fix")
        line: Optional[int] = Field(
            default=None, description="1-based line number, or null if file-wide"
        )

    class AIReview(BaseModel):
        summary: str = Field(
            description="2-4 sentence overall assessment a senior reviewer "
            "would leave on the PR"
        )
        findings: list[AIFinding] = Field(
            description="The most important issues, most severe first"
        )
        refactor_title: str = Field(
            description="Name of the function/block the refactor improves"
        )
        refactored_snippet: str = Field(
            description="An improved version of the single worst section, with "
            "brief inline comments explaining the changes. Plain code, no fences."
        )

    return AIFinding, AIReview


_SYSTEM_PROMPT = """\
You are a meticulous senior software engineer doing a pre-merge code review.
You focus on three dimensions and nothing else:

- Readability: naming, clarity of intent, comments/docstrings, consistent style.
- Structure: function size, cyclomatic complexity, nesting, separation of concerns.
- Maintainability: duplication, error handling, dead code, testability, hidden coupling.

Rules:
- Report concrete, specific issues a human reviewer would actually flag. No vague
  "could be improved" filler.
- Prefer the highest-impact issues. It is fine to return few findings for clean code.
- Every finding must have an actionable suggestion.
- Be encouraging and professional in the summary, like a great teammate.
- For the refactor, pick the single worst section and rewrite just that, keeping
  behaviour identical. Output plain code only — no markdown fences.
"""


def review_with_ai(
    source: str,
    language: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> tuple[list[Finding], str, str]:
    """Return (findings, summary, refactor). Raises on configuration errors."""
    import anthropic

    _AIFinding, AIReview = _build_schema_models()
    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = (
        f"Review the following {language} code. Return structured findings, an "
        f"overall summary, and a refactor of the worst section.\n\n"
        f"```{language.lower()}\n{source}\n```"
    )

    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=AIReview,
    )

    review = response.parsed_output
    if review is None:
        raise RuntimeError(
            "Claude could not produce a structured review (it may have refused "
            "or hit the token limit). Try again or use a smaller snippet."
        )

    findings: list[Finding] = []
    for item in review.findings:
        findings.append(Finding(
            dimension=_DIM_MAP[item.dimension],
            severity=_SEV_MAP[item.severity],
            title=item.title,
            message=item.message,
            suggestion=item.suggestion,
            line=item.line,
            source="ai",
            rule_id="AI",
        ))

    refactor = review.refactored_snippet.strip()
    if review.refactor_title:
        refactor = f"# Suggested refactor — {review.refactor_title}\n{refactor}"

    return findings, review.summary.strip(), refactor
