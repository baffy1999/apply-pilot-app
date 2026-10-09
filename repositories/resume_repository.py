from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from uuid import uuid4

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Certification,
    Education,
    Experience,
    Project,
    Resume,
    ResumeStatus,
    Skill,
    UserInfo,
)
from models.resume_extraction import ResumeContentExtraction


class DuplicateResumeError(Exception):
    """Raised when a resume with the same content hash already exists."""


class ResumeNotFoundError(Exception):
    """Raised when a resume cannot be found."""


class ResumeDeletionInProgressError(Exception):
    """Raised when another request has already claimed the resume deletion."""


@dataclass(frozen=True)
class ResumeDeletionTarget:
    resume_id: UUID
    file_url: Optional[str]


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        resume_id = await self.session.scalar(
            select(Resume.id).where(Resume.content_hash == content_hash).limit(1)
        )
        return resume_id is not None

    async def claim_for_deletion(self, resume_id: UUID) -> ResumeDeletionTarget:
        try:
            result = await self.session.execute(
                update(Resume)
                .where(
                    Resume.id == resume_id,
                    Resume.status.in_(
                        [
                            ResumeStatus.ACTIVE,
                            ResumeStatus.DELETE_FAILED,
                        ]
                    ),
                )
                .values(
                    status=ResumeStatus.DELETING,
                    deletion_attempts=Resume.deletion_attempts + 1,
                    last_deletion_attempt_at=datetime.now(timezone.utc),
                )
                .returning(Resume.id, Resume.file_url)
            )
            row = result.one_or_none()

            if row is None:
                current_status = await self.session.scalar(
                    select(Resume.status).where(Resume.id == resume_id)
                )
                if current_status == ResumeStatus.DELETING:
                    raise ResumeDeletionInProgressError
                raise ResumeNotFoundError

            await self.session.commit()
            return ResumeDeletionTarget(
                resume_id=row.id,
                file_url=row.file_url,
            )
        except Exception:
            await self.session.rollback()
            raise

    async def mark_deletion_failed(self, resume_id: UUID) -> None:
        try:
            await self.session.execute(
                update(Resume)
                .where(Resume.id == resume_id)
                .values(status=ResumeStatus.DELETE_FAILED)
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def delete(self, resume_id: UUID) -> None:
        try:
            await self.session.execute(
                sql_delete(Resume).where(Resume.id == resume_id)
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def create(
        self,
        *,
        resume_id: UUID,
        content_hash: str,
        file_url: str,
        extraction: ResumeContentExtraction,
    ) -> None:
        try:
            resume = Resume(
                id=resume_id,
                content_hash=content_hash,
                file_url=file_url,
            )

            if extraction.user_info is not None:
                resume.user_info = UserInfo(**extraction.user_info.model_dump())

            if extraction.experiences:
                resume.experiences = [
                    Experience(**experience.model_dump())
                    for experience in extraction.experiences
                ]

            if extraction.projects:
                resume.projects = [
                    Project(**project.model_dump())
                    for project in extraction.projects
                ]

            if extraction.education:
                resume.education = [
                    Education(**education.model_dump())
                    for education in extraction.education
                ]

            if extraction.certifications:
                resume.certifications = [
                    Certification(**certification.model_dump())
                    for certification in extraction.certifications
                ]

            if extraction.skills:
                resume.skills = await self._get_or_create_skills(extraction.skills)

            self.session.add(resume)
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            if await self.exists_by_content_hash(content_hash):
                raise DuplicateResumeError from error
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def _get_or_create_skills(self, skill_names: list[str]) -> list[Skill]:
        unique_names = list(
            dict.fromkeys(name.strip() for name in skill_names if name.strip())
        )
        if not unique_names:
            return []

        await self.session.execute(
            insert(Skill)
            .values(
                [
                    {"id": uuid4(), "name": name}
                    for name in unique_names
                ]
            )
            .on_conflict_do_nothing(index_elements=[Skill.name])
        )
        skills = list(
            (
                await self.session.scalars(
                    select(Skill).where(Skill.name.in_(unique_names))
                )
            ).all()
        )
        skills_by_name = {skill.name: skill for skill in skills}
        return [skills_by_name[name] for name in unique_names]
