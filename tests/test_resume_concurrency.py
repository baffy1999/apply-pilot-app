import asyncio
import hashlib
import threading
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import DATABASE_URL
from models import Resume, ResumeStatus
from models.resume_extraction import ResumeContentExtraction, ResumeExtraction
from repositories.resume_repository import (
    DuplicateResumeError,
    ResumeDeletionInProgressError,
    ResumeRepository,
)
from services.resume_service import ResumeDeletionFailedError, ResumeService
from storage.local import LocalFileStorage


def create_pdf_bytes() -> bytes:
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)
    return stream.getvalue()


class TwoPartyBarrier:
    def __init__(self) -> None:
        self.arrivals = 0
        self.lock = asyncio.Lock()
        self.ready = asyncio.Event()

    async def wait(self) -> None:
        async with self.lock:
            self.arrivals += 1
            if self.arrivals == 2:
                self.ready.set()
        await self.ready.wait()


class CoordinatedResumeRepository(ResumeRepository):
    def __init__(
        self,
        session: AsyncSession,
        barrier: TwoPartyBarrier,
    ) -> None:
        super().__init__(session)
        self.barrier = barrier
        self.initial_hash_check_complete = False

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        exists = await super().exists_by_content_hash(content_hash)
        if not self.initial_hash_check_complete:
            self.initial_hash_check_complete = True
            await self.barrier.wait()
        return exists


class StubResumeService(ResumeService):
    async def extract_resume_with_llm(
        self,
        resume_text: str,
    ) -> ResumeContentExtraction:
        return ResumeContentExtraction()


class BlockingStorage(LocalFileStorage):
    def __init__(self, base_directory: Path) -> None:
        super().__init__(base_directory)
        self.delete_started = threading.Event()
        self.allow_delete = threading.Event()

    def delete(self, object_key: str) -> None:
        self.delete_started.set()
        if not self.allow_delete.wait(timeout=5):
            raise TimeoutError("test did not release the blocked deletion")
        super().delete(object_key)


class FailThenBlockStorage(BlockingStorage):
    def __init__(self, base_directory: Path) -> None:
        super().__init__(base_directory)
        self.delete_calls = 0

    def delete(self, object_key: str) -> None:
        self.delete_calls += 1
        if self.delete_calls == 1:
            raise OSError("simulated storage failure")
        super().delete(object_key)


@asynccontextmanager
async def database_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")

    engine = create_async_engine(DATABASE_URL, connect_args={"timeout": 1})
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            async with engine.connect() as connection:
                await connection.execute(select(1))
        except (OSError, SQLAlchemyError) as error:
            pytest.skip(f"PostgreSQL is unavailable: {error}")
        yield session_factory
    finally:
        await engine.dispose()


async def insert_resume(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    file_url: str,
) -> tuple:
    resume_id = uuid4()
    content_hash = hashlib.sha256(str(resume_id).encode()).hexdigest()
    async with session_factory() as session:
        session.add(
            Resume(
                id=resume_id,
                content_hash=content_hash,
                file_url=file_url,
            )
        )
        await session.commit()
    return resume_id, content_hash


async def remove_test_resume(
    session_factory: async_sessionmaker[AsyncSession],
    content_hash: str,
) -> None:
    async with session_factory() as session:
        await session.execute(
            delete(Resume).where(Resume.content_hash == content_hash)
        )
        await session.commit()


