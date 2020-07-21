#!/usr/bin/env bash

set -e
set -o pipefail
set -u
set -x

# Provisioning script for the discovery service
./provision-ida.sh discovery discovery 18381

discovery_exec(){
	docker-compose exec -T discovery bash -c "$*"
}

discovery_exec rm -rf /edx/var/discovery/*
discovery_exec python manage.py create_or_update_partner --site-id 1 --site-domain localhost:18381 --code edx --name edX --courses-api-url "http://edx.devstack.lms:18000/api/courses/v1/" --ecommerce-api-url "http://edx.devstack.ecommerce:18130/api/v2/" --organizations-api-url "http://edx.devstack.lms:18000/api/organizations/v0/" --lms-url "http://edx.devstack.lms:18000/"
discovery_exec python manage.py refresh_course_metadata
discovery_exec python manage.py update_index --disable-change-limit

# Add demo program
./programs/provision.sh discovery
