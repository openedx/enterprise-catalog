#!/usr/bin/env bash
# Should be run from root of repository.
# Example:
#  $ devstack/provision.sh
source devstack/include.sh

# TODO: Fail if we are not in correct dir.

log_major "Starting provisioning process..."

log_major "Pulling latest images..."
docker-compose pull --include-deps app

log_major "Bringing up containers..."
docker-compose up --detatch --build app

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
devstack/provision-app.sh


log_major "Restarting all containers..."
docker-compose restart

log_major "Provision complete!"
