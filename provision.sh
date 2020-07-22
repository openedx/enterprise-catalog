#!/usr/bin/env bash

# Include utilities.
source devstack/include.sh

# TODO: Fail if we are not in correct dir.

log_major "Starting provisioning process..."

log_major "Pulling latest images..."
docker-compose pull --include-deps app

log_major "Bringing up containers..."
docker-compose up --detach --build app

log_major "Waiting a few seconds to make sure MySQL is ready..."
until docker exec -i enterprise.catalog.mysql mysql -u root -se "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = 'root')" &> /dev/null
do
  printf "."
  sleep 1
done
sleep 5

for dependency in lms discovery ; do
	log_major "Provisioning dependency: ${dependency}..."
	devstack/provision-"$dependency".sh
done

log_major "Provisioning app..."

log "Running migrations..."
service_exec app make migrate

log "Creating superuser..."
service_create_edx_user app

log "Creating users and API applications for integrating with LMS..."
create_lms_integration_for_service enterprise_catalog 18160

# TODO: Handle https://github.com/edx/enterprise-catalog/blob/master/docs/getting_started.rst#permissions

# TODO: Do we still need this?
# If so, the username should be enterprise_catalog_worker, not enterprise_worker.
## log "Granting enterprise_worker user in permissions..."
## service_exec_python lms "\
## from django.contrib.auth import get_user_model; \
## from django.contrib.auth.models import Permission; \
## User = get_user_model(); \
## enterprise_worker = User.objects.get(username='enterprise_worker'); \
## enterprise_model_permissions = list(Permission.objects.filter(content_type__app_label='enterprise')); \
## enterprise_worker.user_permissions.add(*enterprise_model_permissions); \
## enterprise_worker.save(); \
## "

log_major "Restarting all containers..."
docker-compose restart

log_major "Provision complete!"
