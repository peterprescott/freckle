"""Unit tests for BranchResolver."""

from freckle.dotfiles import BranchResolver


def test_exact_match():
    """Test that exact branch match returns the configured branch."""
    resolver = BranchResolver(
        configured_branch="main",
        get_available=lambda: ["main", "dev"],
        get_head=lambda: "main",
    )
    result = resolver.resolve()
    assert result["effective"] == "main"
    assert result["reason"] == "exact"
    assert result["message"] is None


def test_main_master_swap():
    """Test fallback from main to master."""
    resolver = BranchResolver(
        configured_branch="main",
        get_available=lambda: ["master", "dev"],
        get_head=lambda: "master",
    )
    result = resolver.resolve()
    assert result["effective"] == "master"
    assert result["reason"] == "main_master_swap"
    assert "main" in result["message"]
    assert "master" in result["message"]


def test_master_main_swap():
    """Test fallback from master to main."""
    resolver = BranchResolver(
        configured_branch="master",
        get_available=lambda: ["main", "dev"],
        get_head=lambda: "main",
    )
    result = resolver.resolve()
    assert result["effective"] == "main"
    assert result["reason"] == "main_master_swap"


def test_fallback_to_head():
    """Test fallback to HEAD when configured branch not found."""
    resolver = BranchResolver(
        configured_branch="feature-branch",
        get_available=lambda: ["develop", "release"],
        get_head=lambda: "develop",
    )
    result = resolver.resolve()
    assert result["effective"] == "develop"
    assert result["reason"] == "fallback_head"


def test_fallback_to_main():
    """Test fallback to main when nothing else matches."""
    resolver = BranchResolver(
        configured_branch="nonexistent",
        get_available=lambda: ["main", "other"],
        get_head=lambda: None,
    )
    result = resolver.resolve()
    assert result["effective"] == "main"
    assert result["reason"] == "fallback_default"


def test_not_found():
    """Test when no suitable branch can be found."""
    resolver = BranchResolver(
        configured_branch="feature",
        get_available=lambda: ["dev", "staging"],
        get_head=lambda: None,
    )
    result = resolver.resolve()
    assert result["effective"] == "feature"  # Returns configured as-is
    assert result["reason"] == "not_found"
    assert "dev" in result["message"]
    assert "staging" in result["message"]


def test_empty_available():
    """Test when no branches are available."""
    resolver = BranchResolver(
        configured_branch="main",
        get_available=lambda: [],
        get_head=lambda: None,
    )
    result = resolver.resolve()
    assert result["effective"] == "main"
    assert result["reason"] == "not_found"
    assert "(none)" in result["message"]
