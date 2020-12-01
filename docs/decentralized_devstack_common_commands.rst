Common commands for Decentralized Devstack
==========================================

.. role:: bash(code)
   :language: bash

We use docker-compose to define and run all the containers necessary for enterprise-catalog service. For Decentralized Devstack, the service is defined in decentralized-docker-compose.yml file. To learn more see: `Docker-compose cheatsheet`_ and `Official compose documentation`_

To use Decentralized Devstack you will need to first go to the `.env` file and uncomment one of the `COMPOSE_FILE` lines.

Below is a list of common commands used during development in Decentralized Devstack, if you find any commands missing, please add it to the list:

- start DD: :bash:`docker-compose up -d`

  * this will run containers in detached mode, remove `-d` if you want all logs to output in current terminal

- end a DD sesssion: :bash:`docker-compose down`
- update images: :bash:`docker-compose pull`
- enter <container_name>'s shell: :bash:`docker-compose exec <container_name> bash`

  * enterprise-catalog's bash shell: :bash:`docker-compose exec app bash`
  * lms's bash shell: :bash:`docker-compose exec lms bash`
  * mysql's mysql shell: :bash:`docker-compose exec mysql mysql`

- see <container_name>'s logs: :bash:`docker-compose logs -f <container_name>`

  * see enterprise-catalog's logs: :bash:`docker-compose logs -f app`
  * see lms's logs: :bash:`docker-compose logs -f lms`
- check which containers are running: :bash:`docker ps`

  * lists all running containers in docker engine.
  * to only see containers related to images declared in docker-compose file, run: :bash:`docker-compose ps`

- destroy current DD: :bash:`docker-compose down -v`
- provision: :bash:`./decentralized_devstack/provision.sh`

.. _ Docker-compose cheatsheet: https://devhints.io/docker-compose
.. _ Official compose documentation: https://docs.docker.com/compose/
