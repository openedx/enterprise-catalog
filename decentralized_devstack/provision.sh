#!/usr/bin/env bash

# Include utilities.
source provisioning-utils.sh

log_step "Starting provisioning process..."

log_step "Bringing down any existing containers..."
docker-compose down

log_step "Pulling latest images..."
docker-compose pull --include-deps app

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

# Run provisioning scripts for dependencies.
# We call provision-lms.sh, provision-discovery.sh, etc., and log an error
# if they fail.
# 'source' tells bash to run in the same shell. This makes the timestamps
# in the log messages work correctly.
for dependency in lms discovery ; do
	log_message "Provisioning dependency: ${dependency}..."
	# shellcheck source=provision-lms.sh
	# shellcheck source=provision-discovery.sh
	if ! source ./provision-"$dependency".sh ; then
		log_error "Error occured while provisioning ${dependency}; stopping."
		exit 1
	fi
done

log_message "Provisioning app..."
source ./../provision-app.sh

log_step "Restarting all containers..."
docker-compose restart

log_step "Provision complete!"
