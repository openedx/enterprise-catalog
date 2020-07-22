#!/usr/bin/env bash

# Include utilities.
source devstack/include.sh

log "Runing migrations for Discovery database..."
service_exec_management discovery migrate

log "Create an edx superuser in Discovery..."
service_create_edx_user discovery

log "Creating Discovery users and API applications for integrating with LMS..."
create_lms_integration_for_service discovery 18381

# TODO: can we handle assets during provisioning? and do we even need it for slim Discovery?
## log "Compiling static assets for Discovery..."
## service_exec discovery make static

log "Removing files in /edx/var/discovery..." 
service_exec discovery rm -rf /edx/var/discovery/*

log "Creating partner model..."
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
log "Refreshing course metadata..."
service_exec_management discovery refresh_course_metadata

log "Running ./manage.py update_index in Discovery..."
service_exec_management discovery update_index --disable-change-limit

log "Done provisioning Discovery."
