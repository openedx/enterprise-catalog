FROM python:3.5
WORKDIR /edx/app/enterprise_catalog/enterprise_catalog
ADD requirements.txt /edx/app/enterprise_catalog/enterprise_catalog/
ADD Makefile /edx/app/enterprise_catalog/enterprise_catalog/
ADD requirements/ /edx/app/enterprise_catalog/enterprise_catalog/requirements/
RUN make requirements
ADD . /edx/app/enterprise_catalog/enterprise_catalog
EXPOSE 18160
