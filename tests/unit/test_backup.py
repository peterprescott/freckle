"""Tests for backup module."""

import json
from pathlib import Path

from freckle.backup import BackupManager, RestorePoint


class TestBackupManagerInit:
    """Tests for BackupManager initialization."""

    def test_default_backup_dir(self):
        """Uses default backup dir when none provided."""
        from pathlib import Path

        manager = BackupManager()

        expected = Path.home() / ".local" / "share" / "freckle" / "backups"
        assert manager.backup_dir == expected


class TestRestorePoint:
    """Tests for RestorePoint dataclass."""

    def test_datetime_property(self):
        """datetime property parses timestamp."""
        point = RestorePoint(
            timestamp="2026-01-25T10:30:00.000",
            reason="test",
            files=[".zshrc"],
            path=Path("/tmp/backup")
        )

        dt = point.datetime
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 25
        assert dt.hour == 10
        assert dt.minute == 30

    def test_display_time_property(self):
        """display_time returns human-readable format."""
        point = RestorePoint(
            timestamp="2026-01-25T10:30:00.000",
            reason="test",
            files=[".zshrc"],
            path=Path("/tmp/backup")
        )

        assert point.display_time == "2026-01-25 10:30"


class TestBackupManagerCreateRestorePoint:
    """Tests for BackupManager.create_restore_point method."""

    def test_creates_backup_directory(self, tmp_path):
        """Creates backup directory structure."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="test",
            home=home
        )

        assert point is not None
        assert point.path.exists()
        assert (point.path / ".zshrc").exists()

    def test_returns_none_when_no_files_exist(self, tmp_path):
        """Returns None when no files exist to backup."""
        home = tmp_path / "home"
        home.mkdir()

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc", ".vimrc"],
            reason="test",
            home=home
        )

        assert point is None

    def test_filters_nonexistent_files(self, tmp_path):
        """Only backs up files that exist."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")
        # .vimrc doesn't exist

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc", ".vimrc"],
            reason="test",
            home=home
        )

        assert point is not None
        assert ".zshrc" in point.files
        assert ".vimrc" not in point.files

    def test_writes_manifest(self, tmp_path):
        """Writes manifest.json with metadata."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="pre-sync",
            home=home
        )

        manifest_path = point.path / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["reason"] == "pre-sync"
        assert ".zshrc" in manifest["files"]

    def test_preserves_directory_structure(self, tmp_path):
        """Preserves nested directory structure."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".config").mkdir()
        (home / ".config" / "nvim").mkdir()
        (home / ".config" / "nvim" / "init.lua").write_text("-- nvim config")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".config/nvim/init.lua"],
            reason="test",
            home=home
        )

        assert (point.path / ".config" / "nvim" / "init.lua").exists()


class TestBackupManagerListRestorePoints:
    """Tests for BackupManager.list_restore_points method."""

    def test_returns_empty_when_no_backups(self, tmp_path):
        """Returns empty list when backup dir doesn't exist."""
        manager = BackupManager(backup_dir=tmp_path / "backups")
        points = manager.list_restore_points()

        assert points == []

    def test_returns_points_sorted_by_timestamp(self, tmp_path):
        """Returns points sorted by timestamp, newest first."""
        backup_dir = tmp_path / "backups"

        # Create two restore points
        for i, ts in enumerate(["2026-01-25T10:00:00", "2026-01-25T11:00:00"]):
            point_dir = backup_dir / ts.replace(":", "-")
            point_dir.mkdir(parents=True)
            manifest = {
                "timestamp": ts,
                "reason": f"test{i}",
                "files": [".zshrc"]
            }
            (point_dir / "manifest.json").write_text(json.dumps(manifest))

        manager = BackupManager(backup_dir=backup_dir)
        points = manager.list_restore_points()

        assert len(points) == 2
        assert points[0].timestamp == "2026-01-25T11:00:00"  # Newest first

    def test_skips_non_directories(self, tmp_path):
        """Skips files that aren't directories."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "somefile.txt").write_text("not a backup")

        manager = BackupManager(backup_dir=backup_dir)
        points = manager.list_restore_points()

        assert points == []

    def test_skips_directories_without_manifest(self, tmp_path):
        """Skips directories without manifest.json."""
        backup_dir = tmp_path / "backups"
        (backup_dir / "incomplete").mkdir(parents=True)

        manager = BackupManager(backup_dir=backup_dir)
        points = manager.list_restore_points()

        assert points == []

    def test_skips_invalid_manifest(self, tmp_path):
        """Skips directories with invalid manifest."""
        backup_dir = tmp_path / "backups"
        point_dir = backup_dir / "2026-01-25T10-00-00"
        point_dir.mkdir(parents=True)
        (point_dir / "manifest.json").write_text("invalid json{")

        manager = BackupManager(backup_dir=backup_dir)
        points = manager.list_restore_points()

        assert points == []

    def test_skips_manifest_missing_keys(self, tmp_path):
        """Skips manifest missing required keys."""
        backup_dir = tmp_path / "backups"
        point_dir = backup_dir / "2026-01-25T10-00-00"
        point_dir.mkdir(parents=True)
        (point_dir / "manifest.json").write_text(json.dumps({"foo": "bar"}))

        manager = BackupManager(backup_dir=backup_dir)
        points = manager.list_restore_points()

        assert points == []


class TestBackupManagerGetRestorePoint:
    """Tests for BackupManager.get_restore_point method."""

    def test_get_by_timestamp(self, tmp_path):
        """Gets point by timestamp prefix."""
        backup_dir = tmp_path / "backups"
        point_dir = backup_dir / "2026-01-25T10-00-00"
        point_dir.mkdir(parents=True)
        manifest = {
            "timestamp": "2026-01-25T10:00:00",
            "reason": "test",
            "files": [".zshrc"]
        }
        (point_dir / "manifest.json").write_text(json.dumps(manifest))

        manager = BackupManager(backup_dir=backup_dir)
        point = manager.get_restore_point("2026-01-25T10")

        assert point is not None
        assert point.reason == "test"

    def test_get_by_display_time(self, tmp_path):
        """Gets point by display time prefix."""
        backup_dir = tmp_path / "backups"
        point_dir = backup_dir / "2026-01-25T10-00-00"
        point_dir.mkdir(parents=True)
        manifest = {
            "timestamp": "2026-01-25T10:00:00",
            "reason": "test",
            "files": [".zshrc"]
        }
        (point_dir / "manifest.json").write_text(json.dumps(manifest))

        manager = BackupManager(backup_dir=backup_dir)
        point = manager.get_restore_point("2026-01-25 10:00")

        assert point is not None
        assert point.reason == "test"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when no matching point."""
        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.get_restore_point("2099-01-01")

        assert point is None


