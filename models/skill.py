from __future__ import annotations

from typing import List
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, Index, String, Table
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


resume_skills = Table(
    "resume_skills",
    Base.metadata,
    Column(
        "resume_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "skill_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_resume_skills_skill_id", "skill_id"),
)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    resumes: Mapped[List["Resume"]] = relationship(
        secondary=resume_skills,
        back_populates="skills",
    )
