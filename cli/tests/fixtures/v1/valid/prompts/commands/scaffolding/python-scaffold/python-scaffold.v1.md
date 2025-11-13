# Python Project Scaffold Command

Create a new Python project with best practices:

1. Initialize project structure:
   ```
   project_name/
   ├── src/project_name/
   │   ├── __init__.py
   │   └── main.py
   ├── tests/
   │   └── __init__.py
   ├── pyproject.toml
   ├── README.md
   ├── .gitignore
   └── LICENSE
   ```

2. Configure pyproject.toml with:
   - Project metadata
   - Dependencies
   - Development dependencies (pytest, black, mypy, ruff)
   - Build system configuration

3. Create README.md with:
   - Project description
   - Installation instructions
   - Usage examples
   - Development setup

4. Add .gitignore for Python projects
5. Initialize git repository
6. Set up pre-commit hooks

Use modern Python tooling (uv, ruff) where possible.

