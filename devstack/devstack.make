
# TODO fix

dev.provision:
	bash ./provision-catalog.sh

dev.init: dev.up dev.migrate

dev.makemigrations:
	docker exec -it enterprise.catalog.app bash -c 'cd /edx/app/enterprise_catalog/enterprise_catalog && python3 manage.py makemigrations'

dev.migrate: # Migrates databases. Application and DB server must be up for this to work.
	docker exec -it enterprise.catalog.app bash -c 'cd /edx/app/enterprise_catalog/enterprise_catalog && make migrate'

dev.up: # Starts all containers
	docker-compose up -d

dev.up.build:
	docker-compose up -d --build

dev.down: # Kills containers and all of their data that isn't in volumes
	docker-compose down

dev.destroy: dev.down #Kills containers and destroys volumes. If you get an error after running this, also run: docker volume rm portal-designer_designer_mysql
	docker volume rm enterprise-catalog_enterprise_catalog_mysql

dev.stop: # Stops containers so they can be restarted
	docker-compose stop

%-shell: ## Run a shell, as root, on the specified service container
	docker exec -u 0 -it enterprise.catalog.$* env TERM=$(TERM) bash

%-logs: ## View the logs of the specified service container
	docker-compose logs -f --tail=500 $*

attach:
	docker attach enterprise.catalog.app

docker_build:
	docker build . --target app -t "openedx/enterprise-catalog:latest"
	docker build . --target newrelic -t "openedx/enterprise-catalog:latest-newrelic"

travis_docker_auth:
	echo "$$DOCKER_PASSWORD" | docker login -u "$$DOCKER_USERNAME" --password-stdin

travis_docker_tag: docker_build
	docker build . --target app -t "openedx/enterprise-catalog:$$TRAVIS_COMMIT"
	docker build . --target newrelic -t "openedx/enterprise-catalog:$$TRAVIS_COMMIT-newrelic"

travis_docker_push: travis_docker_tag travis_docker_auth ## push to docker hub
	docker push "openedx/enterprise-catalog:latest"
	docker push "openedx/enterprise-catalog:$$TRAVIS_COMMIT"
	docker push "openedx/enterprise-catalog:latest-newrelic"
	docker push "openedx/enterprise-catalog:$$TRAVIS_COMMIT-newrelic"
