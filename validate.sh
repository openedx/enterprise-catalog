#!/bin/bash
export DJANGO_SETTINGS_MODULE=enterprise_catalog.settings.test

source /edx/app/enterprise_catalog/enterprise_catalog/venv/bin/activate
cd /edx/app/enterprise_catalog/enterprise_catalog

make requirements

make validate_translations
make validate
