
docker-latest:
	docker build . --file Dockerfile --tag ghcr.io/markusressel/openhasp-config-manager:latest

install:
	rm -rf /tmp/venv-install
	git clone https://github.com/markusressel/venv-install /tmp/venv-install
	cd /tmp/venv-install && ./install.sh
	venv-install openhasp-config-manager openhasp-config-manager
	openhasp-config-manager -h

uninstall:
	venv-uninstall openhasp-config-manager openhasp-config-manager

