#!/usr/bin/env bash
# Should be run from root of repository.
# Example:
#  $ devstack/provision-app.sh
source devstack/include.sh

log "Running migrations..."
service_exec app make migrate

log "Creating superuser..."
service_exec_python app "\
from django.contrib.auth import get_user_model; \
User = get_user_model(); \
User.objects.create_superuser(\"edx\", \"edx@example.com\", \"edx\") if not User.objects.filter(username=\"edx\").exists() else None; \
"

name=enterprise_catalog
port=18160

log "Provisioning ${name}_worker user in LMS..."
service_exec_management lms manage_user "$name"_worker "$name"_worker@example.com --staff --superuser

log "Granting ${name}_worker user in permissions..."
service_exec_python lms "\
from django.contrib.auth import get_user_model; \
from django.contrib.auth.models import Permission; \
User = get_user_model(); \
enterprise_worker = User.objects.get(username='enterprise_worker'); \
enterprise_model_permissions = list(Permission.objects.filter(content_type__app_label='enterprise')); \
enterprise_worker.user_permissions.add(*enterprise_model_permissions); \
enterprise_worker.save(); \
"

log "Creating DOT application for single-sign-on via LMS..."
service_exec_management lms create_dot_application \
	--grant-type authorization-code \
	--skip-authorization \
	--redirect-uris "http://localhost:${port}/complete/edx-oauth2/" \
	--client-id  "$name"-sso-key \
	--client-secret  "$name"-sso-secret \
	--scopes 'user_id' "$name"-sso "$name"_worker

log "Creating DOT application for IDA-to-IDA communication..."
service_exec_management lms create_dot_application \
	--grant-type client-credentials  \
	--client-id "$name"-backend-service-key  \
	--client-secret "$name"-backend-service-secret "$name"-backend-service "$name"_worker 

log "Done provisioning app."
