# Contributing to s3hop

Thank you for your interest in contributing to s3hop! This document provides guidelines and instructions for contributing to the project and publishing new releases.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/hamsti/s3hop.git
cd s3hop
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
pip install build twine
```

## Development Workflow

1. Create a new branch for your feature/fix:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and ensure they follow the project's coding style
3. Write/update tests if necessary
4. Run tests and ensure they pass
5. Commit your changes with clear, descriptive commit messages
6. Push your branch and create a Pull Request

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise
- Add comments for complex logic

## Testing

1. Run tests:
```bash
python -m pytest tests/
```

2. Check code coverage:
```bash
python -m pytest --cov=s3hop tests/
```

## Publishing to PyPI (for maintainers)

### Prerequisites
1. You need maintainer access to the PyPI project
2. Create a PyPI account if you don't have one
3. Install required tools:
```bash
pip install build twine
```

### Publishing Process

1. Update version number in:
   - `s3hop/__init__.py`
   - `setup.py`

2. Create a new git tag:
```bash
git tag v0.1.0  # Replace with your version
git push origin v0.1.0
```

3. Build the distribution packages:
```bash
python -m build
```

4. Test the build on TestPyPI first:
```bash
python -m twine upload --repository testpypi dist/*
```

5. Test the installation from TestPyPI:
```bash
pip install --index-url https://test.pypi.org/simple/ s3hop
```

6. If everything works, upload to PyPI:
```bash
python -m twine upload dist/*
```

### Version Numbering

We follow semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: Incompatible API changes
- MINOR: Add functionality in a backward-compatible manner
- PATCH: Backward-compatible bug fixes

## Release Checklist

Before releasing a new version:

1. [ ] Update version numbers
2. [ ] Update CHANGELOG.md
3. [ ] Ensure all tests pass
4. [ ] Update documentation if needed
5. [ ] Create and push git tag
6. [ ] Build distribution packages
7. [ ] Test on TestPyPI
8. [ ] Publish to PyPI
9. [ ] Create GitHub release

## Getting Help

If you need help or have questions:
1. Check existing issues on GitHub
2. Create a new issue with a clear description
3. Tag it appropriately (bug, enhancement, question, etc.)

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Follow the golden rule

## License

By contributing, you agree that your contributions will be licensed under the MIT License. 