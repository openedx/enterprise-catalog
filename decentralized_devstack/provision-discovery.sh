#!/usr/bin/env bash

# Include utilities.
source decentralized_devstack/provisioning-utils.sh

log_step "discovery: Ensuring MySQL databases and users exist..."
docker-compose exec -T mysql mysql -uroot mysql < decentralized_devstack/provision-mysql-discovery.sql

log_step "discovery: Bringing up container"
docker-compose up -d discovery

log_step "discovery: Running migrations..."
service_exec_management discovery migrate

log_step "discovery: Create an edx superuser..."
service_create_edx_user discovery

log_step "discovery: Creating users and API applications for integrating with LMS..."
create_lms_integration_for_service discovery 18381

log_step "discovery: Removing files in /edx/var/discovery..." 
service_exec discovery bash -c 'rm -rf /edx/var/discovery/*'

log_step "discovery: Creating partner model..."
service_exec_management discovery create_or_update_partner \
	--site-id 1 \
	--site-domain localhost:18381 \
	--code edx \
	--name edX \
	--courses-api-url "http://edx.devstack.lms:18000/api/courses/v1/" \
	--ecommerce-api-url "http://edx.devstack.ecommerce:18130/api/v2/" \
	--organizations-api-url "http://edx.devstack.lms:18000/api/organizations/v0/" \
	--lms-url "http://edx.devstack.lms:18000/"

## TODO: We need ecom for this, probably.
## Removing for now, but it might block enterprise-catalog usage.
# log_step "discovery: Refreshing course metadata..."
# service_exec_management discovery refresh_course_metadata

## TODO: This is giving us an error because it can't connect to elasticsearch.
## Removing for now; unclear whether we need it.
# log_step "discovery: Running ./manage.py update_index..."
# service_exec_management discovery update_index --disable-change-limit

log_message "Done provisioning Discovery."
