#!/usr/bin/env bash
# Should be run from root of repository.
# Example:
#  $ devstack/provision-lms.sh
source devstack/include.sh

log "Runing migrations for LMS database..."
service_exec_management lms migrate

log "Runing migrations for LMS courseware student module history (CSMH) database..."
service_exec_management lms migrate --database student_module_history

# TODO: can we handle assets during provisioning? and do we even need it for slim LMS? for login, probably...
## log "Fixing missing vendor file by clearing the cache..."
## service_exec lms rm /edx/app/edxapp/edx-platform/.prereqs_cache/Node_prereqs.sha1
## log "Compiling static assets for LMS..."
## service_exec lms paver update_assets lms

log "Creating a superuser for LMS..."
service_exec_management lms --settings=devstack_docker manage_user edx edx@example.com --superuser --staff

log "Setting LMS superuser password to 'edx'..."
service_exec_python lms "\
from django.contrib.auth import get_user_model; \
User = get_user_model(); \
user = User.objects.get(username=\"edx\"); \
user.set_password(\"edx\"); user.save()\
"

log "Provisioning a retirement service account user for LMS..."
service_exec_management lms manage_user retirement_service_worker retirement_service_worker@example.com --staff --superuser
service_exec_management lms create_dot_application retirement_service_worker retirement

log "Done provisioning LMS."
