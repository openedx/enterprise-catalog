Decentralized Devstack(DD) Workflows
====================================

This document contains guides to various common workflows, **please update** if you see any missing workflows or wrong information.

.. role:: bash(code)
   :language: bash

Getting started from scratch
----------------------------

#. clone the enterprise-catalog repo and **cd into that directory**
#. create and activate either python 3.5 or 3.8 virtual environment, for more info: `virtualenv`_
#. run :bash:`make requirements` to install requirements.
#. open `.env` file and uncomment the line :bash:`COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
#. provision Decentralized devstack by running: :bash:`$ ./decentralized_devstack/provision.sh`
#. once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

   * You can login with the username *edx* and password *edx*.

#. start developing!

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/

Toggle between Decentralized Devstack and legacy Devstack
---------------------------------------------------------

To switch to Decentralized Devstack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you haven't setup Decentralized Devstack previously
``````````````````````````````````````````````````````

#. cd into edx/devstack directory and run `make down` to turn off legacy devstack
#. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
#. open `.env` file and uncomment the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
#. provision Decentralized devstack by running: :bash:`$ ./decentralized_devstack/provision.sh`
#. once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

   * You can login with the username *edx* and password *edx*.

6. start developing!

If you've already provisioned Decentralized Devstack
````````````````````````````````````````````````````

#. cd into edx/devstack directory and run `make down` to turn off legacy devstack
#. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
#. open `.env` file and uncomment the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
#. run :bash:`$ docker-compose up -d` to bring up DD
#. you can view the enterprise catalog at http://localhost:18160/admin

   * You can login with the username *edx* and password *edx*.

#. start developing!

To switch to Legacy Devstack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~


#. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
#. open `.env` file and comment out the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by adding "#" symbol
#. cd into edx/devstack directory and run :bash:`$ make dev.up.lms`(you might also have to run `dev.pull.lms` before)
#. cd into edx/enterprise-catalog directory and follow instructions in docs/getting_started.rst

.. note:: These instructions assume you have setup legacy devstack correctly before.

Turning on Decentralized Devstack
---------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD, it has already been provisioned(if not, see instructions above)

#. run :bash:`$ docker-compose up -d`

Turning off Decentralized Devstack
----------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD(if not, see instructions above)

#. run :bash:`$ docker-compose down`

Debugging Decentralized Devstack
--------------------------------

This is a grab bag of ideas that might help:

- check to make sure `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` is uncommented in .env file
- run :bash:`docker-compose ps` or/and :bash:`docker ps` to see which containers are up/running

  * if you see a container missing, start it in attached mode to see what logs it outputs by running: :bash:`docker-compose up <container_name>`
- enter container's shell by running: :bash:`docker-compose exec <container_name> bash`

  * once in container's shell, do your normal python/django/general tool debugging


Restarting everything from scratch
----------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD(if not, see instructions above)

.. WARNING:: This will irreversibly remove all decentralized devstack related containers, networks, and volumes.

#. run :bash:`$ docker-compose down -v`
#. provision decentralized devstack by running: :bash:`$ ./decentralized_devstack/provision.sh`
#. once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

   * You can login with the username *edx* and password *edx*.

#. start developing!
