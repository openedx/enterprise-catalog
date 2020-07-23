#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

# TODO: Replace this with 
log_step "lms: Running migrations for default database..."
export SHA="$(service_exec lms cat /edx/app/edx-platform/edx-platform/common/test/db_cache/bok_choy_migrations.sha1)"

service_exec_management lms migrate

log_step "lms: Running migrations for courseware student module history (CSMH) database..."
service_exec_management lms migrate --database student_module_history

# TODO: can we handle assets during provisioning? and do we even need it for slim LMS? for login, probably...
## log "Fixing missing vendor file by clearing the cache..."
## service_exec lms rm /edx/app/edxapp/edx-platform/.prereqs_cache/Node_prereqs.sha1
## log "Compiling static assets for LMS..."
## service_exec lms paver update_assets lms

log_step "lms: Creating a superuser..."
service_create_edx_user lms

log_step "lms: Provisioning a retirement service account user..."
service_exec_management lms manage_user retirement_service_worker retirement_service_worker@example.com --staff --superuser
service_exec_management lms create_dot_application retirement_service_worker retirement

log_message "Done provisioning LMS."
