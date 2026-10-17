"""Resume format detection, extraction limits, and LLM output contracts."""

from __future__ import annotations

import io

import pytest
from app.config import Settings
from app.errors import AppError
from app.resume_contracts import ResumeAnalysisOutput, ResumeQuestionsOutput
from app.resume_processing import DOCX, PDF, extract_resume, validate_file_identity
from docx import Document
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_pdf(*page_texts: str) -> bytes:
    """Build a minimal text PDF using pypdf's documented writer path."""

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            font = writer._add_object(
                DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Font"),
                        NameObject("/Subtype"): NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    }
                )
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
                }
            )
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_docx(text: str) -> bytes:
    """Build a real DOCX package with one paragraph."""

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def analysis_payload(*, evidence_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "analysis_version": "1.0.0",
        "skills": [
            {
                "name": "Python",
                "level": "advanced",
                "evidence_ids": evidence_ids,
            }
        ],
        "projects": [],
        "evidence": [
            {
                "id": evidence_id,
                "summary": f"证据 {evidence_id}",
                "capability_tags": ["backend"],
            }
            for evidence_id in evidence_ids
        ],
        "unverified_items": [],
        "gaps": [],
    }


def questions_payload(*, evidence_id: str) -> dict[str, object]:
    difficulties = ["easy"] * 3 + ["medium"] * 5 + ["hard"] * 2
    return {
        "questions": [
            {
                "sequence": index + 1,
                "question_text": f"问题 {index + 1}",
                "category": "backend",
                "difficulty": difficulty,
                "topic_key": f"topic-{index + 1}",
                "assessment_points": ["考察点"],
                "reference_answer": "参考答案",
                "scoring_rubric": ["评分点"],
                "evidence_ids": [evidence_id],
            }
            for index, difficulty in enumerate(difficulties)
        ]
    }


def test_document_detection_accepts_real_pdf_and_docx(settings: Settings) -> None:
    pdf = make_pdf("Python backend engineer")
    assert (
        validate_file_identity(
            filename="resume.pdf",
            declared_mime=PDF,
            content=pdf,
            settings=settings,
        )
        == PDF
    )
    extracted_pdf = extract_resume(pdf, detected_mime=PDF, settings=settings)
    assert "Python backend engineer" in extracted_pdf.text

    docx_content = make_docx("Python backend engineer")
    assert (
        validate_file_identity(
            filename="resume.docx",
            declared_mime=DOCX,
            content=docx_content,
            settings=settings,
        )
        == DOCX
    )
    extracted = extract_resume(docx_content, detected_mime=DOCX, settings=settings)
    assert extracted.text == "Python backend engineer"
    assert extracted.page_count == 1


def test_extraction_rejects_empty_and_scan_like_pdf(settings: Settings) -> None:
    with pytest.raises(AppError) as empty:
        extract_resume(make_pdf(""), detected_mime=PDF, settings=settings)
    assert empty.value.code == "text_extraction_unsupported"


def test_extraction_rejects_page_and_size_limits(settings: Settings) -> None:
    too_many_pages = make_pdf(*["page"] * 11)
    with pytest.raises(AppError) as pages:
        extract_resume(too_many_pages, detected_mime=PDF, settings=settings)
    assert pages.value.code == "page_limit_exceeded"

    limited = settings.model_copy(update={"resume_max_bytes": 20, "resume_max_docx_characters": 10})
    with pytest.raises(AppError) as size:
        validate_file_identity(
            filename="resume.pdf",
            declared_mime=PDF,
            content=make_pdf("page"),
            settings=limited,
        )
    assert size.value.code == "file_too_large"

    with pytest.raises(AppError) as docx_pages:
        extract_resume(
            make_docx("x" * 111),
            detected_mime=DOCX,
            settings=limited,
        )
    assert docx_pages.value.code == "page_limit_exceeded"


def test_analysis_contract_rejects_dangling_evidence_links() -> None:
    payload = analysis_payload(evidence_ids=["evidence-1"])
    payload["skills"] = [
        {
            "name": "Python",
            "level": "advanced",
            "evidence_ids": ["missing"],
        }
    ]
    with pytest.raises(ValidationError):
        ResumeAnalysisOutput.model_validate(payload)


def test_question_contract_enforces_ten_question_distribution() -> None:
    valid = questions_payload(evidence_id="evidence-1")
    assert len(ResumeQuestionsOutput.model_validate(valid).questions) == 10

    invalid = questions_payload(evidence_id="evidence-1")
    invalid["questions"] = invalid["questions"][:-1]  # type: ignore[index]
    with pytest.raises(ValidationError):
        ResumeQuestionsOutput.model_validate(invalid)
