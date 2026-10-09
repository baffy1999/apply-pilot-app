import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from repositories.resume_repository import ResumeDeletionTarget
from services.resume_service import ResumeDeletionFailedError, ResumeService
from storage.local import LocalFileStorage


def test_delete_resume_removes_file_then_database_record(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="services.resume_service")
    resume_id = uuid4()
    storage = LocalFileStorage(tmp_path)
    object_key = storage.save(
        object_key=f"resumes/{resume_id}.pdf",
        content=b"resume",
    )
    file_url = storage.file_path(object_key)
    repository = MagicMock()
    repository.claim_for_deletion = AsyncMock(
        return_value=ResumeDeletionTarget(resume_id=resume_id, file_url=file_url)
    )
    repository.mark_deletion_failed = AsyncMock()
    repository.delete = AsyncMock()
    service = ResumeService(storage=storage, resume_repository=repository)

    asyncio.run(service.delete_resume(resume_id))

    assert not Path(file_url).exists()
    repository.claim_for_deletion.assert_awaited_once_with(resume_id)
    repository.delete.assert_awaited_once_with(resume_id)
    repository.mark_deletion_failed.assert_not_awaited()
    assert any("Resume deletion attempt started" in message for message in caplog.messages)
    assert any("Resume deletion succeeded" in message for message in caplog.messages)


def test_delete_resume_marks_record_failed_when_file_delete_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="services.resume_service")
    resume_id = uuid4()
    storage = MagicMock(spec=LocalFileStorage)
    storage.delete.side_effect = OSError("disk unavailable")
    repository = MagicMock()
    repository.claim_for_deletion = AsyncMock(
        return_value=ResumeDeletionTarget(
            resume_id=resume_id,
            file_url=str(tmp_path / "resume.pdf"),
        )
    )
    repository.mark_deletion_failed = AsyncMock()
    repository.delete = AsyncMock()
    service = ResumeService(storage=storage, resume_repository=repository)

    with pytest.raises(ResumeDeletionFailedError):
        asyncio.run(service.delete_resume(resume_id))

    repository.mark_deletion_failed.assert_awaited_once_with(resume_id)
    repository.delete.assert_not_awaited()
    assert any("Resume deletion attempt started" in message for message in caplog.messages)
    assert any("Resume deletion failed" in message for message in caplog.messages)


def test_create_resume_logs_unexpected_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="services.resume_service")
    repository = MagicMock()
    repository.exists_by_content_hash = AsyncMock(return_value=False)
    repository.create = AsyncMock()
    service = ResumeService(
        storage=LocalFileStorage(tmp_path),
        resume_repository=repository,
    )

    with pytest.raises(Exception):
        asyncio.run(
            service.create_resume(
                file_name="resume.pdf",
                content=b"not a PDF",
                content_hash="a" * 64,
                content_type="application/pdf",
            )
        )

    assert any("Resume creation attempt started" in message for message in caplog.messages)
    assert any("Resume creation failed" in message for message in caplog.messages)
