# Apply Pilot

Apply Pilot is a learning project for building a resume-processing API with FastAPI, PostgreSQL, SQLAlchemy, Alembic, local file storage, and OpenAI structured extraction.

The API currently accepts PDF resumes, extracts structured resume data, stores the file locally, and persists the complete extraction in normalized PostgreSQL tables. It also supports coordinated resume deletion.

## Current features

- Upload PDF resumes through `POST /resumes`.
- Extract PDF text with `pypdf`.
- Convert resume text into validated Pydantic models using OpenAI structured output.
- Store resumes and extracted sections in PostgreSQL using async SQLAlchemy.
- Persist user information, experience, projects, education, certifications, and skills.
- Prevent duplicate resumes with a unique SHA-256 content hash.
- Save uploaded PDFs beneath `uploads/resumes/`.
- Delete a resume through `DELETE /resumes/{resume_id}`.
- Cascade database deletion to resume-owned child records.
- Coordinate concurrent deletion attempts with `ACTIVE`, `DELETING`, and `DELETE_FAILED` states.
- Manage database schema changes with Alembic migrations.

## Resume creation flow

```text
POST /resumes
    -> validate the filename and declared PDF content type
    -> calculate a SHA-256 content hash
    -> check PostgreSQL for an existing hash
    -> save the PDF under uploads/resumes/<uuid>.pdf
    -> extract text with pypdf
    -> extract structured data with OpenAI
    -> save the resume and all extracted sections in one database transaction
    -> return the extraction, resume ID, and local file path
```

The unique database constraint on `resumes.content_hash` handles concurrent uploads that pass the initial duplicate check at the same time. If extraction or database persistence fails after the PDF is saved, the service removes the newly saved file.

## Resume deletion flow

```text
DELETE /resumes/{resume_id}
    -> atomically claim an ACTIVE or DELETE_FAILED resume
    -> set its status to DELETING
    -> increment deletion_attempts and record the attempt time
    -> delete the local PDF
    -> delete the resume row
    -> let PostgreSQL cascade deletion to related resume data
    -> return 204 No Content
```

If local file deletion fails, the resume is marked `DELETE_FAILED` so a later request can claim it again. A missing local file counts as already deleted and does not prevent database cleanup. A resume already marked `DELETING` cannot be claimed by a second request.

## Database model

The normalized schema currently contains:

- `resumes`
- `user_info`
- `experiences`
- `projects`
- `education`
- `certifications`
- `skills`
- `resume_skills`

Resume-owned tables reference `resumes.id` with `ON DELETE CASCADE`. Skills are shared through the `resume_skills` join table.

## Run locally

Python 3.9 or newer and Docker are required.

Create the Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Add your OpenAI API key to `.env`:

```text
OPENAI_API_KEY=your-key
```

Start PostgreSQL and apply all migrations:

```bash
docker compose up -d postgres
alembic upgrade head
```

Start the API:

```bash
uvicorn app:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## API examples

Upload a resume:

```bash
curl -X POST \
  -F "file=@/path/to/resume.pdf;type=application/pdf" \
  http://127.0.0.1:8000/resumes
```

Delete a resume:

```bash
curl -i -X DELETE \
  http://127.0.0.1:8000/resumes/RESUME_ID
```

## Tests

Run the complete suite with PostgreSQL running:

```bash
pytest
```

The suite covers model validation, local storage, API behavior, repository transactions, duplicate handling, complete extraction persistence, deletion state changes, retries, idempotent file deletion, and real PostgreSQL concurrency behavior. OpenAI calls are replaced during tests, so the suite does not spend API credits.

## Project layout

- `app.py`: creates the FastAPI application and registers routers.
- `api/resumes.py`: defines the resume upload and deletion endpoints.
- `services/resume_service.py`: coordinates storage, extraction, persistence, deletion, and operation logging.
- `repositories/resume_repository.py`: owns resume database operations and transaction boundaries.
- `models/`: contains SQLAlchemy database models and Pydantic extraction models.
- `storage/local.py`: implements local PDF storage.
- `migrations/`: contains Alembic configuration and schema revisions.
- `database.py`: configures the async SQLAlchemy engine and request-scoped sessions.
- `compose.yaml`: runs the local PostgreSQL database.
- `tests/`: contains unit, API integration, repository, and PostgreSQL concurrency tests.
- `NOTES.md`: records deletion design decisions and planned behavior.
- `instructions.md`: contains collaboration rules for the AI coding assistant; the running application does not load it.

## Current limitations

- Uploaded PDFs are stored on the local machine and are not exposed through a download endpoint.
- The upload endpoint trusts the declared MIME type and does not inspect the file signature.
- Upload-size limits are not implemented.
- Authentication and per-user resume ownership are not implemented.
- Automatic/background deletion retries are not implemented; retries are currently initiated by another client request.
- `ResumeDeletionInProgressError` is not yet mapped to a dedicated HTTP response.
- Deletion failures do not yet store a detailed error message.
- Application-wide logging format and destination configuration are not yet centralized.
