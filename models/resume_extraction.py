from __future__ import annotations

from datetime import date, datetime
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def validate_resume_date(
    value: Optional[str],
    *,
    allow_present: bool = False,
) -> Optional[str]:
    if value is None:
        return None

    value = value.strip()
    if allow_present and value.lower() in {"present", "current"}:
        return "Present"

    if re.fullmatch(r"\d{4}", value):
        return value

    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        datetime.strptime(value, "%Y-%m")
        return value

    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-\d{2}", value):
        date.fromisoformat(value)
        return value

    raise ValueError("Date must use YYYY, YYYY-MM, or YYYY-MM-DD format")


class UserInfo(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="The candidate's name exactly as it appears on the resume.",
    )
    email: Optional[str] = Field(
        default=None,
        description="The candidate's email address shown on the resume.",
    )
    phone: Optional[str] = Field(
        default=None,
        description="The candidate's phone number shown on the resume.",
    )
    address: Optional[str] = Field(
        default=None,
        description="The candidate's address or location shown on the resume.",
    )


class Project(BaseModel):
    name: Optional[str] =  Field(
        default=None,
        description="The clean title of a project on the resume. Leave as null if not explicitly stated as a line item.",
    )
    description: Optional[str] =  Field(
        default=None,
        description="The description of what the project the candidate worked on. The responsibilities , ownership , tools and actual work that was done in the project",
    )

class Experience(BaseModel):
    company: Optional[str] = Field(
        default=None,
        description="The clean company name of where the candidate worked. Do not guess if not explicitly stated",
    )
    title: Optional[str] = Field(
        default=None,
        description="The role of the candidate for the experience",
    )
    location: Optional[str] = Field(
        default=None,
        description="The city, state, country where the candidate worked for this experience. Leave as null if not explicitly provided. Some experiences can be done remotely.",
    )
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str]  =  Field(
        default=None,
        description="The description of what the experience entails. The responsibilities , ownership , tools and actual work that was done for the experience",
    )
    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        return validate_resume_date(value)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: Optional[str]) -> Optional[str]:
        return validate_resume_date(value, allow_present=True)


class Education(BaseModel):
    institution: Optional[str] = Field(
        default=None,
        description="The full official name of the school, college, or university."
    )
    degree: Optional[str] = Field(
        default=None,
        description="The type of degree earned (e.g., 'BS', 'BA', 'MS', 'PhD'). Standardize common abbreviations."
    )
    field_of_study: Optional[str] = Field(
        default=None,
        description="The major, minor, or concentration of the degree (e.g., 'Computer Science')."
    )
    start_date: Optional[str] = Field(
        default=None,
        description="The start date of the education. Prefer standard 'YYYY-MM' format if determinable from text."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="The graduation or end date. Use 'Present' or 'Current' if the candidate is still enrolled."
    )
    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: Optional[str]) -> Optional[str]:
        return validate_resume_date(value)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: Optional[str]) -> Optional[str]:
        return validate_resume_date(value, allow_present=True)


class Certification(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="The full title of the certificate or license (e.g., 'AWS Certified Solutions Architect')."
    )
    issuer: Optional[str] = Field(
        default=None,
        description="The organization that granted the certification (e.g., 'Amazon Web Services', 'Coursera')."
    )
    date: Optional[str] = Field(
        default=None,
        description="The date the certification was issued. Prefer standard 'YYYY-MM' format."
    )

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: Optional[str]) -> Optional[str]:
        return validate_resume_date(value)


class ResumeContentExtraction(BaseModel):
    projects: Optional[list[Project]] = None
    skills: Optional[list[str]] = None
    experiences: Optional[list[Experience]] = None
    education: Optional[list[Education]] = None
    certifications: Optional[list[Certification]] = None
    user_info: Optional[UserInfo] = None


class ResumeExtraction(ResumeContentExtraction):
    resume_id: UUID
    file_url: Optional[str] = None
