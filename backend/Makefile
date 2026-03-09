PYTEST := .venv/bin/pytest
MYPY  := .venv/bin/mypy

.PHONY: test
test:
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "Missing backend test runner at $(PYTEST)"; \
		echo "Create backend venv and install dependencies first."; \
		exit 1; \
	fi
	$(MYPY) app
	$(PYTEST) -q tests
