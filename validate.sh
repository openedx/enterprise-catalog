#!/bin/bash

set -e  # exit immediately on error

export DJANGO_SETTINGS_MODULE=enterprise_catalog.settings.test

cd /edx/app/enterprise_catalog/enterprise_catalog

make requirements

make validate_translations
make validate
make check_keywords
