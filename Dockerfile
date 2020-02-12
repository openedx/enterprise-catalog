FROM python:3.5 as app

WORKDIR /edx/app/enterprise_catalog/enterprise_catalog
ADD requirements.txt /edx/app/enterprise_catalog/enterprise_catalog/
ADD Makefile /edx/app/enterprise_catalog/enterprise_catalog/
ADD requirements/ /edx/app/enterprise_catalog/enterprise_catalog/requirements/
RUN make requirements

EXPOSE 8160 
RUN useradd -m --shell /bin/false app
USER app

CMD gunicorn -c /edx/app/enterprise_catalog/docker_gunicorn_config.py enterprise_catalog.wsgi:application
ADD . /edx/app/enterprise_catalog

FROM app as worker
CMD celery worker -A enterprise_catalog --app enterprise_catalog.celery:app --loglevel=info --queue=enterprise_catalog.default --hostname=enterprise_catalog.enterprise_catalog.default.%h --concurrency=1
