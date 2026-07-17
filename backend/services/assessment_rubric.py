from dataclasses import dataclass
from typing import Mapping


RUBRIC_VERSION = "2026-07-16"

CRITERION_KEYS = (
    "technical_correctness",
    "course_alignment",
    "blooms_alignment",
    "clarity_solution",
    "materials_context",
)

RUBRIC_SNAPSHOT = {
    "version": RUBRIC_VERSION,
    "criteria": [
        {
            "key": "technical_correctness",
            "title": "Technical Correctness & Solvability",
            "weight": 30,
            "covers": "Accuracy + Solvability",
            "description": (
                "Thermodynamic correctness; valid equations, assumptions, units, signs, numerical results, "
                "and physical interpretation; sufficient and internally consistent data for a unique intended answer."
            ),
            "comment_prompt": (
                "Which equation, assumption, unit, datum, sign convention, or result needs correction or clarification?"
            ),
            "anchors": {
                "1": (
                    "Contains a substantive error, contradiction, missing essential information, or cannot be solved "
                    "reliably as written."
                ),
                "3": (
                    "Mostly correct and solvable, but has a minor error, implicit assumption, or local inconsistency "
                    "that should be repaired."
                ),
                "5": (
                    "Correct, precise, self-contained, internally consistent, uniquely answerable where intended, "
                    "and physically defensible."
                ),
            },
        },
        {
            "key": "course_alignment",
            "title": "Course Alignment & Concept Bridge",
            "weight": 25,
            "covers": "Course Alignment + Concept Bridge",
            "description": (
                "Alignment with MSE202 preparation, MSE302 target knowledge, requested difficulty and setting; "
                "explicit and meaningful transfer from the prerequisite concept to the later concept."
            ),
            "comment_prompt": (
                "What exactly is transferred from MSE202 to MSE302, and must students use that connection to solve "
                "the question?"
            ),
            "anchors": {
                "1": (
                    "Off-level, off-topic, or the two course concepts are merely named, isolated, or connected "
                    "inaccurately."
                ),
                "3": (
                    "Generally appropriate with a valid but somewhat superficial bridge, limited scope mismatch, "
                    "or uneven emphasis."
                ),
                "5": (
                    "Well matched to student preparation and assessment setting; the MSE202–MSE302 bridge is "
                    "explicit, central, and thermodynamically meaningful."
                ),
            },
        },
        {
            "key": "blooms_alignment",
            "title": "Bloom’s Taxonomy Alignment & Assessment Design",
            "weight": 10,
            "covers": "Bloom’s Taxonomy Alignment + Assessment Design",
            "description": (
                "Match between the Bloom’s taxonomy level specified in the instructor prompt and the observable work "
                "students must perform. Judge the actual reasoning required, not the action verb alone, and consider "
                "whether scaffolding, complexity, and workload suit the assessment setting."
            ),
            "comment_prompt": (
                "What must students actually do, and does that observable performance correspond to the Bloom’s level "
                "specified in the prompt?"
            ),
            "anchors": {
                "1": (
                    "Does not match the specified Bloom’s level. For example, the task asks only for recall or routine "
                    "substitution when Analyze, Evaluate, or Create was requested, or it demands higher-order synthesis "
                    "when a lower level was intended."
                ),
                "3": (
                    "Generally matches the specified level, but the demand is mixed, over-scaffolded, or only part of "
                    "the response requires performance at the target level."
                ),
                "5": (
                    "Clearly and consistently elicits the specified Bloom’s level through observable student performance, "
                    "with suitable complexity, scaffolding, and workload for the assessment setting."
                ),
            },
        },
        {
            "key": "clarity_solution",
            "title": "Clarity, Prompt Alignment & Solution Quality",
            "weight": 25,
            "covers": "Clarity + Prompt–Output Alignment + Solution Quality",
            "description": (
                "Clear wording, notation, data, deliverables, assumptions, constraints, and answer choices; faithful "
                "compliance with the instructor prompt; complete, auditable solution and answer key."
            ),
            "comment_prompt": (
                "Could students interpret the task consistently, and could an instructor verify every requested "
                "requirement and every essential solution step?"
            ),
            "anchors": {
                "1": (
                    "Ambiguous or cumbersome; misses central prompt requirements; solution or key is incorrect, "
                    "incomplete, or skips essential reasoning."
                ),
                "3": (
                    "Understandable and mostly compliant, but needs minor wording, formatting, algebra, units, "
                    "assumptions, or explanation improvements."
                ),
                "5": (
                    "Concise, student-ready, fully compliant with the request, and supported by a complete solution "
                    "with assumptions, units, physical meaning, and distractor analysis where applicable."
                ),
            },
        },
        {
            "key": "materials_context",
            "title": "Materials Science Context & Relevance",
            "weight": 10,
            "covers": "Materials Context",
            "description": (
                "Authenticity, specificity, plausibility, and instructional value of the materials science or "
                "engineering scenario."
            ),
            "comment_prompt": (
                "Does the context meaningfully support the thermodynamics or an engineering interpretation rather "
                "than merely naming a material?"
            ),
            "anchors": {
                "1": "Generic, decorative, implausible, or unrelated to the thermodynamic reasoning.",
                "3": (
                    "Relevant context is present but underdeveloped or contributes little to interpretation or "
                    "decision-making."
                ),
                "5": (
                    "Authentic and specific context that motivates the analysis and helps students interpret the "
                    "result in a materials engineering setting."
                ),
            },
        },
    ],
}


@dataclass(frozen=True)
class EvaluationCalculation:
    weighted_score: float
    critical_gate: str
    overall_decision: str
    instructor_readiness: str


def calculate_evaluation(scores: Mapping[str, int]) -> EvaluationCalculation:
    if set(scores) != set(CRITERION_KEYS):
        raise ValueError("scores must contain all five rubric criteria")

    invalid_score = any(
        not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5
        for value in scores.values()
    )
    if invalid_score:
        raise ValueError("each score must be an integer from 1 through 5")

    weights = {item["key"]: item["weight"] for item in RUBRIC_SNAPSHOT["criteria"]}
    weighted_score = round(sum(scores[key] * weights[key] / 5 for key in CRITERION_KEYS), 1)
    critical_gate = "FAIL" if scores["technical_correctness"] < 3 else "PASS"

    if critical_gate == "FAIL":
        overall_decision = "Not ready – critical issue"
    elif weighted_score >= 90:
        overall_decision = "Instructor-ready"
    elif weighted_score >= 80:
        overall_decision = "Strong – minor revision"
    elif weighted_score >= 70:
        overall_decision = "Usable – moderate revision"
    elif weighted_score >= 60:
        overall_decision = "Substantial revision"
    else:
        overall_decision = "Not ready"

    instructor_readiness = "Instructor-ready" if overall_decision == "Instructor-ready" else "Revision required"
    return EvaluationCalculation(
        weighted_score=weighted_score,
        critical_gate=critical_gate,
        overall_decision=overall_decision,
        instructor_readiness=instructor_readiness,
    )
