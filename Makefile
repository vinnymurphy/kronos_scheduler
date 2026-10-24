# JobSearch Project Automation
VENV       := venv
BIN        := $(VENV)/bin
PYTHON     := $(BIN)/python3

BACKUP_DIR := backups
DJLINT     := $(BIN)/djlint
MANAGE     := $(PYTHON) manage.py
PIP        := $(BIN)/pip
RUFF       := $(BIN)/ruff
TIMESTAMP  := $(shell date +%F_%H%M%S)

.PHONY: all backup clean format help install lint manage migrate restore run setup shell test
help:
	@echo "Available commands:"
	@echo "  make backup   - Export database to timestamped JSON"
	@echo "  make check    - Run format, test, and backup"
	@echo "  make clean    - Remove __pycache__ and build artifacts"
	@echo "  make format   - Run formatters and auto-fix lint issues"
	@echo "  make lint     - Run lint checks"
	@echo "  make manage ARGS='COMMAND [OPTIONS]' - Run a Django management command"
	@echo "  make migrate  - Generate and apply database migrations"
	@echo "  make restore  - Load data from the most recent backup file"
	@echo "  make run      - Start the Django development server"
	@echo "  make setup    - Create venv and install dependencies"
	@echo "  make shell    - Open the Django interactive shell"
	@echo "  make test     - Run the test suite (Performance & Logic)"


setup:
	@echo "[INFO] Initializing Virtual Environment..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "[SUCCESS] Environment ready. Run 'make migrate' next."

migrate:
	$(MANAGE) makemigrations
	$(MANAGE) migrate

run:
	$(MANAGE) runserver


test:
	$(MANAGE) test -v 2 scoring

shell:
	$(MANAGE) shell $(ARGS)

manage:
	$(MANAGE) $(ARGS)

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	find . -name "*~" -delete

backup:
	@mkdir -p $(BACKUP_DIR)
	@echo "----------------------------------------------------------------"
	@echo "BUILD STATUS: Exporting JobSearch data..."
	@echo "TARGET: $(BACKUP_DIR)/db_backup_$(TIMESTAMP).json"
	@$(MANAGE) dumpdata --indent 2 --exclude auth.permission --exclude contenttypes > $(BACKUP_DIR)/db_backup_$(TIMESTAMP).json
	@echo "RESULT: Backup completed successfully at $(shell date)."
	@echo "----------------------------------------------------------------"

restore:
	@echo "----------------------------------------------------------------"
	@echo "BUILD STATUS: Restoring latest data state..."
	@$(MANAGE) loaddata $(shell ls -t $(BACKUP_DIR)/*.json | head -1)
	@echo "RESULT: Database synchronized with $(shell ls -t $(BACKUP_DIR)/*.json | head -1)"
	@echo "----------------------------------------------------------------"


format:
	@echo "----------------------------------------------------------------"
	@echo "BUILD STATUS: Formatting with $(RUFF)..."
	@$(RUFF) format .
	@$(RUFF) check --fix .
	@echo "BUILD STATUS: Formatting with $(DJLINT)..."
	@$(DJLINT) . --reformat
	@echo "RESULT: Codebase formatted and auto-fixed."
	@$(BIN)/isort .
	@echo "RESULT: Imports sorted with isort."
	@$(BIN)/black .
	@echo "RESULT: Codebase formatted with Black."
	@echo "----------------------------------------------------------------"

lint:
	@echo "----------------------------------------------------------------"
	@echo "BUILD STATUS: Linting with $(RUFF)..."
	@$(RUFF) check .
	@echo "RESULT: Linting complete."
	@echo "----------------------------------------------------------------"
	@echo "BUILD STATUS: Linting with $(DJLINT)..."
	@$(DJLINT) . --check
	@echo "RESULT: Linting complete."
	@echo "----------------------------------------------------------------"

# The "Safety Suite" - Run everything in one go
check: format test backup
	@echo "----------------------------------------------------------------"
	@echo "PIPELINE STATUS: ALL CHECKS PASSED"
	@echo "----------------------------------------------------------------"
