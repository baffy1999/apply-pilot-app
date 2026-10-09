import os
import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_database_session
from models.resume_extraction import ResumeExtraction
from repositories.resume_repository import (
    DuplicateResumeError,
    ResumeNotFoundError,
    ResumeRepository,
)
from services.resume_service import ResumeDeletionFailedError, ResumeService
from storage.local import LocalFileStorage


router = APIRouter(prefix="/resumes", tags=["resumes"])


def get_resume_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ResumeService:
    upload_directory = os.getenv("UPLOAD_DIRECTORY", "uploads")
    storage = LocalFileStorage(base_directory=upload_directory)
    resume_repository = ResumeRepository(session=session)
    return ResumeService(
        storage=storage,
        resume_repository=resume_repository,
    )

@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: Annotated[UploadFile, File(description="Resume PDF")],
    resume_service: Annotated[ResumeService, Depends(get_resume_service)],
) -> ResumeExtraction:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required",
        )
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF files are allowed."
        )
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    try:
        return await resume_service.create_resume(
            file_name=file.filename,
            content=content,
            content_hash=file_hash,
            content_type=file.content_type,
        )
    except DuplicateResumeError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This resume has already been uploaded.",
        ) from error


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: UUID,
    resume_service: Annotated[ResumeService, Depends(get_resume_service)],
) -> Response:
    try:
        await resume_service.delete_resume(resume_id)
    except ResumeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found.",
        ) from error
    except ResumeDeletionFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The resume file could not be deleted.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
