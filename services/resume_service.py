
from __future__ import annotations

import asyncio
import io
import logging
from uuid import UUID, uuid4
import os

from openai import AsyncOpenAI
from pypdf import PdfReader

from config import OPENAI_API_KEY, MODEL_NAME, TEMPERATURE
from models.resume_extraction import ResumeExtraction, ResumeContentExtraction
from repositories.resume_repository import (
    DuplicateResumeError,
    ResumeDeletionInProgressError,
    ResumeNotFoundError,
    ResumeRepository,
)
from storage.local import LocalFileStorage


logger = logging.getLogger(__name__)


class ResumeService:
    def __init__(
        self,
        storage: LocalFileStorage,
        resume_repository: ResumeRepository,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.storage = storage
        self.resume_repository = resume_repository
        self.llm_client = llm_client

    async def create_resume(
        self,
        *,
        file_name: str,
        content: bytes,
        content_hash: str,
        content_type: str | None = None,
    ) -> ResumeExtraction:
        """Create and extract a resume from an uploaded PDF."""

        operation_id = uuid4()
        resume_id = None
        object_key = None
        saved_object_key = None

        logger.info(
            "Resume creation attempt started operation_id=%s content_size=%d",
            operation_id,
            len(content),
        )

        try:
            if await self.resume_repository.exists_by_content_hash(content_hash):
                raise DuplicateResumeError

            resume_id = uuid4()
            object_key = f"resumes/{resume_id}.pdf"
            saved_object_key = await asyncio.to_thread(
                self.storage.save,
                object_key=object_key,
                content=content,
            )

            pdf_text = await asyncio.to_thread(self.extract_pdf_text, content)
            resume_content_extraction = await self.extract_resume_with_llm(pdf_text)

            file_url = self.storage.file_path(saved_object_key)
            resume_extraction = ResumeExtraction(
                **resume_content_extraction.model_dump(),
                resume_id=resume_id,
                file_url=file_url,
            )
            await self.resume_repository.create(
                resume_id=resume_id,
                content_hash=content_hash,
                file_url=file_url,
                extraction=resume_content_extraction,
            )

            logger.info(
                "Resume creation succeeded operation_id=%s resume_id=%s",
                operation_id,
                resume_id,
            )
            return resume_extraction
        except Exception as error:
            if isinstance(error, DuplicateResumeError):
                logger.warning(
                    "Resume creation rejected as duplicate operation_id=%s",
                    operation_id,
                )
            else:
                logger.exception(
                    "Resume creation failed operation_id=%s resume_id=%s",
                    operation_id,
                    resume_id,
                )
            if saved_object_key is not None:
                await asyncio.to_thread(self.storage.delete, saved_object_key)
            raise

    async def delete_resume(self, resume_id: UUID) -> None:
        logger.info("Resume deletion attempt started resume_id=%s", resume_id)

        try:
            target = await self.resume_repository.claim_for_deletion(resume_id)

            try:
                if target.file_url is not None:
                    await asyncio.to_thread(self.storage.delete, target.file_url)
            except Exception as error:
                await self.resume_repository.mark_deletion_failed(resume_id)
                raise ResumeDeletionFailedError from error

            await self.resume_repository.delete(resume_id)
        except (ResumeNotFoundError, ResumeDeletionInProgressError):
            logger.warning(
                "Resume deletion could not be claimed resume_id=%s",
                resume_id,
            )
            raise
        except Exception:
            logger.exception("Resume deletion failed resume_id=%s", resume_id)
            raise

        logger.info("Resume deletion succeeded resume_id=%s", resume_id)

    @staticmethod
    def extract_pdf_text(pdf_bytes: bytes) -> str:
        pdf_stream = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_stream)
        full_text = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)

        return "\n".join(full_text)




    async def extract_resume_with_llm(
        self,
        resume_text: str,
    ) -> ResumeContentExtraction:
        if self.llm_client is None:
            if not OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            self.llm_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        response = await self.llm_client.responses.parse(
            model=MODEL_NAME,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract resume information from the supplied text. Use null when information is not present and do not "
                        "invent details."
                    ),
                },
                {"role": "user", "content": resume_text},
            ],
            text_format=ResumeContentExtraction,
        )

        if response.output_parsed is None:
            raise RuntimeError("The LLM did not return a resume extraction")

        return response.output_parsed


class ResumeDeletionFailedError(Exception):
    """Raised when the stored resume file cannot be deleted."""
