#!/usr/bin/env bash

# Include utilities.
source decentralized_devstack/provisioning-utils.sh

# only load mysql schema if database does not exist, this way reprovisioning will not overwrite data
edxapp_count=$(docker-compose exec mysql mysql -uroot --skip-column-names -se "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='edxapp';" 2>/dev/null | tr -d $'\r')
if [[ "${edxapp_count}" = "1" ]]; then
  log_step "LMS DB exists, skipping lms schema load.."
else
  log_step "lms: Ensuring MySQL databases and users exist..."
  docker-compose exec -T mysql bash -c "mysql -uroot mysql" < decentralized_devstack/provision-mysql-lms.sql

  log_step "lms: Adding default MySQL data from dump..."
  docker-compose exec -T mysql /usr/bin/mysql edxapp < decentralized_devstack/provision-mysql-lms-data.sql
fi

log_step "lms: Making sure MongoDB is ready..."
until docker-compose exec -T mongo bash -c 'mongo --eval "printjson(db.serverStatus())"' &> /dev/null
do
  printf "."
  sleep 1
done

log_step "lms: Creating MongoDB users..."
docker-compose exec -T mongo bash -c "mongo" < decentralized_devstack/provision-mongo.js

log_step "lms: Adding default MongoDB data..."
service_exec mongo mongorestore --gzip /data/dump

log_step "lms: Bringing up LMS..."
docker-compose up --detach lms

# TODO: uncomment below in case we want to update data dump(when it has gotten off sync from lms)
# # TODO: Make sure this handles squashed migrations idempotently 
# # (e.g. enterprise/migrations/0001_squashed_0092_auto_20200312_1650.py)
# log_step "lms: Running migrations for default database..."
# service_exec_management lms migrate

# log_step "lms: Running migrations for courseware student module history (CSMH) database..."
# service_exec_management lms migrate --database student_module_history



log_message "Done provisioning LMS."
