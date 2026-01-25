"""Dotfiles management using the bare repository pattern with pygit2."""

import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

import pygit2

logger = logging.getLogger(__name__)


class CheckoutConflictCollector(pygit2.CheckoutCallbacks):
    """Callback handler that collects checkout conflicts without aborting."""
    
    def __init__(self):
        super().__init__()
        self.conflicts: List[str] = []
        self.updated: List[str] = []
    
    def checkout_notify_flags(self) -> int:
        """Tell libgit2 what events to notify us about."""
        return (
            pygit2.GIT_CHECKOUT_NOTIFY_CONFLICT |
            pygit2.GIT_CHECKOUT_NOTIFY_DIRTY |
            pygit2.GIT_CHECKOUT_NOTIFY_UNTRACKED
        )
    
    def checkout_notify(self, why: int, path: str, baseline, target, workdir) -> int:
        """Called before each file is modified during checkout.
        
        Return 0 to continue, non-zero to abort checkout.
        We collect conflicts but don't abort - we'll handle them after.
        """
        if why in (
            pygit2.GIT_CHECKOUT_NOTIFY_CONFLICT,
            pygit2.GIT_CHECKOUT_NOTIFY_DIRTY,
            pygit2.GIT_CHECKOUT_NOTIFY_UNTRACKED
        ):
            self.conflicts.append(path)
        return 0  # Continue collecting, don't abort


