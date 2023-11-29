FROM ubuntu:focal as app
MAINTAINER sre@edx.org

# Packages installed:
# git
#     Used to pull in particular requirements from github rather than pypi,
#     and to check the sha of the code checkout.
# language-pack-en locales
#     ubuntu locale support so that system utilities have a consistent
#     language and time zone.
# python3.5
#     ubuntu doesnt ship with python, so this is the python we will use to run the
#     application
# python3-pip
#     install pip to install application requirements.txt files
# pkg-config
#     mysqlclient>=2.2.0 requires this (https://github.com/PyMySQL/mysqlclient/issues/620)
# libssl-dev
#     mysqlclient wont install without this.
# libmysqlclient-dev
#     to install header files needed to use native C implementation for
#     MySQL-python for performance gains.

# If you add a package here please include a comment above describing what it is used for
RUN apt-get update && apt-get -qy install --no-install-recommends \
 language-pack-en \
 locales \
 python3.8 \
 python3-pip \
 python3.8-venv \
 python3.8-dev \
 pkg-config \
 libmysqlclient-dev \
 libssl-dev \
 build-essential \
 git \
 wget

ENV VIRTUAL_ENV=/venv
RUN python3.8 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install pip==20.2.3 setuptools==50.3.0

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV DJANGO_SETTINGS_MODULE enterprise_access.settings.production

# Prod ports
EXPOSE 8160
EXPOSE 8161

RUN useradd -m --shell /bin/false app

WORKDIR /edx/app/enterprise_catalog/enterprise_catalog

COPY requirements/ /edx/app/enterprise_catalog/enterprise_catalog/requirements/
RUN pip install -r /edx/app/enterprise_catalog/enterprise_catalog/requirements/production.txt

# Code is owned by root so it cannot be modified by the application user.
# So we copy it before changing users.
USER app

# Gunicorn 19 does not log to stdout or stderr by default. Once we are past gunicorn 19, the logging to STDOUT need not be specified.
CMD ["gunicorn", "--workers=2", "--name", "enterprise_catalog", "-c", "/edx/app/enterprise_catalog/enterprise_catalog/enterprise_catalog/docker_gunicorn_configuration.py", "--log-file", "-", "--max-requests=1000", "enterprise_catalog.wsgi:application"]

# This line is after the requirements so that changes to the code will not
# bust the image cache
COPY . /edx/app/enterprise_catalog/enterprise_catalog

###############################################################
# Create newrelic image used by the experimental docker shim. #
###############################################################
# TODO: remove this after we migrate to k8s since it will serve no more purpose.
FROM app as newrelic
RUN pip install newrelic
CMD ["newrelic-admin", "run-program", "gunicorn", "--workers=2", "--name", "enterprise_catalog", "-c", "/edx/app/enterprise_catalog/enterprise_catalog/enterprise_catalog/docker_gunicorn_configuration.py", "--log-file", "-", "--max-requests=1000", "enterprise_catalog.wsgi:application"]

#################################
# Create image used by devstack #
#################################
# TODO: remove this after we migrate to k8s.  It already isn't used today, but just defer changes until absolutely
# necessary for safety.
FROM app as legacy_devapp
# Dev ports
EXPOSE 18160
EXPOSE 18161
USER root
RUN pip install -r /edx/app/enterprise_catalog/enterprise_catalog/requirements/dev.txt
USER app
CMD ["gunicorn", "--reload", "--workers=2", "--name", "enterprise_catalog", "-b", ":18160", "-c", "/edx/app/enterprise_catalog/enterprise_catalog/enterprise_catalog/docker_gunicorn_configuration.py", "--log-file", "-", "--max-requests=1000", "enterprise_catalog.wsgi:application"]
