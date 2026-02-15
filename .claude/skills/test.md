# Test Runner Skill

Run pytest for the openapi-mcp-bridge project.

## Usage
- `/test` - Run all tests
- `/test <path>` - Run specific test file or directory

## Instructions

When this skill is invoked:

1. **If no arguments provided**: Run all tests with `pytest tests/ -v`
2. **If path argument provided**: Run `pytest <path> -v`

### Commands to execute:

```bash
# Activate venv and run pytest
.venv/bin/pytest ${ARGS:-tests/} -v --tb=short
```

### On failure:
- Show the failed test output
- Suggest fixes based on the error messages

### On success:
- Show summary of passed tests
- Report test coverage if available
