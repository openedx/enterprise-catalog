#!/usr/bin/env bash

# Include utilities.
source decentralized_devstack/provisioning-utils.sh

# only load mysql schema if database does not exist, this way reprovisioning will not overwrite data
edxapp_count=$(docker-compose exec mysql mysql -uroot --skip-column-names -se "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='edxapp';" 2>/dev/null | tr -d $'\r')
if [[ "${edxapp_count}" = "1" ]]; then
  log_step "LMS DB exists, skipping lms schema load.."
else
  log_step "lms: Ensuring MySQL databases and users exist..."
  docker-compose exec -T mysql mysql -uroot mysql < decentralized_devstack/provision-mysql-lms.sql

  log_step "lms: Adding default MySQL data from dump..."
  docker-compose exec -T mysql mysql edxapp < decentralized_devstack/provision-mysql-lms-data.sql
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
# FYI, without --quiet flag below, when this command is run on database which was previously provisioned,
# it will throw out errors complaining about duplicates(E11000 duplicate key error collection),
# we are  ignoring these errors(using --quiet flag),
# because mongorestore behaves how we want it to: Not replace data that already exists
service_exec mongo mongorestore --quiet --gzip /data/dump 

log_step "lms: Bringing up LMS..."
docker-compose up --detach lms

# # TODO: Make sure this handles squashed migrations idempotently 
# # (e.g. enterprise/migrations/0001_squashed_0092_auto_20200312_1650.py)
log_step "lms: Running migrations for default database..."
service_exec_management lms migrate

log_step "lms: Running migrations for courseware student module history (CSMH) database..."
service_exec_management lms migrate --database student_module_history

log_message "Done provisioning LMS."
