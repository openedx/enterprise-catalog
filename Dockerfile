FROM ubuntu:focal as app
MAINTAINER sre@edx.org

# Packages installed:
# git
#     Used to pull in particular requirements from github rather than pypi,
#     and to check the sha of the code checkout.
# language-pack-en locales
#     ubuntu locale support so that system utilities have a consistent
#     language and time zone.
# python3-pip
#     install pip to install application requirements.txt files
# pkg-config
#     mysqlclient>=2.2.0 requires this (https://github.com/PyMySQL/mysqlclient/issues/620)
# libssl-dev
#     mysqlclient wont install without this.
# libmysqlclient-dev
#     to install header files needed to use native C implementation for
#     MySQL-python for performance gains.

ARG PYTHON_VERSION=3.12
ENV TZ=UTC
ENV TERM=xterm-256color
ENV DEBIAN_FRONTEND=noninteractive

# If you add a package here please include a comment above describing what it is used for
RUN apt-get update && \
  apt-get install -y software-properties-common && \
  apt-add-repository -y ppa:deadsnakes/ppa

RUN apt-get update && apt-get -qy install --no-install-recommends \
 build-essential \
 language-pack-en \
 locales \
 pkg-config \
 libmysqlclient-dev \
 libssl-dev \
 libffi-dev \
 libsqlite3-dev \
 git \
 wget \
 python3.12 \
 python3.12-dev \
 python3.12-distutils \
 python3-pip

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VERSION}
RUN pip install virtualenv

ENV VIRTUAL_ENV=/venv
RUN virtualenv -p python$PYTHON_VERSION -m $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install pip==24.0 setuptools==69.5.1

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV DJANGO_SETTINGS_MODULE enterprise_catalog.settings.production

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
