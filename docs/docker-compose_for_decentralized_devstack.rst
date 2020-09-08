Docker-compose for Decentralized Devstack
=========================================

We use docker-compose to define and run all the containers necessary for enterprise-catalog service. For decentralized devstack, the service is defined in decentralized-docker-compose.yml file. You should be able to interface with DD using the following docker-compose commands:

- start DD: `docker-compose up -d`
- end a DD sesssion: `docker-compose down`
- update images: `docker-compose pull`
- enter enterprise-catalog's bash shell: `docker-compose exec app bash`
- see enterise-catalog's logs: `docker-compose logs -f app`
- check which containers are running: `docker ps`

`Docker-compose cheatsheet`_

`Official compose documentation`_

.. _ Docker-compose cheatsheet: https://devhints.io/docker-compose

.. _ Official compose documentation: https://docs.docker.com/compose/

Enterprise-catlog FAQ
---------------------

As you use DD, please add any questions and answers that you think would be useful to others to this doc

How do I run make migrate on enterprise-catalog?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You have two options: 

1) Run following command: docker exec -it enterprise.catalog.app bash -c 'make migrate'
2) Enter shell and run command from inside containers

  - To enter shell: `docker-compose exec app bash`

    + You command line should now be in enterprise-catalog directory in container.
    + From here, you can run any django/python related commands to interact with enterprise-catalog service

  - Run: `make migrate`

FYI, to run another general command like `python3 manage.py makemigrations` on service, just replace `make migrate` above with general command.
