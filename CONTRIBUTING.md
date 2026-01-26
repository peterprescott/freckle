# Contributing to freckle

Thank you for your interest in contributing to freckle! This document provides
guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- git

### Getting Started

1. Clone the repository:

```bash
git clone https://github.com/peterprescott/freckle.git
cd freckle
```

2. Install dependencies:

```bash
uv sync --all-groups
```

3. Verify your setup:

```bash
uv run freckle --version
uv run pytest tests/unit -q
```

## Project Structure

```
src/freckle/
├── cli/              # CLI commands (one module per command)
│   ├── profile/      # Profile subpackage (create, delete, operations)
│   └── ...
├── dotfiles/         # Core dotfiles management
│   ├── manager.py    # High-level operations
│   ├── repo.py       # Git repository operations
│   └── types.py      # TypedDict definitions
├── backup.py         # Restore point management
├── config.py         # Configuration parsing
├── secrets.py        # Secret detection
└── tools_registry.py # Tool installation
```

## Code Style

- **Line length**: 79 characters (enforced by ruff)
- **Formatting**: Managed by ruff
- **Type hints**: Required for all public functions
- **Docstrings**: Required for modules, classes, and public functions

### Running Linters

```bash
# Check for issues
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/

# Type checking
uv run ty check src/
```

## Testing

### Test Structure

```
tests/
├── unit/         # Fast, isolated unit tests
├── integration/  # Tests with file system / subprocess
└── e2e/          # Full end-to-end CLI tests
```

**Coverage approach:**
- Core library (`src/freckle/`): Measured via pytest-cov
- CLI modules (`src/freckle/cli/`): Tested via E2E tests (excluded from coverage stats)

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only (fast)
uv run pytest tests/unit

# With coverage report
uv run pytest tests/unit tests/integration --cov=freckle --cov-report=term-missing

# E2E tests only
uv run pytest tests/e2e

# Specific test file
uv run pytest tests/unit/test_config.py -v
```

### Test Categories

**Unit tests** (`tests/unit/`):
- Test individual functions and classes in isolation
- Mock external dependencies (git, file system, package managers)
- Fast execution, run frequently during development

**Integration tests** (`tests/integration/`):
- Test interactions between components
- May use real file system with `tmp_path`
- Still mock external tools like git

**E2E tests** (`tests/e2e/`):
- Test complete CLI workflows
- Run actual `freckle` commands via subprocess
- Use temporary home directories to isolate from real system
- Cover all CLI commands

### Writing Tests

- Use `tmp_path` fixture for file system operations
- Mock external dependencies (git, package managers) in unit tests
- Test both success and error paths
- Keep tests focused and independent
- For CLI commands, add E2E tests in `tests/e2e/test_cli_commands.py`

## Pull Request Process

1. **Create a branch** from `dev`:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/your-feature-name
```

2. **Make your changes**:
   - Write tests for new functionality
   - Update documentation if needed
   - Follow the code style guidelines

3. **Verify your changes**:

```bash
uv run ruff check src/ tests/
uv run ty check src/
uv run pytest
```

4. **Commit with a clear message**:

```bash
git commit -m "feat: add support for feature X

- Added new module for X
- Updated config parsing
- Added tests for X"
```

5. **Push and create PR**:

```bash
git push -u origin feature/your-feature-name
```

Then create a pull request against the `dev` branch.

## Commit Message Guidelines

Use conventional commit format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `ci:` CI/CD changes

## Architecture Notes

### CLI Commands

Each command is a separate module in `src/freckle/cli/`. Commands:

1. Define a `register(app)` function to add themselves to the main app
2. Use `typer` for argument parsing
3. Import helpers from `cli/helpers.py`

### Dotfiles Management

The `dotfiles/` package handles git operations:

- `BareGitRepo`: Low-level git commands
- `DotfilesManager`: High-level operations (sync, backup, etc.)
- Uses "bare repository with work tree" pattern

### Configuration

- Config file: `~/.freckle.yaml`
- `CONFIG_PATH` constant in `cli/helpers.py`
- `Config` class handles loading and variable substitution

## Questions?

Open an issue on GitHub if you have questions or need help.
