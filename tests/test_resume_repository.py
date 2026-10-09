import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import ResumeStatus, Skill
from models.resume_extraction import (
    Certification as CertificationExtraction,
    Education as EducationExtraction,
    Experience as ExperienceExtraction,
    Project as ProjectExtraction,
    ResumeContentExtraction,
    UserInfo as UserInfoExtraction,
)
from repositories.resume_repository import (
    DuplicateResumeError,
    ResumeDeletionInProgressError,
    ResumeNotFoundError,
    ResumeRepository,
)


def create_session_mock() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def test_exists_by_content_hash_returns_false_when_missing() -> None:
    session = create_session_mock()
    session.scalar.return_value = None
    repository = ResumeRepository(session)

    exists = asyncio.run(repository.exists_by_content_hash("a" * 64))

    assert exists is False
    session.scalar.assert_awaited_once()


def test_exists_by_content_hash_returns_true_when_present() -> None:
    session = create_session_mock()
    session.scalar.return_value = uuid4()
    repository = ResumeRepository(session)

    exists = asyncio.run(repository.exists_by_content_hash("a" * 64))

    assert exists is True
    session.scalar.assert_awaited_once()


def test_duplicate_resume_during_commit_rolls_back_and_raises_duplicate() -> None:
    session = create_session_mock()
    integrity_error = IntegrityError(
        "INSERT INTO resumes",
        {},
        Exception("unique constraint violation"),
    )
    session.commit.side_effect = integrity_error
    session.scalar.return_value = uuid4()
    repository = ResumeRepository(session)

    with pytest.raises(DuplicateResumeError) as raised_error:
        asyncio.run(
            repository.create(
                resume_id=uuid4(),
                content_hash="d" * 64,
                file_url="/tmp/resume.pdf",
                extraction=ResumeContentExtraction(),
            )
        )

    session.rollback.assert_awaited_once_with()
    session.scalar.assert_awaited_once()
    assert raised_error.value.__cause__ is integrity_error


def test_unrelated_integrity_error_rolls_back_and_is_reraised() -> None:
    session = create_session_mock()
    integrity_error = IntegrityError(
        "INSERT INTO resumes",
        {},
        Exception("unrelated constraint violation"),
    )
    session.commit.side_effect = integrity_error
    session.scalar.return_value = None
    repository = ResumeRepository(session)

    with pytest.raises(IntegrityError) as raised_error:
        asyncio.run(
            repository.create(
                resume_id=uuid4(),
                content_hash="e" * 64,
                file_url="/tmp/resume.pdf",
                extraction=ResumeContentExtraction(),
            )
        )

    session.rollback.assert_awaited_once_with()
    session.scalar.assert_awaited_once()
    assert raised_error.value is integrity_error


def test_duplicate_skills_in_extraction_are_attached_once() -> None:
    session = create_session_mock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = [Skill(name="Python")]
    session.scalars.return_value = scalar_result
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="f" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(skills=["Python", "Python"]),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert [skill.name for skill in saved_resume.skills] == ["Python"]
    session.execute.assert_awaited_once()
    session.scalars.assert_awaited_once()


def test_whitespace_skills_are_trimmed_and_blanks_are_ignored() -> None:
    session = create_session_mock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = [Skill(name="Python"), Skill(name="SQL")]
    session.scalars.return_value = scalar_result
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="1" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(skills=[" Python ", "  ", "SQL"]),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert [skill.name for skill in saved_resume.skills] == ["Python", "SQL"]


def test_skills_are_attached_in_extraction_order() -> None:
    session = create_session_mock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = [Skill(name="SQLAlchemy"), Skill(name="Python")]
    session.scalars.return_value = scalar_result
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="2" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(skills=["Python", "SQLAlchemy"]),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert [skill.name for skill in saved_resume.skills] == ["Python", "SQLAlchemy"]


@pytest.mark.parametrize("skills", [None, [], ["", "   "]])
def test_empty_skills_do_not_query_or_insert(skills) -> None:
    session = create_session_mock()
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="3" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(skills=skills),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert saved_resume.skills == []
    session.execute.assert_not_awaited()
    session.scalars.assert_not_awaited()


def test_existing_skill_object_is_reused() -> None:
    session = create_session_mock()
    existing_skill = Skill(name="Python")
    scalar_result = MagicMock()
    scalar_result.all.return_value = [existing_skill]
    session.scalars.return_value = scalar_result
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="4" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(skills=["Python"]),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert saved_resume.skills == [existing_skill]
    assert saved_resume.skills[0] is existing_skill


