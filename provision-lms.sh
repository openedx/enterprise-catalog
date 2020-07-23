#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

# TOOD: Use some sort of database dump to speed the rest of these steps up.
db_sha="$(service_exec lms cat /edx/app/edx-platform/edx-platform/common/test/db_cache/bok_choy_migrations.sha1)"

log_step "lms: Running migrations for default database..."
service_exec_management lms migrate

log_step "lms: Running migrations for courseware student module history (CSMH) database..."
service_exec_management lms migrate --database student_module_history

# TODO: can we handle assets during provisioning? and do we even need it for slim LMS? for login, probably...
## log "Fixing missing vendor file by clearing the cache..."
## service_exec lms rm /edx/app/edxapp/edx-platform/.prereqs_cache/Node_prereqs.sha1
## log "Compiling static assets for LMS..."
## service_exec lms paver update_assets lms

log_step "lms: Making sure MongoDB is ready..."
until docker-compose exec -T mongo bash -c 'mongo --eval "printjson(db.serverStatus())"' &> /dev/null
do
  printf "."
  sleep 1
done

log_step "MongoDB ready. Creating MongoDB users..."
docker-compose exec -T mongo bash -c "mongo" < provision-mongo.js

log_step "lms: Creating a superuser..."
service_create_edx_user lms

log_step "lms: Provisioning a retirement service account user..."
service_exec_management lms manage_user \
	--staff --superuser \
	retirement_service_worker retirement_service_worker@example.com
service_exec_management lms create_dot_application \
	retirement retirement_service_worker

log_message "Done provisioning LMS."
