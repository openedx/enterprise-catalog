Decentralized Devstack(DD) Workflows
====================================

.. role:: bash(code)
   :language: bash

.. _Getting Started from scratch:

Getting Started from scratch
----------------------------

1. Clone the enterprise-catalog repo and **cd into that directory**
2. Create and activate either python 3.5 or 3.8 virtual environment, for more info: `virtualenv`_
3. install requirements by running: `make requirements`
4. open .env file and uncomment the line :bash:`COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
5. provision Decentralized devstack by running: `./decentralized_devstack/provision.sh`
6. Once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

  - You can login with the username *edx* and password *edx*.

7. start developing!

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/

Toggle between Decentralized Devstack and legacy Devstack
---------------------------------------------------------

To switch to Decentralized Devstack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if you haven't setup Decentralized Devstack previously
``````````````````````````````````````````````````````

1. cd into edx/devstack directory and run `make down` to turn off legacy devstack
2. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
3. open .env file and uncomment the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
4. provision Decentralized devstack by running: `./decentralized_devstack/provision.sh`
5. once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

  - You can login with the username *edx* and password *edx*.

6. start developing!

if you've already provisioned Decentralized Devstack
````````````````````````````````````````````````````

1. cd into edx/devstack directory and run `make down` to turn off legacy devstack
2. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
3. open .env file and uncomment the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by removing "#" symbol
4. run `docker-compose up -d` to bring up DD
5. you can view the enterprise catalog at http://localhost:18160/admin

  - You can login with the username *edx* and password *edx*.

6. start developing!

To switch to Legacy Devstack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~


1. cd into edx/enterprise-catalog directory and run `docker-compose down` to turn off any local docker-compose containers(defined in docker_compose.yml files)
2. open .env file and comment out the line `COMPOSE_FILE=decentralized_devstack/docker-compose.yml` by adding "#" symbol
3. cd into edx/devstack directory and run `make dev.up.lms`(you might also have to run `dev.pull.lms` before)
4. cd into edx/enterprise-catalog directory and follow instructions in docs/getting_started.rst

.. note:: These instructions assume you have setup legacy devstack correctly before.

Turning on Decentralized Devstack
---------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD, it has already been provisioned(if not, see instructions above)

- run `docker-compose up -d`

Turning off Decentralized Devstack
---------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD, it has already been provisioned(if not, see instructions above)

- run `docker-compose down`

Restarting everything from scratch
----------------------------------

Prerequisites: You have toggled to enterprise_catalog's DD(if not, see instructions above)

.. warning:: This will irreversibly remove all decentralized devstack related containers, networks, and volumes.

1. run `docker-compose down -v`
2. provision Decentralized devstack by running: `./decentralized_devstack/provision.sh`
3. Once provisioning has successfully run, you can view the enterprise catalog at http://localhost:18160/admin

  - You can login with the username *edx* and password *edx*.

4. start developing!
