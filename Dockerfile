# dont use alpine for python builds: https://pythonspeed.com/articles/alpine-docker-python/
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION="2.1.2"
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV VENV_HOME=/opt/poetry
WORKDIR /app

COPY README.md README.md
COPY openhasp_config_manager openhasp_config_manager
COPY poetry.lock pyproject.toml ./

RUN apt-get update \
 && apt-get -y install python3-pip \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv ${VENV_HOME} \
 && ${VENV_HOME}/bin/pip install --upgrade pip \
 && ${VENV_HOME}/bin/pip install "poetry==${POETRY_VERSION}" \
 && ${VENV_HOME}/bin/poetry check \
 && POETRY_VIRTUALENVS_CREATE=false ${VENV_HOME}/bin/poetry install --no-interaction --no-cache --without dev \
 && ${VENV_HOME}/bin/pip uninstall -y poetry

# Add Poetry to PATH
ENV PATH="${VENV_HOME}/bin:${PATH}"

RUN ${VENV_HOME}/bin/pip install .

ENTRYPOINT [ "openhasp-config-manager" ]

