from io import BytesIO
import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pytest import MonkeyPatch

from app import app
from models.resume_extraction import ResumeContentExtraction
from repositories.resume_repository import (
    DuplicateResumeError,
    ResumeNotFoundError,
    ResumeRepository,
)
from services.resume_service import ResumeDeletionFailedError, ResumeService


def create_pdf_bytes() -> bytes:
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)
    return stream.getvalue()


def test_upload_resume_integration(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="services.resume_service")
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(tmp_path))

    async def fake_llm_extraction(
        self: ResumeService,
        resume_text: str,
    ) -> ResumeContentExtraction:
        return ResumeContentExtraction(skills=["Python"])

    monkeypatch.setattr(
        ResumeService,
        "extract_resume_with_llm",
        fake_llm_extraction,
    )

    async def fake_resume_exists(
        self: ResumeRepository,
        content_hash: str,
    ) -> bool:
        return False

    monkeypatch.setattr(
        ResumeRepository,
        "exists_by_content_hash",
        fake_resume_exists,
    )
    saved_resume: dict[str, object] = {}

    async def fake_create_resume_record(
        self: ResumeRepository,
        *,
        resume_id,
        content_hash: str,
        file_url: str,
        extraction: ResumeContentExtraction,
    ) -> None:
        saved_resume.update(
            resume_id=resume_id,
            content_hash=content_hash,
            file_url=file_url,
            extraction=extraction,
        )

    monkeypatch.setattr(
        ResumeRepository,
        "create",
        fake_create_resume_record,
    )
    pdf_bytes = create_pdf_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/resumes",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 201
    saved_path = Path(response.json()["file_url"])
    assert saved_path.is_relative_to(tmp_path)
    assert saved_path.read_bytes() == pdf_bytes
    assert response.json()["skills"] == ["Python"]
    assert str(saved_resume["resume_id"]) == response.json()["resume_id"]
    assert saved_resume["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert saved_resume["file_url"] == response.json()["file_url"]
    assert saved_resume["extraction"].skills == ["Python"]
    assert any("Resume creation attempt started" in message for message in caplog.messages)
    assert any("Resume creation succeeded" in message for message in caplog.messages)


def test_rejects_resume_already_committed_to_database(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(tmp_path))

    async def fake_resume_exists(
        self: ResumeRepository,
        content_hash: str,
    ) -> bool:
        return True

    monkeypatch.setattr(
        ResumeRepository,
        "exists_by_content_hash",
        fake_resume_exists,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resumes",
            files={"file": ("resume.pdf", create_pdf_bytes(), "application/pdf")},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "This resume has already been uploaded."}
    assert list(tmp_path.rglob("*.pdf")) == []


def test_removes_new_file_when_concurrent_upload_wins(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(tmp_path))

    async def fake_resume_does_not_exist(
        self: ResumeRepository,
        content_hash: str,
    ) -> bool:
        return False

    async def fake_llm_extraction(
        self: ResumeService,
        resume_text: str,
    ) -> ResumeContentExtraction:
        return ResumeContentExtraction()

    async def fake_duplicate_on_create(
        self: ResumeRepository,
        *,
        resume_id,
        content_hash: str,
        file_url: str,
        extraction: ResumeContentExtraction,
    ) -> None:
        raise DuplicateResumeError

    monkeypatch.setattr(
        ResumeRepository,
        "exists_by_content_hash",
        fake_resume_does_not_exist,
    )
    monkeypatch.setattr(
        ResumeService,
        "extract_resume_with_llm",
        fake_llm_extraction,
    )
    monkeypatch.setattr(
        ResumeRepository,
        "create",
        fake_duplicate_on_create,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resumes",
            files={"file": ("resume.pdf", create_pdf_bytes(), "application/pdf")},
        )

    assert response.status_code == 409
    assert list(tmp_path.rglob("*.pdf")) == []


def test_delete_resume_returns_no_content(monkeypatch: MonkeyPatch) -> None:
    resume_id = uuid4()

    async def fake_delete_resume(
        self: ResumeService,
        requested_resume_id,
    ) -> None:
        assert requested_resume_id == resume_id

    monkeypatch.setattr(ResumeService, "delete_resume", fake_delete_resume)

    with TestClient(app) as client:
        response = client.delete(f"/resumes/{resume_id}")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_resume_returns_not_found(monkeypatch: MonkeyPatch) -> None:
    async def fake_delete_resume(
        self: ResumeService,
        requested_resume_id,
    ) -> None:
        raise ResumeNotFoundError

    monkeypatch.setattr(ResumeService, "delete_resume", fake_delete_resume)

    with TestClient(app) as client:
        response = client.delete(f"/resumes/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Resume not found."}


def test_delete_resume_returns_service_unavailable_when_file_delete_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    async def fake_delete_resume(
        self: ResumeService,
        requested_resume_id,
    ) -> None:
        raise ResumeDeletionFailedError

    monkeypatch.setattr(ResumeService, "delete_resume", fake_delete_resume)

    with TestClient(app) as client:
        response = client.delete(f"/resumes/{uuid4()}")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The resume file could not be deleted."
    }
