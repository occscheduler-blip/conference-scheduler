PYTEST   := .venv/bin/pytest
MYPY     := .venv/bin/mypy
SUPABASE := $(shell which supabase)

.PHONY: supabase-start supabase-migrate test

# Start local Supabase Docker containers (idempotent — safe to run if already running).
supabase-start:
	$(SUPABASE) start

# Apply any pending migrations to the local database.
supabase-migrate:
	$(SUPABASE) migration up

test:
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "Missing backend test runner at $(PYTEST)"; \
		echo "Create backend venv and install dependencies first."; \
		exit 1; \
	fi
	@nc -z 127.0.0.1 54321 2>/dev/null || ($(MAKE) supabase-start && $(MAKE) supabase-migrate)
	$(MYPY) app
	$(PYTEST) -q tests
