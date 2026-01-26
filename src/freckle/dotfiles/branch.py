"""Branch resolution logic for git repositories."""

from typing import Callable, List, Optional

from .types import BranchInfo


class BranchResolver:
    """Resolves which git branch to use with intelligent fallbacks.

    Handles common scenarios like main/master swapping and missing branches.
    """

    def __init__(
        self,
        configured_branch: str,
        get_available: Callable[[], List[str]],
        get_head: Callable[[], Optional[str]],
    ):
        """Initialize the branch resolver.

        Args:
            configured_branch: The branch name from configuration
            get_available: Callback to get list of available branches
            get_head: Callback to get current HEAD branch name
        """
        self.configured = configured_branch
        self._get_available = get_available
        self._get_head = get_head

    def resolve(self) -> BranchInfo:
        """Resolve which branch to use, with detailed context.

        Returns a dict with:
        - effective: The branch to actually use
        - configured: The originally configured branch
        - reason: Why this branch was chosen
        - available: List of available branches
        - message: Human-readable explanation (None if exact match)
        """
        available = self._get_available()

        # Check if configured branch exists
        if self.configured in available:
            return self._result(
                effective=self.configured,
                reason="exact",
                available=available,
                message=None,
            )

        # Common main/master swap
        swap_map = {"main": "master", "master": "main"}
        if self.configured in swap_map:
            swapped = swap_map[self.configured]
            if swapped in available:
                return self._result(
                    effective=swapped,
                    reason="main_master_swap",
                    available=available,
                    message=(
                        f"Branch '{self.configured}' not found; "
                        f"using '{swapped}' instead."
                    ),
                )

        # Try HEAD
        head_branch = self._get_head()
        if head_branch and head_branch in available:
            return self._result(
                effective=head_branch,
                reason="fallback_head",
                available=available,
                message=(
                    f"Branch '{self.configured}' not found; "
                    f"using current HEAD '{head_branch}'."
                ),
            )

        # Try common defaults
        for fallback in ["main", "master"]:
            if fallback in available:
                return self._result(
                    effective=fallback,
                    reason="fallback_default",
                    available=available,
                    message=(
                        f"Branch '{self.configured}' not found; "
                        f"falling back to '{fallback}'."
                    ),
                )

        # Nothing found - return configured as-is
        branches = ", ".join(available) or "(none)"
        return self._result(
            effective=self.configured,
            reason="not_found",
            available=available,
            message=(
                f"Branch '{self.configured}' not found. "
                f"Available: {branches}"
            ),
        )

    def _result(
        self,
        effective: str,
        reason: str,
        available: List[str],
        message: Optional[str],
    ) -> BranchInfo:
        """Build a resolution result dict."""
        result: BranchInfo = {
            "effective": effective,
            "configured": self.configured,
            "reason": reason,
        }
        if message is not None:
            result["message"] = message
        return result
