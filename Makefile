
setup:
	pyenv install 3.13
	pyenv local 3.13
	poetry install

test:
	cd tests && poetry run pytest

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

