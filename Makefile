IMAGE_NAME = "http-segmentation"
build:
	docker build -t $(IMAGE_NAME) .

BIN = .venv/bin
PY = ${BIN}/python -B
PIP_INSTALL = ${BIN}/pip install
venv: .venv/touchfile ## Create Python virtual environment and install dependencies

.venv/touchfile: requirements.txt requirements_dev.txt
	[ -d .venv ] || python3 -m venv .venv
	${PIP_INSTALL} --upgrade pip wheel
	${PIP_INSTALL} -r requirements.txt
	${PIP_INSTALL} -r requirements_dev.txt
	touch .venv/touchfile

clean_venv:
	[ -d .venv ] && rm -rf .venv

FORMAT_DIRS = .
format: venv
	${BIN}/ruff format ${FORMAT_DIRS}

format_check: venv
	${BIN}/ruff format --check ${FORMAT_DIRS}

LINT_DIRS = .
lint: venv ## Lint codebase with Ruff
	${BIN}/ruff ${LINT_DIRS}

lint_fix: venv ## Lint codebase with Ruff and fix issues automatically
	${BIN}/ruff --fix ${LINT_DIRS}

include .env
run: venv ## Run application
	${BIN}/uvicorn --reload main:app
