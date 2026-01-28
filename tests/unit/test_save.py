"""Tests for save command."""

from pathlib import Path


class TestSaveGitCommands:
    """Tests to ensure save uses correct git commands."""

    def test_save_uses_git_add_u_not_git_add_A(self):
        """Ensure save.py uses 'git add -u' not 'git add -A'.

        Using 'git add -A' with a bare repo and work-tree set to $HOME
        would try to add ALL files in the home directory, which is:
        1. Extremely slow (traverses entire home)
        2. Error-prone (permission issues, too many files)
        3. Wrong behavior (we only want tracked files)

        This test reads the source code to ensure we don't regress.
        """
        src = Path(__file__).parent.parent.parent / "src"
        save_py = src / "freckle/cli/save.py"
        content = save_py.read_text()

        # Should NOT contain 'add", "-A"' or "add', '-A'"
        assert '"add", "-A"' not in content, (
            "save.py must not use 'git add -A' - use 'git add -u' instead"
        )
        assert "'add', '-A'" not in content, (
            "save.py must not use 'git add -A' - use 'git add -u' instead"
        )

        # Should contain 'add", "-u"' (the correct command)
        assert '"add", "-u"' in content, (
            "save.py should use 'git add -u' to only stage tracked files"
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
