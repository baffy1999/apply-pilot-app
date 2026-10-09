DELETE resume by resume_id

1. Atomically claim the deletion:
   - ACTIVE → DELETING
   - DELETE_FAILED → DELETING
   - increment deletion_attempts
   - set last_deletion_attempt_at
   - return the stored file_url

2. If no row was returned:
   - resume does not exist → 404
   - resume is already DELETING → report deletion in progress

3. Delete the PDF using the stored file_url.
   - A missing file counts as successful deletion.
   - Retry only a limited number of times.

4. If file deletion fails:
   - set status to DELETE_FAILED
   - store last_deletion_error
   - return an error

5. If file deletion succeeds:
   - begin the final database transaction
   - DELETE FROM resumes WHERE id = resume_id
   - PostgreSQL cascades all related deletions
   - commit

6. If the final database transaction fails:
   - PostgreSQL rolls back all database deletions
   - keep the resume as DELETING or change it to DELETE_FAILED
   - store the database error
   - retry only if it is a transient database failure

7. If commit succeeds:
   - return 204 No Content