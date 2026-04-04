ARG python=python:3.14-slim-trixie
ARG TARGETARCH

FROM ${python} AS gls-builder-python
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG TARGETARCH
ENV TARGETARCH=${TARGETARCH:-amd64}

WORKDIR /app
ENV UV_NO_DEV=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv,id=uv-${TARGETARCH} \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

COPY pyproject.toml .
COPY uv.lock .
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-${TARGETARCH} \
    uv sync --locked --no-editable

FROM ${python}
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron curl gettext procps \
    && pip install --no-cache-dir supervisor \
    && rm -rf /var/lib/apt/lists/*
RUN echo 'alias ll="ls -l"' >>~/.bashrc
RUN mkdir -p /app/run/db /app/run/static/themes /app/run/templates /app/media /app/static
COPY --from=gls-builder-python --chown=app:app /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH
ENV DJANGO_SETTINGS_MODULE=run.settings_docker
WORKDIR /app
COPY conf/docker/entrypoint.sh .
COPY run/__init__.py run/settings_docker.py run/
COPY locale locale
COPY glifestream glifestream
COPY manage.py .
COPY worker.py .
RUN usermod -a -G users www-data
RUN chgrp -R users /app/glifestream/static && chmod -R g+w /app/glifestream/static
RUN python manage.py compilemessages
EXPOSE 80
COPY conf/docker/etc/supervisord.conf /etc/supervisord.conf

COPY conf/docker/etc/cron.d/ /etc/cron.d/
RUN touch /var/log/cron.log
RUN chmod 0644 /etc/cron.d/glifestream
RUN crontab /etc/cron.d/glifestream

HEALTHCHECK --interval=60m --timeout=3s CMD curl -f http://localhost/ || exit 1
CMD ["/app/entrypoint.sh"]
