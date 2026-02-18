PYTEST := .venv/bin/pytest

.PHONY: test
test:
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "Missing backend test runner at $(PYTEST)"; \
		echo "Create backend venv and install dependencies first."; \
		exit 1; \
	fi
	$(PYTEST) -q tests
