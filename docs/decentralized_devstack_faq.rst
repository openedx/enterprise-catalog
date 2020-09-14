Docker-compose for Decentralized Devstack
=========================================

.. role:: bash(code)
   :language: bash

As you use DD, please add any questions and answers that you think would be useful to others to this doc

How do I run make migrate on enterprise-catalog?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You have two options: 

#. Run following command: :bash:`docker-compose exec -T app make migrate`
#. Enter shell and run command from inside containers:

   * To enter shell: :bash:`docker-compose exec app bash`

     + You command line should now be in enterprise-catalog directory in container.
     + From here, you can run any django/python related commands to interact with enterprise-catalog service

   * Run: :bash:`make migrate`

FYI, to run another general command like :bash:`python3 manage.py makemigrations` on service, just replace :bash:`make migrate` above with general command.
