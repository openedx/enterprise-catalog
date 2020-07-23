#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

log_step "discovery: Running migrations..."
service_exec_management discovery migrate

log_step "discovery: Create an edx superuser..."
service_create_edx_user discovery

log_step "discovery: Creating users and API applications for integrating with LMS..."
create_lms_integration_for_service discovery 18381

# TODO: can we handle assets during provisioning? and do we even need it for slim Discovery?
## log "Compiling static assets for Discovery..."
## service_exec discovery make static

log_step "discovery: Removing files in /edx/var/discovery..." 
service_exec discovery rm -rf /edx/var/discovery/*

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

# TODO: Do we need Ecom for this?
log_step "discovery: Refreshing course metadata..."
service_exec_management discovery refresh_course_metadata

log_step "discovery: Running ./manage.py update_index..."
service_exec_management discovery update_index --disable-change-limit

log_message "Done provisioning Discovery."
