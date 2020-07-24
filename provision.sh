#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

log_step "Starting provisioning process..."

## TODO put this back.
# log_step "Bringing down any existing containers..."
# docker-compose down

## TODO put this back.
# log_step "Pulling latest images..."
# docker-compose pull --include-deps app

log_step "Bringing up database containers..."
docker-compose up --detach mysql mongo elasticsearch

is_mysql_ready(){
	docker-compose exec \
		-T mysql mysql \
		-u root \
		-se "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = 'root')" \
		&> /dev/null
}

log_step "Waiting until we can run a MySQL query..."
until is_mysql_ready
do
  printf "."
  sleep 1
done

# A fresh MySQL container with no databases may die and need to be restarted.
# So, we wait 5 seconds, and if MySQL has died, restart it and wait 5 more seconds.
# See https://github.com/docker-library/mysql/issues/245 for why this is necessary.
log_step "Waiting a few seconds to make sure MySQL is ready..."
sleep 5
if ! is_mysql_ready; then
	log_step "Restarting MySQL because it died."
	docker-compose restart mysql
	sleep 5
fi

log_step "Adding default MySQL data from dump..."
docker-compose exec -T mysql /usr/bin/mysql edxapp < provision-mysql_from-devstack.sql

log_step "Ensuring MySQL databases and users exist..."
docker-compose exec -T mysql bash -c "mysql -uroot mysql" < provision-mysql.sql

log_step "lms: Making sure MongoDB is ready..."
until docker-compose exec -T mongo bash -c 'mongo --eval "printjson(db.serverStatus())"' &> /dev/null
do
  printf "."
  sleep 1
done

log_step "MongoDB ready. Creating MongoDB users..."
docker-compose exec -T mongo bash -c "mongo" < provision-mongo.js

log_step "MongoDB ready. Adding default MongoDB data..."
service_exec mongo mongorestore --gzip /data/dump

log_step "Bringing up app containers..."
docker-compose up --detach app

# Run provisioning scripts for dependencies.
# We call provision-lms.sh, provision-discovery.sh, etc., and log an error
# if they fail.
# 'source' tells bash to run in the same shell. This makes the timestamps
# in the log messages work correctly.
for dependency in lms discovery ; do
	log_message "Provisioning dependency: ${dependency}..."
	if ! source ./provision-"$dependency".sh ; then
		log_error "Error occured while provisioning ${dependency}; stopping."
		exit 1
	fi
done

log_message "Provisioning app..."

log_step "app: Running migrations..."
service_exec app make migrate

log_step "app: Creating superuser..."
service_create_edx_user app

log_step "app: Creating users and API applications for integrating with LMS..."
create_lms_integration_for_service enterprise_catalog 18160

## TODO: Handle https://github.com/edx/enterprise-catalog/blob/master/docs/getting_started.rst#permissions

## TODO: Do we still need this? It came from edx/devstack:entprise/provision.sh
## If so, the username should be enterprise_catalog_worker, not enterprise_worker.
# log_step "Granting enterprise_worker user in permissions..."
# service_exec_python lms "\
# from django.contrib.auth import get_user_model; \
# from django.contrib.auth.models import Permission; \
# User = get_user_model(); \
# enterprise_worker = User.objects.get(username='enterprise_worker'); \
# enterprise_model_permissions = list(Permission.objects.filter(content_type__app_label='enterprise')); \
# enterprise_worker.user_permissions.add(*enterprise_model_permissions); \
# enterprise_worker.save(); \
# "

log_step "Restarting all containers..."
docker-compose restart

log_step "Provision complete!"