def test_concurrent_creation_commits_one_resume_and_rejects_duplicate(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with database_sessions() as session_factory:
            content = create_pdf_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
            barrier = TwoPartyBarrier()

            try:
                async with session_factory() as first_session, session_factory() as second_session:
                    first_service = StubResumeService(
                        storage=LocalFileStorage(tmp_path),
                        resume_repository=CoordinatedResumeRepository(
                            first_session,
                            barrier,
                        ),
                    )
                    second_service = StubResumeService(
                        storage=LocalFileStorage(tmp_path),
                        resume_repository=CoordinatedResumeRepository(
                            second_session,
                            barrier,
                        ),
                    )

                    results = await asyncio.gather(
                        first_service.create_resume(
                            file_name="resume.pdf",
                            content=content,
                            content_hash=content_hash,
                            content_type="application/pdf",
                        ),
                        second_service.create_resume(
                            file_name="resume.pdf",
                            content=content,
                            content_hash=content_hash,
                            content_type="application/pdf",
                        ),
                        return_exceptions=True,
                    )

                assert (
                    sum(isinstance(result, ResumeExtraction) for result in results) == 1
                ), repr(results)
                assert (
                    sum(isinstance(result, DuplicateResumeError) for result in results)
                    == 1
                ), repr(results)

                async with session_factory() as verification_session:
                    resumes = list(
                        (
                            await verification_session.scalars(
                                select(Resume).where(
                                    Resume.content_hash == content_hash
                                )
                            )
                        ).all()
                    )
                assert len(resumes) == 1
                assert len(list(tmp_path.rglob("*.pdf"))) == 1
            finally:
                await remove_test_resume(session_factory, content_hash)

    asyncio.run(scenario())


def test_first_deletion_claim_wins_while_second_request_is_rejected(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with database_sessions() as session_factory:
            storage = BlockingStorage(tmp_path)
            object_key = storage.save(
                object_key=f"resumes/{uuid4()}.pdf",
                content=b"resume",
            )
            resume_id, content_hash = await insert_resume(
                session_factory,
                file_url=storage.file_path(object_key),
            )

            try:
                async with session_factory() as first_session, session_factory() as second_session:
                    first_service = ResumeService(
                        storage=storage,
                        resume_repository=ResumeRepository(first_session),
                    )
                    second_service = ResumeService(
                        storage=storage,
                        resume_repository=ResumeRepository(second_session),
                    )

                    first_request = asyncio.create_task(
                        first_service.delete_resume(resume_id)
                    )
                    started = await asyncio.to_thread(
                        storage.delete_started.wait,
                        5,
                    )
                    assert started is True

                    with pytest.raises(ResumeDeletionInProgressError):
                        await second_service.delete_resume(resume_id)

                    storage.allow_delete.set()
                    await first_request

                async with session_factory() as verification_session:
                    stored_resume = await verification_session.get(Resume, resume_id)
                assert stored_resume is None
                assert not Path(storage.file_path(object_key)).exists()
            finally:
                storage.allow_delete.set()
                await remove_test_resume(session_factory, content_hash)

    asyncio.run(scenario())


def test_failed_deletion_can_be_claimed_and_retried(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with database_sessions() as session_factory:
            storage = FailThenBlockStorage(tmp_path)
            object_key = storage.save(
                object_key=f"resumes/{uuid4()}.pdf",
                content=b"resume",
            )
            resume_id, content_hash = await insert_resume(
                session_factory,
                file_url=storage.file_path(object_key),
            )

            try:
                async with session_factory() as first_session:
                    first_service = ResumeService(
                        storage=storage,
                        resume_repository=ResumeRepository(first_session),
                    )
                    with pytest.raises(ResumeDeletionFailedError):
                        await first_service.delete_resume(resume_id)

                async with session_factory() as verification_session:
                    failed_resume = await verification_session.get(Resume, resume_id)
                    assert failed_resume is not None
                    assert failed_resume.status == ResumeStatus.DELETE_FAILED
                    assert failed_resume.deletion_attempts == 1

                async with session_factory() as second_session:
                    second_service = ResumeService(
                        storage=storage,
                        resume_repository=ResumeRepository(second_session),
                    )
                    retry = asyncio.create_task(
                        second_service.delete_resume(resume_id)
                    )
                    started = await asyncio.to_thread(
                        storage.delete_started.wait,
                        5,
                    )
                    assert started is True

                    async with session_factory() as verification_session:
                        claimed_resume = await verification_session.get(
                            Resume,
                            resume_id,
                        )
                        assert claimed_resume is not None
                        assert claimed_resume.status == ResumeStatus.DELETING
                        assert claimed_resume.deletion_attempts == 2

                    storage.allow_delete.set()
                    await retry

                async with session_factory() as verification_session:
                    stored_resume = await verification_session.get(Resume, resume_id)
                assert stored_resume is None
                assert storage.delete_calls == 2
            finally:
                storage.allow_delete.set()
                await remove_test_resume(session_factory, content_hash)

    asyncio.run(scenario())


def test_deletion_is_idempotent_when_file_is_already_missing(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with database_sessions() as session_factory:
            storage = LocalFileStorage(tmp_path)
            missing_file = storage.file_path(f"resumes/{uuid4()}.pdf")
            resume_id, content_hash = await insert_resume(
                session_factory,
                file_url=missing_file,
            )

            try:
                async with session_factory() as session:
                    service = ResumeService(
                        storage=storage,
                        resume_repository=ResumeRepository(session),
                    )
                    await service.delete_resume(resume_id)

                async with session_factory() as verification_session:
                    stored_resume = await verification_session.get(Resume, resume_id)
                assert stored_resume is None
            finally:
                await remove_test_resume(session_factory, content_hash)

    asyncio.run(scenario())
