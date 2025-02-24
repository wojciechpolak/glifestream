ARG python=python:3.12-slim-bookworm

FROM ${python} AS gls-builder-python
RUN apt update -y
RUN apt install -y gcc g++
RUN apt-get clean
WORKDIR /app
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
RUN pip install --no-cache-dir poetry==1.7.1
COPY pyproject.toml .
COPY poetry.lock .
RUN poetry config virtualenvs.create false
RUN poetry config installer.max-workers 10
RUN poetry install --no-dev -n

FROM ${python}
RUN apt update -y
RUN apt install -y cron curl gettext procps
RUN pip install --no-cache-dir supervisor
RUN apt-get clean
RUN echo 'alias ll="ls -l"' >>~/.bashrc
RUN mkdir /app /app/run
COPY --from=gls-builder-python /venv /venv
ENV PATH=/venv/bin:$PATH
ENV DJANGO_SETTINGS_MODULE=run.settings_docker
WORKDIR /app
COPY conf/docker/entrypoint.sh .
ADD run run
ADD locale locale
ADD glifestream glifestream
COPY manage.py .
COPY worker.py .
RUN usermod -a -G users www-data
RUN chgrp -R users /app/glifestream/static && chmod -R g+w /app/glifestream/static
RUN python manage.py compilemessages
ENV PYTHONPATH="${PYTHONPATH}:/app"
EXPOSE 80
COPY conf/docker/etc/supervisord.conf /etc/supervisord.conf

COPY conf/docker/etc/cron.d/ /etc/cron.d/
RUN touch /var/log/cron.log
RUN chmod 0644 /etc/cron.d/glifestream
RUN crontab /etc/cron.d/glifestream

HEALTHCHECK --interval=60m --timeout=3s CMD curl -f http://localhost/ || exit 1
CMD /app/entrypoint.sh
