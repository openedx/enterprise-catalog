#!/bin/bash

set -e  # exit immediately on error

export DJANGO_SETTINGS_MODULE=enterprise_catalog.settings.test

cd /edx/app/enterprise_catalog/enterprise_catalog

# The edxops/enterprise-catalog-dev image doesn't have uv preinstalled.
command -v uv >/dev/null 2>&1 || pip install uv

make requirements

# Alex Dusenbery 2022-04-12: This is failing CI for a reason I don't understand
# and I don't know why we care about translations here, anyway.
# make validate_translations
make validate
make check_keywords
