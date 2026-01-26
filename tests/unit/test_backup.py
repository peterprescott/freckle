"""Tests for backup and restore functionality."""

import tempfile
from pathlib import Path

from freckle.backup import BackupManager, RestorePoint


class TestBackupManager:
    """Tests for BackupManager class."""

    def test_create_restore_point_basic(self):
        """Creates restore point for existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            # Create test files
            (home / ".zshrc").write_text("zsh config")
            (home / ".config").mkdir()
            (home / ".config" / "nvim").mkdir()
            (home / ".config" / "nvim" / "init.lua").write_text("nvim config")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc", ".config/nvim/init.lua"],
                reason="pre-sync",
                home=home,
            )

            assert point is not None
            assert point.reason == "pre-sync"
            assert len(point.files) == 2
            assert ".zshrc" in point.files
            assert ".config/nvim/init.lua" in point.files

            # Verify files were copied
            assert (point.path / ".zshrc").exists()
            assert (point.path / ".config" / "nvim" / "init.lua").exists()

    def test_create_restore_point_skips_nonexistent(self):
        """Skips files that don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("zsh config")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc", ".nonexistent"],
                reason="test",
                home=home,
            )

            assert point is not None
            assert len(point.files) == 1
            assert ".zshrc" in point.files

    def test_create_restore_point_returns_none_if_no_files(self):
        """Returns None if no files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".nonexistent"],
                reason="test",
                home=home,
            )

            assert point is None

    def test_list_restore_points(self):
        """Lists restore points in reverse chronological order."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("config")

            manager = BackupManager(backup_dir)

            # Create multiple restore points with delay for unique timestamps
            manager.create_restore_point(
                files=[".zshrc"], reason="first", home=home
            )
            time.sleep(0.01)
            manager.create_restore_point(
                files=[".zshrc"], reason="second", home=home
            )

            points = manager.list_restore_points()

            assert len(points) == 2
            # Newest first
            assert points[0].reason == "second"
            assert points[1].reason == "first"

    def test_get_restore_point_by_prefix(self):
        """Gets restore point by timestamp prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("config")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc"], reason="test", home=home
            )

            # Get by date prefix
            date_prefix = point.timestamp[:10]  # YYYY-MM-DD
            found = manager.get_restore_point(date_prefix)

            assert found is not None
            assert found.timestamp == point.timestamp

    def test_restore_files(self):
        """Restores files from restore point."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            # Create and backup file
            (home / ".zshrc").write_text("original content")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc"], reason="test", home=home
            )

            # Modify file
            (home / ".zshrc").write_text("modified content")
            assert (home / ".zshrc").read_text() == "modified content"

            # Restore
            restored = manager.restore(point, home)

            assert len(restored) == 1
            assert ".zshrc" in restored
            assert (home / ".zshrc").read_text() == "original content"

    def test_restore_specific_files(self):
        """Restores only specified files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("zsh original")
            (home / ".bashrc").write_text("bash original")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc", ".bashrc"], reason="test", home=home
            )

            # Modify both
            (home / ".zshrc").write_text("zsh modified")
            (home / ".bashrc").write_text("bash modified")

            # Restore only .zshrc
            restored = manager.restore(point, home, files=[".zshrc"])

            assert len(restored) == 1
            assert (home / ".zshrc").read_text() == "zsh original"
            assert (home / ".bashrc").read_text() == "bash modified"

    def test_delete_restore_point(self):
        """Deletes restore point."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("config")

            manager = BackupManager(backup_dir)
            point = manager.create_restore_point(
                files=[".zshrc"], reason="test", home=home
            )

            assert point.path.exists()

            result = manager.delete_restore_point(point)

            assert result is True
            assert not point.path.exists()

    def test_prune_old_backups(self):
        """Prunes backups over the limit."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            backup_dir = Path(tmpdir) / "backups"
            home.mkdir()

            (home / ".zshrc").write_text("config")

            manager = BackupManager(backup_dir)
            manager.MAX_RESTORE_POINTS = 3  # Low limit for testing

            # Create more than limit with small delays for unique timestamps
            for i in range(5):
                manager.create_restore_point(
                    files=[".zshrc"], reason=f"backup-{i}", home=home
                )
                time.sleep(0.01)  # Ensure unique millisecond timestamps

            points = manager.list_restore_points()

            # Should have pruned to 3
            assert len(points) == 3
            # Should have kept the 3 newest (backup-4, backup-3, backup-2)
            reasons = [p.reason for p in points]
            assert "backup-4" in reasons
            assert "backup-3" in reasons
            assert "backup-2" in reasons


class TestRestorePoint:
    """Tests for RestorePoint dataclass."""

    def test_display_time(self):
        """Formats timestamp for display."""
        point = RestorePoint(
            timestamp="2026-01-25T10:30:00",
            reason="test",
            files=[".zshrc"],
            path=Path("/tmp/test"),
        )

        assert point.display_time == "2026-01-25 10:30"

    def test_datetime_property(self):
        """Parses timestamp as datetime."""
        point = RestorePoint(
            timestamp="2026-01-25T10:30:00",
            reason="test",
            files=[".zshrc"],
            path=Path("/tmp/test"),
        )

        dt = point.datetime
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 25
        assert dt.hour == 10
        assert dt.minute == 30