def test_skill_operation_failure_rolls_back_complete_transaction() -> None:
    session = create_session_mock()
    skill_error = RuntimeError("skill insert failed")
    session.execute.side_effect = skill_error
    repository = ResumeRepository(session)

    with pytest.raises(RuntimeError) as raised_error:
        asyncio.run(
            repository.create(
                resume_id=uuid4(),
                content_hash="5" * 64,
                file_url="/tmp/resume.pdf",
                extraction=ResumeContentExtraction(skills=["Python"]),
            )
        )

    session.rollback.assert_awaited_once_with()
    session.commit.assert_not_awaited()
    assert raised_error.value is skill_error


def test_create_builds_complete_resume_graph_and_commits_once() -> None:
    session = create_session_mock()
    python_skill = Skill(name="Python")
    sqlalchemy_skill = Skill(name="SQLAlchemy")
    scalar_result = MagicMock()
    scalar_result.all.return_value = [python_skill, sqlalchemy_skill]
    session.scalars.return_value = scalar_result
    repository = ResumeRepository(session)
    extraction = ResumeContentExtraction(
        user_info=UserInfoExtraction(name="Ada Lovelace"),
        experiences=[ExperienceExtraction(company="Example Company")],
        projects=[ProjectExtraction(name="Apply Pilot")],
        education=[EducationExtraction(institution="Example University")],
        certifications=[CertificationExtraction(name="Example Certificate")],
        skills=["Python", "Python", " SQLAlchemy "],
    )

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="a" * 64,
            file_url="/tmp/resume.pdf",
            extraction=extraction,
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert saved_resume.user_info.name == "Ada Lovelace"
    assert saved_resume.experiences[0].company == "Example Company"
    assert saved_resume.projects[0].name == "Apply Pilot"
    assert saved_resume.education[0].institution == "Example University"
    assert saved_resume.certifications[0].name == "Example Certificate"
    assert [skill.name for skill in saved_resume.skills] == ["Python", "SQLAlchemy"]
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


def test_create_skips_missing_extraction_sections() -> None:
    session = create_session_mock()
    repository = ResumeRepository(session)

    asyncio.run(
        repository.create(
            resume_id=uuid4(),
            content_hash="b" * 64,
            file_url="/tmp/resume.pdf",
            extraction=ResumeContentExtraction(),
        )
    )

    saved_resume = session.add.call_args.args[0]
    assert saved_resume.user_info is None
    assert saved_resume.experiences == []
    assert saved_resume.projects == []
    assert saved_resume.education == []
    assert saved_resume.certifications == []
    assert saved_resume.skills == []
    session.execute.assert_not_awaited()
    session.scalars.assert_not_awaited()
    session.commit.assert_awaited_once_with()


def test_create_rolls_back_when_commit_fails() -> None:
    session = create_session_mock()
    session.commit.side_effect = RuntimeError("database write failed")
    repository = ResumeRepository(session)

    with pytest.raises(RuntimeError, match="database write failed"):
        asyncio.run(
            repository.create(
                resume_id=uuid4(),
                content_hash="c" * 64,
                file_url="/tmp/resume.pdf",
                extraction=ResumeContentExtraction(),
            )
        )

    session.rollback.assert_awaited_once_with()


def test_claim_for_deletion_commits_and_returns_file_target() -> None:
    session = create_session_mock()
    resume_id = uuid4()
    result = MagicMock()
    result.one_or_none.return_value = SimpleNamespace(
        id=resume_id,
        file_url="/tmp/resume.pdf",
    )
    session.execute.return_value = result
    repository = ResumeRepository(session)

    target = asyncio.run(repository.claim_for_deletion(resume_id))

    assert target.resume_id == resume_id
    assert target.file_url == "/tmp/resume.pdf"
    statement = session.execute.await_args.args[0]
    assert statement.compile().params["status_1"] == [
        ResumeStatus.ACTIVE,
        ResumeStatus.DELETE_FAILED,
    ]
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


def test_claim_for_deletion_rolls_back_when_resume_is_missing() -> None:
    session = create_session_mock()
    update_result = MagicMock()
    update_result.one_or_none.return_value = None
    session.execute.return_value = update_result
    repository = ResumeRepository(session)

    with pytest.raises(ResumeNotFoundError):
        asyncio.run(repository.claim_for_deletion(uuid4()))

    session.execute.assert_awaited_once()
    session.scalar.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


def test_claim_for_deletion_rejects_resume_already_being_deleted() -> None:
    session = create_session_mock()
    update_result = MagicMock()
    update_result.one_or_none.return_value = None
    session.execute.return_value = update_result
    session.scalar.return_value = ResumeStatus.DELETING
    repository = ResumeRepository(session)

    with pytest.raises(ResumeDeletionInProgressError):
        asyncio.run(repository.claim_for_deletion(uuid4()))

    session.execute.assert_awaited_once()
    session.scalar.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


def test_delete_resume_record_commits() -> None:
    session = create_session_mock()
    repository = ResumeRepository(session)

    asyncio.run(repository.delete(uuid4()))

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()
