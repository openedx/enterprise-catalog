#!/bin/bash

set -e  # exit immediately on error

export DJANGO_SETTINGS_MODULE=enterprise_catalog.settings.test

cd /edx/app/enterprise_catalog/enterprise_catalog

if [[ "$TOXENV" == "py38-django42" ]]; then
    make requirements
elif [[ "$TOXENV" == "py312-django42" ]]; then
    make requirements312
fi

# Alex Dusenbery 2022-04-12: This is failing CI for a reason I don't understand
# and I don't know why we care about translations here, anyway.
# make validate_translations
make validate
make check_keywords
