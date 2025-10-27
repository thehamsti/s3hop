# Repository Guidelines

## Project Structure & Module Organization
- `s3hop/` holds the package code; `core.py` contains transfer logic and `cli.py` exposes the command-line entrypoints. Keep helper modules colocated here.
- `tests/unit/` mirrors the package layout with pytest modules such as `test_core.py` and `test_cli.py`. Add new tests alongside the code they cover.
- `setup.cfg` centralizes lint, formatting, and mypy settings. Update it when introducing project-wide tooling changes.
- `build/` and `s3hop.egg-info/` are build artifacts; leave them untouched in commits.

## Build, Test, and Development Commands
- `pip install -e .` performs an editable install for local development.
- `python -m build` (requires `pip install build`) produces wheels and source dists under `dist/`.
- `pytest -vv` runs the full test suite; add `--cov=s3hop --cov-report=term-missing` to inspect coverage gaps.
- `black .` and `isort .` auto-format imports and code; run before committing.
- `flake8 .` and `mypy s3hop` enforce linting and typing gates.

## Coding Style & Naming Conventions
- Follow Black formatting with 100-character lines, 4-space indentation, and trailing commas where valid.
- Import order is standard library, third-party, then local modules, each group separated by one blank line.
- Public callables require Google-style docstrings and complete type hints; avoid `Any` unless justified.
- Use `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_SNAKE` for constants.

## Testing Guidelines
- Write pytest tests that describe behavior; name files `test_*.py` and functions `test_<feature>`.
- Aim to keep coverage high; new features should not lower existing branch coverage reported by `--cov`.
- Exercise CLI paths via `click.testing.CliRunner` helpers in `test_cli.py`.

## Commit & Pull Request Guidelines
- Craft concise, present-tense commit subjects (e.g., `Fix upload chunk size`) and include issue references like `(#123)` when applicable.
- Each PR should summarize behavior changes, note validation steps (commands run), and attach screenshots for CLI output changes when useful.
- Ensure lint, type checks, and tests pass locally before requesting review.

## Security & Configuration Tips
- Never commit credentials or AWS configuration files; rely on environment variables or local profiles outside the repo.
- Review `s3hop/core.py` for network or S3 parameter changes and document new configuration flags in `README.md`.
