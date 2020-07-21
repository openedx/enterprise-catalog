#!/usr/bin/env bash

# Include utilities.
source decentralized_devstack/provisioning-utils.sh

log_step "app: Bringing up container(s)..."
docker-compose up --build --detach app

log_step "app: Ensuring MySQL databases and users exist..."
docker-compose exec -T mysql mysql -uroot mysql < decentralized_devstack/provision-mysql-app.sql

log_step "app: Running migrations..."
service_exec app make migrate

log_step "app: Creating superuser..."
service_create_edx_user app

log_step "app: Creating users and API applications for integrating with LMS..."
create_lms_integration_for_service enterprise-catalog 8160

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
