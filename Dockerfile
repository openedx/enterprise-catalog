FROM python:3.6
WORKDIR /edx/app/catalog/catalog
ADD requirements.txt /edx/app/catalog/catalog/
ADD Makefile /edx/app/catalog/catalog/
ADD requirements/ /edx/app/catalog/catalog/requirements/
RUN make requirements
ADD . /edx/app/catalog/catalog
EXPOSE 18160
