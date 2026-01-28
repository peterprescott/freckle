"""Tests for save command."""

from pathlib import Path


class TestSaveGitCommands:
    """Tests to ensure save uses correct git commands."""

    def test_save_does_not_use_git_add_A(self):
        """Ensure save.py does NOT use 'git add -A'.

        Using 'git add -A' with a bare repo and work-tree set to $HOME
        would try to add ALL files in the home directory, which is:
        1. Extremely slow (traverses entire home)
        2. Error-prone (permission issues, too many files)
        3. Wrong behavior (we only want tracked files)

        The correct approach is to add files individually by path,
        which is what single-file commits do.

        This test reads the source code to ensure we don't regress.
        """
        src = Path(__file__).parent.parent.parent / "src"
        save_py = src / "freckle/cli/save.py"
        content = save_py.read_text()

        # Should NOT contain 'add", "-A"' or "add', '-A'"
        assert '"add", "-A"' not in content, (
            "save.py must not use 'git add -A'"
        )
        assert "'add', '-A'" not in content, (
            "save.py must not use 'git add -A'"
        )

    def test_save_uses_single_file_commits(self):
        """Ensure save.py uses single-file commit pattern.

        Single-file commits enable:
        1. Clean config sync (config commit is isolated)
        2. Atomic rollback of individual files
        3. Safe staging (no -A that could add entire $HOME)
        """
        src = Path(__file__).parent.parent.parent / "src"
        save_py = src / "freckle/cli/save.py"
        content = save_py.read_text()

        # Should have the single-file commit function
        assert "_commit_files_individually" in content, (
            "save.py should use _commit_files_individually for single-file "
            "commits"
        )


class TestNoGitAddAllInCodebase:
    """Ensure no git add -A usage anywhere in the codebase."""

    def test_no_git_add_A_anywhere(self):
        """Scan entire src/ for dangerous 'git add -A' usage.

        The bare repo pattern with work-tree=$HOME means 'git add -A'
        would try to stage every file in the home directory.
        This is never correct for our use case.
        """
        src_dir = Path(__file__).parent.parent.parent / "src"

        violations = []
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text()
            # Check for various patterns that could be git add -A
            if '"add", "-A"' in content or "'add', '-A'" in content:
                violations.append(str(py_file.relative_to(src_dir.parent)))
            if '"add", "-a"' in content or "'add', '-a'" in content:
                # -a is also dangerous (adds all modified tracked files AND
                # commits, but combined with other flags could be problematic)
                # Actually -a is okay for commits, skip this check
                pass

        assert not violations, (
            f"Found dangerous 'git add -A' in: {violations}\n"
            "Use 'git add -u' (tracked files only) or add specific files."
        )
