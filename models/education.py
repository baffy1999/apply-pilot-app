from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Education(Base):
    __tablename__ = "education"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    resume_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    institution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    degree: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    field_of_study: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="education")
