from sqlalchemy.orm import configure_mappers

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
from models.skill import resume_skills


def test_resume_and_experience_relationships_are_configured() -> None:
    configure_mappers()

    assert Resume.experiences.property.mapper.class_ is Experience
    assert Experience.resume.property.mapper.class_ is Resume


def test_resume_content_hash_is_required_and_unique() -> None:
    content_hash_column = Resume.__table__.c.content_hash

    assert content_hash_column.nullable is False
    assert content_hash_column.unique is True
    assert content_hash_column.type.length == 64


def test_resume_deletion_state_columns_are_configured() -> None:
    status_column = Resume.__table__.c.status
    deletion_attempts_column = Resume.__table__.c.deletion_attempts
    last_attempt_column = Resume.__table__.c.last_deletion_attempt_at

    assert status_column.nullable is False
    assert set(status_column.type.enums) == {
        ResumeStatus.ACTIVE.value,
        ResumeStatus.DELETING.value,
        ResumeStatus.DELETE_FAILED.value,
    }
    assert str(status_column.server_default.arg) == ResumeStatus.ACTIVE.value
    assert deletion_attempts_column.nullable is False
    assert str(deletion_attempts_column.server_default.arg) == "0"
    assert last_attempt_column.nullable is True


def test_experience_references_resume_with_cascade_delete() -> None:
    resume_id_foreign_key = next(iter(Experience.__table__.c.resume_id.foreign_keys))

    assert resume_id_foreign_key.target_fullname == "resumes.id"
    assert resume_id_foreign_key.ondelete == "CASCADE"


def test_resume_and_project_relationships_are_configured() -> None:
    configure_mappers()

    assert Resume.projects.property.mapper.class_ is Project
    assert Project.resume.property.mapper.class_ is Resume


def test_project_references_resume_with_cascade_delete() -> None:
    resume_id_foreign_key = next(iter(Project.__table__.c.resume_id.foreign_keys))

    assert resume_id_foreign_key.target_fullname == "resumes.id"
    assert resume_id_foreign_key.ondelete == "CASCADE"


def test_resume_and_education_relationships_are_configured() -> None:
    configure_mappers()

    assert Resume.education.property.mapper.class_ is Education
    assert Education.resume.property.mapper.class_ is Resume


def test_education_references_resume_with_cascade_delete() -> None:
    resume_id_foreign_key = next(iter(Education.__table__.c.resume_id.foreign_keys))

    assert resume_id_foreign_key.target_fullname == "resumes.id"
    assert resume_id_foreign_key.ondelete == "CASCADE"


def test_resume_and_certification_relationships_are_configured() -> None:
    configure_mappers()

    assert Resume.certifications.property.mapper.class_ is Certification
    assert Certification.resume.property.mapper.class_ is Resume


def test_certification_references_resume_with_cascade_delete() -> None:
    resume_id_foreign_key = next(
        iter(Certification.__table__.c.resume_id.foreign_keys)
    )

    assert resume_id_foreign_key.target_fullname == "resumes.id"
    assert resume_id_foreign_key.ondelete == "CASCADE"


def test_resume_and_skill_relationships_are_many_to_many() -> None:
    configure_mappers()

    assert Resume.skills.property.mapper.class_ is Skill
    assert Skill.resumes.property.mapper.class_ is Resume
    assert Resume.skills.property.secondary is resume_skills


def test_skill_name_is_required_and_unique() -> None:
    name_column = Skill.__table__.c.name

    assert name_column.nullable is False
    assert name_column.unique is True


def test_resume_skills_has_composite_key_and_cascade_foreign_keys() -> None:
    assert set(resume_skills.primary_key.columns.keys()) == {"resume_id", "skill_id"}

    foreign_keys = {
        foreign_key.parent.name: foreign_key
        for foreign_key in resume_skills.foreign_keys
    }
    assert foreign_keys["resume_id"].target_fullname == "resumes.id"
    assert foreign_keys["resume_id"].ondelete == "CASCADE"
    assert foreign_keys["skill_id"].target_fullname == "skills.id"
    assert foreign_keys["skill_id"].ondelete == "CASCADE"


def test_resume_and_user_info_have_a_one_to_one_relationship() -> None:
    configure_mappers()

    assert Resume.user_info.property.mapper.class_ is UserInfo
    assert Resume.user_info.property.uselist is False
    assert UserInfo.resume.property.mapper.class_ is Resume


def test_user_info_uniquely_references_resume_with_cascade_delete() -> None:
    resume_id_column = UserInfo.__table__.c.resume_id
    resume_id_foreign_key = next(iter(resume_id_column.foreign_keys))

    assert resume_id_column.unique is True
    assert resume_id_foreign_key.target_fullname == "resumes.id"
    assert resume_id_foreign_key.ondelete == "CASCADE"
