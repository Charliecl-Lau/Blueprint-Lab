import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assessment import Assessment
from backend.models.run import ControlSet
from backend.schemas.run_schemas import AssessmentDetailResponse
from backend.workers.assessment_worker import run_assessment_pipeline

try:
    from weasyprint import HTML
except OSError:
    HTML = None  # type: ignore[assignment,misc]  # GTK/Pango not installed

router = APIRouter(prefix="/assessments", tags=["assessments"])

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "pdf")
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))


@router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return a


@router.post("/{assessment_id}/regenerate")
def regenerate_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Clear old pipeline records
    if a.prompt_generation:
        db.delete(a.prompt_generation)
    if a.planner_output:
        db.delete(a.planner_output)
    if a.assessment_generation:
        db.delete(a.assessment_generation)
    for q in a.questions:
        for opt in q.options:
            db.delete(opt)
        if q.model_answer:
            db.delete(q.model_answer)
        db.delete(q)
    db.commit()

    a.status = "pending"
    db.commit()

    run_assessment_pipeline.delay(assessment_id)
    return {"assessment_id": assessment_id, "status": "pending"}


@router.post("/{assessment_id}/export-pdf")
def export_pdf(
    assessment_id: int,
    variant: Literal["student", "answer_key"],
    db: Session = Depends(get_db),
):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    run = a.run
    cs = db.get(ControlSet, a.control_set_id)
    control_summary = f"{cs.personality} / {cs.prompt_length} / {cs.action_word_count} words"
    answer_word_guide = {"short": "~100", "medium": "~200", "long": "~350"}.get(cs.result_length, "~200")

    template_name = "student.html" if variant == "student" else "answer_key.html"
    template = _jinja_env.get_template(template_name)

    questions_data = []
    for q in sorted(a.questions, key=lambda x: x.order):
        qd = {
            "type": q.type,
            "body": q.body,
            "options": [{"body": o.body, "is_correct": o.is_correct} for o in q.options],
            "model_answer": q.model_answer,
        }
        questions_data.append(qd)

    html_content = template.render(
        topic=run.topic,
        framework=a.framework.upper(),
        control_summary=control_summary,
        questions=questions_data,
        answer_word_guide=answer_word_guide,
    )

    if HTML is None:
        raise HTTPException(status_code=503, detail="PDF rendering unavailable: GTK/Pango libraries not installed")
    pdf_bytes = HTML(string=html_content).write_pdf()
    filename = f"{run.topic.replace(' ', '-').lower()}-{a.framework}-cs{cs.id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
