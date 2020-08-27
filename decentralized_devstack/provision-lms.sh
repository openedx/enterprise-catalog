#!/usr/bin/env bash

# Include utilities.
source decentralized_devstack/provisioning-utils.sh

log_step "lms: Ensuring MySQL databases and users exist..."
docker-compose exec -T mysql bash -c "mysql -uroot mysql" < decentralized_devstack/provision-mysql-lms.sql

log_step "lms: Adding default MySQL data from dump..."
docker-compose exec -T mysql /usr/bin/mysql edxapp < decentralized_devstack/provision-mysql-lms-data.sql

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

# TODO: Make sure this handles squashed migrations idempotently 
# (e.g. enterprise/migrations/0001_squashed_0092_auto_20200312_1650.py)
log_step "lms: Running migrations for default database..."
service_exec_management lms migrate

log_step "lms: Running migrations for courseware student module history (CSMH) database..."
service_exec_management lms migrate --database student_module_history



log_message "Done provisioning LMS."
