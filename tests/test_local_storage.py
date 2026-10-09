from pathlib import Path

from storage.local import LocalFileStorage


def test_saves_real_pdf(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    pdf_bytes = Path("tests/fixtures/sample_resume.pdf").read_bytes()

    key = storage.save(
        object_key="resumes/resume-1.pdf",
        content=pdf_bytes,
    )

    assert Path(storage.file_path(key)).read_bytes() == pdf_bytes


def test_deletes_saved_pdf(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)
    key = storage.save(
        object_key="resumes/resume-1.pdf",
        content=b"%PDF-1.7",
    )

    storage.delete(key)

    assert not Path(storage.file_path(key)).exists()
