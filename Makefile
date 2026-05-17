.PHONY: install install-pi dev test lint typecheck deploy pi-shell pi-install check-hardware calibrate-servos calibrate-workspace measure-arm

PI_HOST ?= rpclaw@UMDCLAW.local

install:
	uv sync --extra dev

install-pi:
	uv sync --extra dev --extra hardware

dev:
	uv run uvicorn claw_companion.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

lint:
	uv run ruff check src tests scripts

typecheck:
	uv run mypy src

deploy:
	bash deploy.sh

pi-shell:
	ssh $(PI_HOST)

pi-install:
	ssh $(PI_HOST) "cd ~/claw-companion && uv sync --extra dev --extra hardware"

check-hardware:
	ssh $(PI_HOST) "cd ~/claw-companion && uv run python scripts/check_hardware.py"

calibrate-servos:
	ssh -t $(PI_HOST) "cd ~/claw-companion && uv run python scripts/calibrate_servos.py"

calibrate-workspace:
	ssh -t $(PI_HOST) "cd ~/claw-companion && uv run python scripts/calibrate_workspace.py"

measure-arm:
	ssh -t $(PI_HOST) "cd ~/claw-companion && uv run python scripts/measure_arm.py"