class TestBackupManagerRestore:
    """Tests for BackupManager.restore method."""

    def test_restores_all_files(self, tmp_path):
        """Restores all files from restore point."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# original")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="test",
            home=home
        )

        # Modify the file
        (home / ".zshrc").write_text("# modified")

        # Restore
        restored = manager.restore(point, home)

        assert restored == [".zshrc"]
        assert (home / ".zshrc").read_text() == "# original"

    def test_restores_specific_files(self, tmp_path):
        """Restores only specified files."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")
        (home / ".vimrc").write_text("# vimrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc", ".vimrc"],
            reason="test",
            home=home
        )

        # Modify both files
        (home / ".zshrc").write_text("# modified zshrc")
        (home / ".vimrc").write_text("# modified vimrc")

        # Restore only .zshrc
        restored = manager.restore(point, home, files=[".zshrc"])

        assert restored == [".zshrc"]
        assert (home / ".zshrc").read_text() == "# zshrc"
        assert (home / ".vimrc").read_text() == "# modified vimrc"

    def test_skips_files_not_in_point(self, tmp_path):
        """Skips files that weren't in the restore point."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="test",
            home=home
        )

        restored = manager.restore(point, home, files=[".zshrc", ".vimrc"])

        assert restored == [".zshrc"]

    def test_skips_missing_backup_file(self, tmp_path):
        """Skips if backup file was deleted."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="test",
            home=home
        )

        # Delete the backup file
        (point.path / ".zshrc").unlink()

        restored = manager.restore(point, home)

        assert restored == []

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories when restoring."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".config").mkdir()
        (home / ".config" / "app").mkdir()
        (home / ".config" / "app" / "config.yaml").write_text("key: value")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".config/app/config.yaml"],
            reason="test",
            home=home
        )

        # Delete the entire directory structure
        import shutil
        shutil.rmtree(home / ".config")

        # Restore
        restored = manager.restore(point, home)

        assert ".config/app/config.yaml" in restored
        assert (home / ".config" / "app" / "config.yaml").exists()


class TestBackupManagerDeleteRestorePoint:
    """Tests for BackupManager.delete_restore_point method."""

    def test_deletes_restore_point(self, tmp_path):
        """Deletes restore point directory."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = manager.create_restore_point(
            files=[".zshrc"],
            reason="test",
            home=home
        )

        assert point.path.exists()

        result = manager.delete_restore_point(point)

        assert result is True
        assert not point.path.exists()

    def test_returns_false_when_not_found(self, tmp_path):
        """Returns False when point doesn't exist."""
        manager = BackupManager(backup_dir=tmp_path / "backups")
        point = RestorePoint(
            timestamp="2026-01-25T10:00:00",
            reason="test",
            files=[],
            path=tmp_path / "nonexistent"
        )

        result = manager.delete_restore_point(point)

        assert result is False


class TestBackupManagerPruneOldBackups:
    """Tests for BackupManager._prune_old_backups method."""

    def test_prunes_over_limit(self, tmp_path):
        """Removes oldest backups when over limit."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        manager.MAX_RESTORE_POINTS = 3

        # Create more backups than the limit
        for i in range(5):
            manager.create_restore_point(
                files=[".zshrc"],
                reason=f"test{i}",
                home=home
            )
            import time
            time.sleep(0.01)  # Ensure unique timestamps

        points = manager.list_restore_points()

        assert len(points) == 3

    def test_keeps_newest_backups(self, tmp_path):
        """Keeps the newest backups when pruning."""
        home = tmp_path / "home"
        home.mkdir()
        (home / ".zshrc").write_text("# zshrc")

        manager = BackupManager(backup_dir=tmp_path / "backups")
        manager.MAX_RESTORE_POINTS = 2

        # Create 3 backups
        reasons = []
        for i in range(3):
            point = manager.create_restore_point(
                files=[".zshrc"],
                reason=f"test{i}",
                home=home
            )
            reasons.append(point.reason)
            import time
            time.sleep(0.01)

        points = manager.list_restore_points()

        # Should have the 2 newest (test1, test2)
        assert len(points) == 2
        point_reasons = [p.reason for p in points]
        assert "test2" in point_reasons
        assert "test1" in point_reasons
        assert "test0" not in point_reasons
