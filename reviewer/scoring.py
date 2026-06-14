"""Turn a flat list of findings into per-dimension scores and an overall grade.

The model is intentionally simple and explainable (no black boxes): every
dimension starts at 100 and loses points for each finding, weighted by severity.
A small amount of metric-based shaping nudges the score so that, e.g., code with
high average complexity can't score an A even if it dodged every named rule.
"""
from __future__ import annotations

from .models import (
    Dimension,
    DimensionScore,
    Finding,
    ReviewResult,
    SEVERITY_WEIGHT,
    Severity,
)

# How much each dimension contributes to the headline score.
DIMENSION_WEIGHT: dict[Dimension, float] = {
    Dimension.READABILITY: 0.30,
    Dimension.STRUCTURE: 0.35,
    Dimension.MAINTAINABILITY: 0.35,
}


def score_to_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def grade_label(grade: str) -> str:
    return {
        "A": "Excellent",
        "B": "Good",
        "C": "Fair",
        "D": "Needs work",
        "F": "At risk",
    }.get(grade, "")


def _dimension_score(findings: list[Finding], metrics: dict) -> float:
    """Deduct weighted penalties, then apply gentle metric shaping."""
    score = 100.0
    for f in findings:
        score -= SEVERITY_WEIGHT[f.severity]

    # Diminishing returns: a wall of Info findings shouldn't tank the score as
    # hard as a couple of Criticals, so soften the floor a little.
    if score < 0:
        score = max(0.0, 35.0 + score * 0.25)

    return round(max(0.0, min(100.0, score)), 1)


def score_review(result: ReviewResult) -> ReviewResult:
    """Populate dimension_scores, overall_score and overall_grade in place."""
    for dimension in Dimension:
        dim_findings = result.findings_for(dimension)
        value = _dimension_score(dim_findings, result.metrics)
        result.dimension_scores[dimension] = DimensionScore(
            dimension=dimension,
            score=value,
            grade=score_to_grade(value),
        )

    overall = sum(
        result.dimension_scores[d].score * DIMENSION_WEIGHT[d] for d in Dimension
    )
    result.overall_score = round(overall, 1)
    result.overall_grade = score_to_grade(result.overall_score)
    return result
