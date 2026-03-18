"""JSON changelog read/write for twingate-idp-migrator.

The changelog is the only persistent artifact from a migration run.
It is used as the source of truth for rollback.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.models import ChangeLog, ChangeLogEntry, MigrationAction
from src.utils.logging import get_logger

logger = get_logger(__name__)


def new_changelog(tenant: str) -> ChangeLog:
    """Create a fresh, empty ChangeLog for a new migration run.

    Args:
        tenant: Twingate tenant name (for audit purposes).

    Returns:
        A new ChangeLog with started_at set to now.
    """
    return ChangeLog(tenant=tenant, started_at=datetime.now())


def append_entry(changelog: ChangeLog, entry: ChangeLogEntry) -> None:
    """Append a single entry to the changelog in-memory.

    Args:
        changelog: The changelog to mutate.
        entry: The entry to append.
    """
    changelog.entries.append(entry)


def save_changelog(changelog: ChangeLog, path: Path) -> None:
    """Serialize and save the changelog to a JSON file.

    Writes atomically via a temp file to avoid partial writes. Creates
    parent directories if they do not exist.

    Args:
        changelog: The changelog to save.
        path: Destination file path (will be created or overwritten).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            changelog.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    logger.info("changelog_saved", path=str(path), entries=len(changelog.entries))


def load_changelog(path: Path) -> ChangeLog:
    """Load a changelog from a JSON file.

    Args:
        path: Path to a previously saved changelog JSON file.

    Returns:
        Parsed ChangeLog.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed as a valid ChangeLog.
    """
    try:
        data = path.read_text(encoding="utf-8")
        changelog = ChangeLog.model_validate_json(data)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to parse changelog at {path}: {exc}") from exc

    logger.info("changelog_loaded", path=str(path), entries=len(changelog.entries))
    return changelog


def make_entry(
    action: MigrationAction,
    success: bool,
    error: str | None = None,
) -> ChangeLogEntry:
    """Construct a ChangeLogEntry for a just-executed action.

    Args:
        action: The MigrationAction that was attempted.
        success: Whether the API call succeeded.
        error: Error message if success=False.

    Returns:
        A ChangeLogEntry with executed_at set to now.
    """
    return ChangeLogEntry(
        action=action,
        executed_at=datetime.now(),
        success=success,
        error=error,
    )
