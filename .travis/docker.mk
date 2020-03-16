
docker_auth:
	echo "$$DOCKER_PASSWORD" | docker login -u "$$DOCKER_USERNAME" --password-stdin

docker_build:
	docker build . --target app -t "openedx/enterprise-catalog:latest"
	docker build . --target app -t "openedx/enterprise-catalog:$$TRAVIS_COMMIT"
	docker build . --target newrelic -t "openedx/enterprise-catalog:latest-newrelic"
	docker build . --target newrelic -t "openedx/enterprise-catalog:$$TRAVIS_COMMIT-newrelic"

docker_push: docker_build docker_auth ## push to docker hub
	docker push "openedx/enterprise-catalog:latest"
	docker push "openedx/enterprise-catalog:$$TRAVIS_COMMIT"
	docker push "openedx/enterprise-catalog:latest-newrelic"
	docker push "openedx/enterprise-catalog:$$TRAVIS_COMMIT-newrelic"
