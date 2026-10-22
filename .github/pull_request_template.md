## Summary

Describe the problem, the change, and why this approach was chosen.

## Validation

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy app tests evals migrations`
- [ ] `uv run pytest -q`
- [ ] Frontend checks, if applicable
- [ ] Integration or browser E2E checks, if applicable

List the commands run and any checks that could not be run.

## Risk

- [ ] No secrets, personal data, internal endpoints, or production data are
  included.
- [ ] Public behavior, configuration, migrations, and deployment changes are
  documented.
- [ ] Security, authorization, and data-isolation implications were reviewed.

## Notes

Add known limitations, rollout notes, or follow-up work here.
