from __future__ import annotations

from pathlib import Path


class LocalFileStorage:
    def __init__(self, base_directory: str | Path) -> None:
        self.base_directory = Path(base_directory).resolve()
        self.base_directory.mkdir(parents=True, exist_ok=True)

    def save(self, *, object_key: str, content: bytes) -> str:
        """Save file content and return its storage key."""
        path = self._path_for(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return object_key

    def delete(self, object_key: str) -> None:
        """Delete a stored file if it exists."""
        self._path_for(object_key).unlink(missing_ok=True)

    def file_path(self, object_key: str) -> str:
        """Return the local path for a stored file."""
        return str(self._path_for(object_key))

    def _path_for(self, object_key: str) -> Path:
        path = (self.base_directory / object_key).resolve()
        if not path.is_relative_to(self.base_directory):
            raise ValueError("Object key must stay inside the storage directory")
        return path