class DotfilesManager:
    """Manages dotfiles using a bare git repository with a separate work tree.
    
    This implements the "bare repo" pattern for dotfiles:
    - The git repository is stored in a bare format (e.g., ~/.dotfiles)
    - The work tree is the user's home directory
    - This allows tracking dotfiles without polluting $HOME with .git
    """
    
    def __init__(self, repo_url: str, dotfiles_dir: Path, work_tree: Path, branch: str = "main"):
        self.repo_url = repo_url
        self.dotfiles_dir = Path(dotfiles_dir)
        self.work_tree = Path(work_tree)
        self.branch = branch
        self._repo: Optional[pygit2.Repository] = None

    def _get_repo(self) -> pygit2.Repository:
        """Get or initialize the pygit2 Repository object."""
        if self._repo is None:
            if not self.dotfiles_dir.exists():
                logger.info(f"Cloning bare repository from {self.repo_url} to {self.dotfiles_dir}")
                self._repo = pygit2.clone_repository(
                    self.repo_url,
                    str(self.dotfiles_dir),
                    bare=True
                )
            else:
                self._repo = pygit2.Repository(str(self.dotfiles_dir))
        return self._repo

    def _get_available_branches(self) -> List[str]:
        """Get list of all available branch names (local and remote)."""
        repo = self._get_repo()
        branches = set()
        
        for ref in repo.references:
            if ref.startswith("refs/heads/"):
                branches.add(ref[len("refs/heads/"):])
            elif ref.startswith("refs/remotes/origin/"):
                branch = ref[len("refs/remotes/origin/"):]
                if branch != "HEAD":
                    branches.add(branch)
        
        return sorted(branches)

    def _resolve_branch(self) -> Dict[str, Any]:
        """Resolve which branch to use, with detailed context.
        
        Returns a dict with:
        - effective: The branch to actually use
        - configured: The originally configured branch
        - reason: Why this branch was chosen ('exact', 'main_master_swap', 'fallback_head', 'fallback_default', 'not_found')
        - available: List of available branches (if configured wasn't found)
        - message: Human-readable explanation (if not exact match)
        """
        repo = self._get_repo()
        configured = self.branch
        available = self._get_available_branches()
        
        # Check if configured branch exists
        if configured in available:
            return {
                "effective": configured,
                "configured": configured,
                "reason": "exact",
                "available": available,
                "message": None,
            }
        
        # Common main/master swap
        swap_map = {"main": "master", "master": "main"}
        if configured in swap_map and swap_map[configured] in available:
            swapped = swap_map[configured]
            return {
                "effective": swapped,
                "configured": configured,
                "reason": "main_master_swap",
                "available": available,
                "message": f"Branch '{configured}' not found; using '{swapped}' instead.",
            }
        
        # Try HEAD
        try:
            if not repo.head_is_unborn:
                head_ref = repo.head.name
                if head_ref.startswith("refs/heads/"):
                    head_branch = head_ref[len("refs/heads/"):]
                    return {
                        "effective": head_branch,
                        "configured": configured,
                        "reason": "fallback_head",
                        "available": available,
                        "message": f"Branch '{configured}' not found; using current HEAD '{head_branch}'.",
                    }
        except Exception:
            pass
        
        # Try common defaults
        for fallback in ["main", "master"]:
            if fallback in available:
                return {
                    "effective": fallback,
                    "configured": configured,
                    "reason": "fallback_default",
                    "available": available,
                    "message": f"Branch '{configured}' not found; falling back to '{fallback}'.",
                }
        
        # Nothing found - use configured anyway (will likely fail)
        return {
            "effective": configured,
            "configured": configured,
            "reason": "not_found",
            "available": available,
            "message": f"Branch '{configured}' not found. Available branches: {', '.join(available) or '(none)'}",
        }

    def _get_tracked_files(self, branch: str = None) -> List[str]:
        """Get list of all files tracked in the target branch."""
        repo = self._get_repo()
        branch = branch or self.branch
        
        # Try remote branch first, then local
        try:
            ref = repo.references.get(f"refs/remotes/origin/{branch}")
            if ref is None:
                ref = repo.references.get(f"refs/heads/{branch}")
            if ref is None:
                return []
            
            commit = ref.peel(pygit2.Commit)
            tree = commit.tree
            
            files = []
            self._collect_tree_files(tree, "", files)
            return files
        except Exception as e:
            logger.warning(f"Could not get tracked files: {e}")
            return []

    def _collect_tree_files(self, tree: pygit2.Tree, prefix: str, files: List[str]):
        """Recursively collect all file paths from a tree."""
        for entry in tree:
            path = f"{prefix}{entry.name}" if prefix else entry.name
            if entry.type_str == "tree":
                subtree = self._get_repo()[entry.id]
                self._collect_tree_files(subtree, f"{path}/", files)
            else:
                files.append(path)

    def _find_existing_files(self, tracked_files: List[str]) -> List[str]:
        """Find which tracked files already exist in the work tree."""
        existing = []
        for file_path in tracked_files:
            local_path = self.work_tree / file_path
            if local_path.exists() and local_path.is_file():
                existing.append(file_path)
        return existing

    def _backup_files(self, file_paths: List[str]) -> Optional[Path]:
        """Move files to a timestamped backup directory."""
        if not file_paths:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.work_tree / f".dotfiles_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Backing up {len(file_paths)} existing files to {backup_dir}")
        for file_path in file_paths:
            src = self.work_tree / file_path
            dst = backup_dir / file_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        
        return backup_dir

    def _ensure_fetch_refspec(self):
        """Ensure fetch refspec is configured for remote tracking.
        
        Bare repos created manually often lack the fetch refspec,
        which prevents remote-tracking branches from being created.
        """
        repo = self._get_repo()
        try:
            remote = repo.remotes["origin"]
            expected_refspec = "+refs/heads/*:refs/remotes/origin/*"
            current_refspecs = list(remote.fetch_refspecs)
            
            if expected_refspec not in current_refspecs:
                logger.info("Configuring fetch refspec for remote tracking")
                # add_fetch is on repo.remotes, not the remote object
                repo.remotes.add_fetch("origin", expected_refspec)
        except Exception as e:
            logger.debug(f"Could not configure fetch refspec: {e}")

    def _fetch(self) -> bool:
        """Fetch from remote origin. Returns True on success.
        
        Uses git subprocess for reliability with credential helpers.
        """
        self._ensure_fetch_refspec()
        
        try:
            # Use git subprocess - it handles credentials properly
            result = subprocess.run(
                ["git", "--git-dir", str(self.dotfiles_dir), "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.warning(f"Fetch failed: {result.stderr.strip()}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Fetch timed out")
            return False
        except Exception as e:
            logger.warning(f"Could not fetch from remote: {e}")
            return False

    def _setup_branch(self):
        """Set up the local branch to track remote after cloning."""
        repo = self._get_repo()
        
        # Fetch to get remote refs
        self._fetch()
        
        # Get the remote branch reference
        remote_ref = repo.references.get(f"refs/remotes/origin/{self.branch}")
        if remote_ref is None:
            raise RuntimeError(f"Remote branch origin/{self.branch} not found")
        
        # Create local branch pointing to the same commit
        commit = remote_ref.peel(pygit2.Commit)
        repo.references.create(f"refs/heads/{self.branch}", commit.id, force=True)
        
        # Set HEAD to point to the local branch
        repo.set_head(f"refs/heads/{self.branch}")

    def _checkout_to_worktree(self, force: bool = False):
        """Checkout files to the work tree directory."""
        repo = self._get_repo()
        
        # Get the commit to checkout
        ref = repo.references.get(f"refs/heads/{self.branch}")
        if ref is None:
            ref = repo.references.get(f"refs/remotes/origin/{self.branch}")
        if ref is None:
            raise RuntimeError(f"Branch {self.branch} not found")
        
        commit = ref.peel(pygit2.Commit)
        
        # Determine checkout strategy
        if force:
            strategy = pygit2.GIT_CHECKOUT_FORCE
        else:
            strategy = pygit2.GIT_CHECKOUT_SAFE | pygit2.GIT_CHECKOUT_RECREATE_MISSING
        
        # Checkout with the work tree directory
        repo.checkout_tree(
            commit,
            strategy=strategy,
            directory=str(self.work_tree)
        )

    def setup(self):
        """Initial setup: clone repo and checkout dotfiles to home directory.
        
        This method:
        1. Clones the bare repository if it doesn't exist
        2. Fetches and sets up the branch
        3. Detects files that would conflict with checkout
        4. Backs up conflicting files
        5. Performs the checkout
        """
        if self.dotfiles_dir.exists():
            logger.info("Dotfiles repository already exists")
            return
        
        # Clone and setup
        repo = self._get_repo()  # This clones if needed
        self._setup_branch()
        
        # Find files that would conflict
        tracked = self._get_tracked_files()
        existing = self._find_existing_files(tracked)
        
        # Backup any existing files
        backup_dir = self._backup_files(existing)
        if backup_dir:
            logger.info(f"Backed up existing files to {backup_dir}")
        
        # Now checkout (should succeed since we backed up conflicts)
        self._checkout_to_worktree(force=True)
        logger.info("Checkout complete!")

    def get_detailed_status(self, offline: bool = False) -> Dict[str, Any]:
        """Get detailed sync status of the dotfiles repository.
        
        Args:
            offline: If True, skip fetching from remote.
            
        Returns:
            Dictionary with sync status information.
        """
        if not self.dotfiles_dir.exists():
            return {"initialized": False}
        
        repo = self._get_repo()
        
        fetch_failed = False
        if not offline:
            fetch_failed = not self._fetch()
        
        # Determine which branch to use (with fallback)
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]
        
        # Get changed files by comparing work tree to HEAD
        changed_files = self._get_changed_files(branch=effective_branch)
        
        # Get local and remote commits
        local_ref = repo.references.get(f"refs/heads/{effective_branch}")
        remote_ref = repo.references.get(f"refs/remotes/origin/{effective_branch}")
        
        if local_ref is None:
            return {
                "initialized": True,
                "branch": effective_branch,
                "branch_info": branch_info,
                "has_local_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "is_ahead": False,
                "is_behind": False,
                "local_commit": None,
                "remote_commit": None,
                "fetch_failed": fetch_failed,
            }
        
        local_commit = local_ref.peel(pygit2.Commit)
        local_oid = local_commit.id
        
        if remote_ref is None:
            return {
                "initialized": True,
                "branch": effective_branch,
                "branch_info": branch_info,
                "has_local_changes": len(changed_files) > 0,
                "changed_files": changed_files,
                "is_ahead": False,
                "is_behind": False,
                "local_commit": str(local_oid)[:7],
                "remote_commit": None,
                "fetch_failed": fetch_failed,
            }
        
        remote_commit = remote_ref.peel(pygit2.Commit)
        remote_oid = remote_commit.id
        
        # Calculate ahead/behind
        ahead, behind = repo.ahead_behind(local_oid, remote_oid)
        
        return {
            "initialized": True,
            "branch": effective_branch,
            "branch_info": branch_info,
            "has_local_changes": len(changed_files) > 0,
            "changed_files": changed_files,
            "is_ahead": ahead > 0,
            "is_behind": behind > 0,
            "ahead_count": ahead,
            "behind_count": behind,
            "local_commit": str(local_oid)[:7],
            "remote_commit": str(remote_oid)[:7],
            "fetch_failed": fetch_failed,
        }

    def _get_changed_files(self, branch: str = None) -> List[str]:
        """Get list of files that differ between work tree and HEAD."""
        repo = self._get_repo()
        changed = []
        branch = branch or self.branch
        
        # Get HEAD tree
        try:
            head_ref = repo.references.get(f"refs/heads/{branch}")
            if head_ref is None:
                return []
            head_commit = head_ref.peel(pygit2.Commit)
            head_tree = head_commit.tree
        except Exception:
            return []
        
        # Compare each tracked file with work tree
        tracked = self._get_tracked_files(branch=branch)
        for file_path in tracked:
            local_path = self.work_tree / file_path
            
            if not local_path.exists():
                # File is tracked but missing locally
                changed.append(file_path)
                continue
            
            # Get the blob from HEAD
            try:
                entry = head_tree[file_path]
                head_blob = repo[entry.id]
                
                # Compare with local file
                local_content = local_path.read_bytes()
                if local_content != head_blob.data:
                    changed.append(file_path)
            except KeyError:
                # File not in HEAD (shouldn't happen for tracked files)
                pass
        
        return changed

    def get_file_sync_status(self, relative_path: str) -> str:
        """Get sync status of a specific file.
        
        Returns one of:
        - 'not-initialized': Repo doesn't exist
        - 'not-found': File doesn't exist locally and isn't tracked
        - 'missing': File is tracked but doesn't exist locally
        - 'untracked': File exists locally but isn't tracked
        - 'up-to-date': File matches HEAD
        - 'modified': File has local changes
        - 'behind': File differs from remote (remote is newer)
        - 'error': Could not determine status
        """
        if not self.dotfiles_dir.exists():
            return "not-initialized"
        
        repo = self._get_repo()
        local_file = self.work_tree / relative_path
        
        # Resolve the actual branch to use
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]
        
        # Check if tracked in HEAD
        head_blob = None
        try:
            head_ref = repo.references.get(f"refs/heads/{effective_branch}")
            if head_ref:
                head_tree = head_ref.peel(pygit2.Commit).tree
                entry = head_tree[relative_path]
                head_blob = repo[entry.id]
        except (KeyError, Exception):
            pass
        
        # Check if tracked in remote
        remote_blob = None
        try:
            remote_ref = repo.references.get(f"refs/remotes/origin/{effective_branch}")
            if remote_ref:
                remote_tree = remote_ref.peel(pygit2.Commit).tree
                entry = remote_tree[relative_path]
                remote_blob = repo[entry.id]
        except (KeyError, Exception):
            pass
        
        is_tracked = head_blob is not None or remote_blob is not None
        
        if not local_file.exists():
            return "missing" if is_tracked else "not-found"
        
        if not is_tracked:
            return "untracked"
        
        try:
            local_content = local_file.read_bytes()
            
            # Check if matches remote (up-to-date)
            if remote_blob and local_content == remote_blob.data:
                return "up-to-date"
            
            # Check if differs from HEAD (modified locally)
            if head_blob and local_content != head_blob.data:
                return "modified"
            
            # Matches HEAD but differs from remote (behind)
            if remote_blob and head_blob and head_blob.id != remote_blob.id:
                return "behind"
            
            return "up-to-date"
        except Exception:
            return "error"

    def commit_and_push(self, message: str) -> Dict[str, Any]:
        """Commit local changes to tracked files and push to remote.
        
        Only commits changes to files already tracked in the repository.
        
        Returns:
            Dictionary with result info:
            - success: Whether the operation completed successfully
            - committed: Whether a commit was made
            - pushed: Whether the push succeeded
            - error: Error message if any step failed
        """
        repo = self._get_repo()
        result = {"success": False, "committed": False, "pushed": False, "error": None}
        
        # Resolve the actual branch to use
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]
        
        if branch_info["reason"] == "not_found":
            result["error"] = branch_info["message"]
            return result
        
        # Get changed files
        changed = self._get_changed_files(branch=effective_branch)
        if not changed:
            result["success"] = True
            result["error"] = "No changes to commit"
            return result
        
        try:
            # Build the new tree by updating the index
            head_ref = repo.references.get(f"refs/heads/{effective_branch}")
            if head_ref is None:
                result["error"] = f"Branch {effective_branch} not found"
                return result
            
            head_commit = head_ref.peel(pygit2.Commit)
            
            # Create index from HEAD tree
            index = pygit2.Index()
            index.read_tree(head_commit.tree)
            
            # Update changed files in the index
            for file_path in changed:
                local_path = self.work_tree / file_path
                if local_path.exists():
                    # Read file and create blob
                    content = local_path.read_bytes()
                    blob_id = repo.create_blob(content)
                    
                    # Add to index
                    entry = pygit2.IndexEntry(file_path, blob_id, pygit2.GIT_FILEMODE_BLOB)
                    index.add(entry)
                else:
                    # File was deleted
                    try:
                        index.remove(file_path)
                    except KeyError:
                        pass
            
            # Write the tree
            tree_id = index.write_tree(repo)
            
            # Create the commit
            author = repo.default_signature
            committer = repo.default_signature
            
            parent = head_commit.id
            commit_id = repo.create_commit(
                f"refs/heads/{effective_branch}",
                author,
                committer,
                message,
                tree_id,
                [parent]
            )
            
            result["committed"] = True
            logger.info(f"Created commit {str(commit_id)[:7]}")
            
        except Exception as e:
            result["error"] = f"Commit failed: {e}"
            return result
        
        # Push to remote using git subprocess (handles credentials properly)
        try:
            push_result = subprocess.run(
                ["git", "--git-dir", str(self.dotfiles_dir), 
                 "push", "origin", effective_branch],
                capture_output=True,
                text=True,
                timeout=60
            )
            if push_result.returncode == 0:
                result["pushed"] = True
                result["success"] = True
                logger.info(f"Pushed to origin/{effective_branch}")
            else:
                result["error"] = f"Push failed: {push_result.stderr.strip()}"
                logger.error(result["error"])
        except subprocess.TimeoutExpired:
            result["error"] = "Push timed out"
            logger.error(result["error"])
        except Exception as e:
            result["error"] = f"Push failed (changes committed locally): {e}"
            logger.error(result["error"])
        
        return result

    def force_checkout(self):
        """Discard local changes and update to match remote.
        
        Fetches latest from remote, resets to remote branch,
        and force-checkouts files to work tree.
        """
        repo = self._get_repo()
        
        # Fetch first
        logger.info("Fetching latest from remote...")
        self._fetch()
        
        # Resolve the actual branch to use
        branch_info = self._resolve_branch()
        effective_branch = branch_info["effective"]
        
        # Get remote commit
        remote_ref = repo.references.get(f"refs/remotes/origin/{effective_branch}")
        if remote_ref is None:
            raise RuntimeError(f"Remote branch origin/{effective_branch} not found")
        
        remote_commit = remote_ref.peel(pygit2.Commit)
        
        # Update local branch to point to remote
        repo.references.create(f"refs/heads/{effective_branch}", remote_commit.id, force=True)
        
        # Force checkout
        logger.info("Discarding local changes and updating to remote...")
        self._checkout_to_worktree(force=True)
