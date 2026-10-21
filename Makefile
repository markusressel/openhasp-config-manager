
setup:
	pyenv install 3.13
	pyenv local 3.13
	poetry install

format:
	poetry run ruff format .

lint:
	# --fix automatically fixes lint violations (like unused imports)
	# --unsafe-fixes allows ruff to fix things that might change code behavior
	poetry run ruff check . --fix

test:
	cd tests && poetry run pytest

# the tests of the haad integration (tests/haad) need haad and Python 3.14: they run in haad's environment
test-haad:
	PYTHONPATH=../haad uv run --project ../haad pytest tests/haad --cov=openhasp_config_manager/haad --cov-branch --cov-report=term-missing --cov-fail-under=100

docker-latest:
	docker build . --file Dockerfile --tag ghcr.io/markusressel/openhasp-config-manager:latest

install-release:
	rm -rf /tmp/venv-install
	git clone https://github.com/markusressel/venv-install /tmp/venv-install
	cd /tmp/venv-install && ./install.sh
	venv-install openhasp-config-manager openhasp-config-manager
	openhasp-config-manager -h

uninstall-release:
	venv-uninstall openhasp-config-manager openhasp-config-manager

