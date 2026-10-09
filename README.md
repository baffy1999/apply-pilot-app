# Apply Pilot

Apply Pilot is a learning project for building a resume-processing API. Its current vertical slice accepts a PDF resume, stores it locally, extracts its text, asks an OpenAI model for structured resume data, and returns that data with an ID and local file path.

## Current request flow

```text
POST /resumes
    -> validate filename and PDF content type
    -> reject a duplicate seen during this process lifetime
    -> save the PDF under uploads/resumes/<uuid>.pdf
    -> extract text with pypdf
    -> parse text into Pydantic models with OpenAI structured output
    -> return the extraction, resume ID, and file path
```

If extraction fails after the file is saved, the service deletes that file before re-raising the error.

## Run locally

Python 3.9 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Add an OpenAI API key to `.env`, then start the API:

```bash
uvicorn app:app --reload
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

Run the tests with:

```bash
pytest
```

The API integration test replaces the real LLM call, so the current test suite should not spend API credits.

## Project layout

- `app.py`: creates the FastAPI application and registers routes.
- `api/resumes.py`: owns the `POST /resumes` HTTP endpoint and request validation.
- `services/resume_service.py`: coordinates storage, PDF text extraction, LLM extraction, and cleanup.
- `models/resume_extraction.py`: defines and validates the structured resume response.
- `storage/local.py`: saves and deletes files beneath a configured local directory.
- `tests/`: covers storage, date validation, and the upload flow.
- `instructions.md`: collaboration rules for an AI coding assistant; it is not loaded or used by the running API.
- `clients/`, `repositories/`, and `tests/fakes/`: currently empty placeholders, not active parts of the application.

## Current limitations

- Duplicate detection uses an in-memory set, so it resets on restart and is not shared between server processes.
- A file hash is recorded before processing succeeds, so a failed extraction can make a retry look like a duplicate until restart.
- The endpoint trusts the declared MIME type; it does not yet inspect the file signature or handle upload-size limits.
- Extracted resume data is returned but is not persisted in a database.
- Uploaded files are local and are not served through a download endpoint.
- Configuration values for chunking, temperature, AWS, S3, and a database exist, but the current request flow does not use them.
