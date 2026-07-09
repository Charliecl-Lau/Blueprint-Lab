from collections import Counter
from dataclasses import dataclass, field
from backend.schemas.planner_schema import PlannerResponse


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


def validate_plan(plan: PlannerResponse, mcq_count: int, long_answer_count: int) -> ValidationResult:
    errors = []
    questions = plan.assessment_plan.questions

    actual_mcq = sum(1 for q in questions if q.type == "mcq")
    actual_la = sum(1 for q in questions if q.type == "long_answer")

    if actual_mcq != mcq_count:
        errors.append(f"MCQ count mismatch: expected {mcq_count}, got {actual_mcq}")

    if actual_la != long_answer_count:
        errors.append(f"Long answer count mismatch: expected {long_answer_count}, got {actual_la}")

    topics = [q.topic.strip().lower() for q in questions]
    topic_counts = Counter(topics)
    repeated = [t for t, count in topic_counts.items() if count > 1]
    if repeated:
        errors.append(f"Repeated question topics: {repeated}")

    total = len(questions)
    if total > 0:
        bloom_counts = Counter(q.bloom_level.strip().lower() for q in questions)
        for level, count in bloom_counts.items():
            if count / total > 0.60:
                errors.append(
                    f"Bloom level '{level}' appears in {count}/{total} questions ({count/total:.0%}), exceeds 60% limit"
                )

    empty_scope = [i + 1 for i, q in enumerate(questions) if not q.answer_scope.strip()]
    if empty_scope:
        errors.append(f"Empty answer_scope on question(s): {empty_scope}")

    return ValidationResult(passed=len(errors) == 0, errors=errors)
