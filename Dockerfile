FROM python:3.5

WORKDIR /edx/app/enterprise_catalog/enterprise_catalog
ADD requirements.txt /edx/app/enterprise_catalog/enterprise_catalog/
ADD Makefile /edx/app/enterprise_catalog/enterprise_catalog/
ADD requirements/ /edx/app/enterprise_catalog/enterprise_catalog/requirements/
RUN make requirements

EXPOSE 8160 
RUN useradd -m --shell /bin/false app
USER app

CMD gunicorn --bind=0.0.0.0:8160 --workers 2 --max-requests=1000 -c /edx/app/enterprise_catalog/docker_gunicorn_config.py enterprise_catalog.wsgi:application
ADD . /edx/app/enterprise_catalog

FROM app as edx.org
CMD celery worker -A enterprise_catalog --app enterprise_catalog.celery:app --loglevel=info --queue=enterprise_catalog.default --hostname=enterprise_catalog.enterprise_catalog.default.%h --concurrency=1
