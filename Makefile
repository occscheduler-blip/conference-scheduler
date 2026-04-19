.PHONY: test test-frontend test-backend

test: test-frontend test-backend

test-frontend:
	npm test

test-backend:
	$(MAKE) -C backend test
