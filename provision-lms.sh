#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

log_step "lms: Making sure MongoDB is ready..."
until docker-compose exec -T mongo bash -c 'mongo --eval "printjson(db.serverStatus())"' &> /dev/null
do
  printf "."
  sleep 1
done

log_step "MongoDB ready. Adding default MongoDB data..."
service_exec mongo mongorestore --gzip /data/dump

log_step "MongoDB ready. Creating MongoDB users..."
docker-compose exec -T mongo bash -c "mongo" < provision-mongo.js

log_step "Adding default MySQL data from dump..."
cat provision-mysql_from-devstack.sql | docker-compose exec -T mysql /usr/bin/mysql edxapp

log_step "Ensuring MySQL databases and users exist again..."
docker-compose exec -T mysql bash -c "mysql -uroot mysql" < provision-mysql.sql

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
