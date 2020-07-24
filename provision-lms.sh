#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

# TODO: Make sure this handles squashed migrations idempotently 
# (e.g. enterprise/migrations/0001_squashed_0092_auto_20200312_1650.py)
#log_step "lms: Running migrations for default database..."
#service_exec_management lms migrate

#log_step "lms: Running migrations for courseware student module history (CSMH) database..."
#service_exec_management lms migrate --database student_module_history


## TODO: can we handle assets during provisioning? and do we even need it for slim LMS? for login, probably...
# log "Fixing missing vendor file by clearing the cache..."
# service_exec lms rm /edx/app/edxapp/edx-platform/.prereqs_cache/Node_prereqs.sha1
# log "Compiling static assets for LMS..."
# service_exec lms paver update_assets lms


log_message "Done provisioning LMS."
