import pytest
from pydantic import ValidationError

from models.resume_extraction import Certification, Education, Experience, Project


def test_accepts_supported_resume_dates() -> None:
    experience = Experience(start_date="2022-06", end_date="current")
    education = Education(start_date="2018", end_date="2022-05-30")

    assert experience.end_date == "Present"
    assert education.end_date == "2022-05-30"


@pytest.mark.parametrize("invalid_date", ["June 2022", "2022-13", "2023-02-30"])
def test_rejects_invalid_certification_dates(invalid_date: str) -> None:
    with pytest.raises(ValidationError):
        Certification(date=invalid_date)


def test_rejects_present_as_a_start_date() -> None:
    with pytest.raises(ValidationError):
        Experience(start_date="Present")


def test_project_name_defaults_to_none() -> None:
    assert Project().name is None
