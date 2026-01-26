"""Backup and restore functionality for dotfiles.

Provides automatic backup of files before destructive operations and
restore capability to recover previous versions.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class RestorePoint:
    """A point-in-time backup of files."""

    timestamp: str
    reason: str
    files: list[str]
    path: Path

    @property
    def datetime(self) -> datetime:
        """Parse timestamp as datetime."""
        return datetime.fromisoformat(self.timestamp)

    @property
    def display_time(self) -> str:
        """Human-readable timestamp."""
        dt = self.datetime
        return dt.strftime("%Y-%m-%d %H:%M")


class BackupManager:
    """Manages file backups and restore points."""

    MAX_RESTORE_POINTS = 10

    def __init__(self, backup_dir: Optional[Path] = None):
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups. Defaults to
                        ~/.local/share/freckle/backups/
        """
        if backup_dir is None:
            backup_dir = (
                Path.home() / ".local" / "share" / "freckle" / "backups"
            )
        self.backup_dir = backup_dir

    def create_restore_point(
        self,
        files: list[str],
        reason: str,
        home: Path,
    ) -> Optional[RestorePoint]:
        """Create a restore point for the given files.

        Args:
            files: List of file paths relative to home directory
            reason: Reason for backup (e.g., "pre-sync", "pre-checkout")
            home: Home directory path

        Returns:
            RestorePoint if files were backed up, None if no files existed
        """
        # Filter to files that actually exist
        existing_files = []
        for f in files:
            full_path = home / f
            if full_path.is_file():
                existing_files.append(f)

        if not existing_files:
            return None

        # Create timestamped backup directory with milliseconds for uniqueness
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        safe_timestamp = timestamp.replace(":", "-").replace(".", "-")
        point_dir = self.backup_dir / safe_timestamp
        point_dir.mkdir(parents=True, exist_ok=True)

        # Copy files preserving directory structure
        for f in existing_files:
            src = home / f
            dst = point_dir / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # Write manifest
        manifest = {
            "timestamp": timestamp,
            "reason": reason,
            "files": existing_files,
        }
        manifest_path = point_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Prune old backups
        self._prune_old_backups()

        return RestorePoint(
            timestamp=timestamp,
            reason=reason,
            files=existing_files,
            path=point_dir,
        )

    def list_restore_points(self) -> list[RestorePoint]:
        """List available restore points, newest first."""
        if not self.backup_dir.exists():
            return []

        points = []
        for entry in self.backup_dir.iterdir():
            if not entry.is_dir():
                continue

            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue

            try:
                manifest = json.loads(manifest_path.read_text())
                points.append(
                    RestorePoint(
                        timestamp=manifest["timestamp"],
                        reason=manifest["reason"],
                        files=manifest["files"],
                        path=entry,
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by timestamp, newest first
        points.sort(key=lambda p: p.timestamp, reverse=True)
        return points

    def get_restore_point(self, identifier: str) -> Optional[RestorePoint]:
        """Get a restore point by timestamp prefix or date.

        Args:
            identifier: Timestamp prefix (e.g., "2026-01-25") or full timestamp

        Returns:
            RestorePoint if found, None otherwise
        """
        points = self.list_restore_points()

        for point in points:
            # Match by full timestamp or prefix
            if point.timestamp.startswith(identifier):
                return point
            # Match by display time
            if point.display_time.startswith(identifier):
                return point

        return None

    def restore(
        self,
        point: RestorePoint,
        home: Path,
        files: Optional[list[str]] = None,
    ) -> list[str]:
        """Restore files from a restore point.

        Args:
            point: RestorePoint to restore from
            home: Home directory path
            files: Specific files to restore (None = all files in point)

        Returns:
            List of files that were restored
        """
        files_to_restore = files if files else point.files
        restored = []

        for f in files_to_restore:
            if f not in point.files:
                continue

            src = point.path / f
            dst = home / f

            if not src.exists():
                continue

            # Ensure parent directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)

            # Copy file back
            shutil.copy2(src, dst)
            restored.append(f)

        return restored

    def delete_restore_point(self, point: RestorePoint) -> bool:
        """Delete a restore point.

        Args:
            point: RestorePoint to delete

        Returns:
            True if deleted, False if not found
        """
        if point.path.exists():
            shutil.rmtree(point.path)
            return True
        return False

    def _prune_old_backups(self) -> None:
        """Remove oldest backups if over the limit."""
        points = self.list_restore_points()

        if len(points) > self.MAX_RESTORE_POINTS:
            for old_point in points[self.MAX_RESTORE_POINTS :]:
                self.delete_restore_point(old_point)
