"""Core data models for the Smart Code Reviewer.

These dataclasses are the shared vocabulary between the static-analysis engine,
the Claude-powered reviewer, and the Streamlit UI. Keeping them in one place
means a "Finding" looks identical whether it came from the AST walker or the LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """How much a finding should worry a reviewer, worst first."""

    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    INFO = "Info"


class Dimension(str, Enum):
    """The three lenses every piece of code is graded through."""

    READABILITY = "Readability"
    STRUCTURE = "Structure"
    MAINTAINABILITY = "Maintainability"


# Points deducted from a dimension's score per finding of each severity.
SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.CRITICAL: 22.0,
    Severity.MAJOR: 11.0,
    Severity.MINOR: 4.5,
    Severity.INFO: 1.0,
}

# A calm, accessible palette (red → amber → blue) used across the UI.
SEVERITY_COLOR: dict[Severity, str] = {
    Severity.CRITICAL: "#E5484D",
    Severity.MAJOR: "#F76808",
    Severity.MINOR: "#E0A726",
    Severity.INFO: "#5B8DEF",
}

SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
    Severity.INFO: 3,
}


@dataclass
class Finding:
    """A single issue raised against the code."""

    dimension: Dimension
    severity: Severity
    title: str
    message: str
    suggestion: str = ""
    line: Optional[int] = None
    rule_id: str = ""
    source: str = "static"  # "static" (heuristic engine) or "ai" (Claude)

    def sort_key(self) -> tuple:
        return (SEVERITY_RANK[self.severity], self.line or 1_000_000)


@dataclass
class DimensionScore:
    dimension: Dimension
    score: float
    grade: str


@dataclass
class ReviewResult:
    """Everything the UI needs to render one review."""

    language: str
    findings: list[Finding] = field(default_factory=list)
    dimension_scores: dict[Dimension, DimensionScore] = field(default_factory=dict)
    overall_score: float = 100.0
    overall_grade: str = "A"
    metrics: dict[str, object] = field(default_factory=dict)
    summary: str = ""
    refactor: str = ""
    ai_used: bool = False

    def findings_for(self, dimension: Dimension) -> list[Finding]:
        return [f for f in self.findings if f.dimension == dimension]

    def counts_by_severity(self) -> dict[Severity, int]:
        counts = {s: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity] += 1
        return counts
