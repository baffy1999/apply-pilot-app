from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SQLAlchemyEnum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ResumeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DELETING = "DELETING"
    DELETE_FAILED = "DELETE_FAILED"


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ResumeStatus] = mapped_column(
        SQLAlchemyEnum(
            ResumeStatus,
            name="resume_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default=ResumeStatus.ACTIVE,
        server_default=ResumeStatus.ACTIVE.value,
    )
    deletion_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_deletion_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    experiences: Mapped[List["Experience"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )
    projects: Mapped[List["Project"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )
    education: Mapped[List["Education"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )
    certifications: Mapped[List["Certification"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )
    skills: Mapped[List["Skill"]] = relationship(
        secondary="resume_skills",
        back_populates="resumes",
    )
    user_info: Mapped[Optional["UserInfo"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
