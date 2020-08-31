Getting Started
===============

If you have not already done so, install create/activate a Python 3.5 or 3.8 `virtualenv`_.
Unless otherwise stated, assume all terminal code below
is executed within the virtualenv.

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/

You will also need to install docker.


Initialize and Provision
------------------------
    1. Verify that your virtual environment is active and all requirements installed (`make requirements`) before proceeding
    2. Clone the enterprise-catalog repo and **cd into that directory**
    3. Run the following to provision a new enterprise catalog environment:

    .. code-block:: bash

        $ docker-compose pull --include-deps app && docker ps
        $ ./decentralized_devstack/provision.sh

Viewing Enterprise Catalog
--------------------------
Once the server is up and running you can view the enterprise catalog at http://localhost:18160/admin.

You can login with the username *edx* and password *edx*.

Makefile Commands
--------------------
The `Makefile <../Makefile>`_ includes numerous commands to interact with the service, but the basic commands are the following:

Open the shell to the enterprise catalog container for manual commands

.. code-block:: bash

    $ make app-shell

Open the logs in the enterprise catalog container

.. code-block:: bash

    $ make app-logs

Migrating Catalog Data from LMS to the Catalog Service
------------------------------------------------------
You may already have enterprise catalog data persisted in your local LMS (edx-platform) database.  The edx-enterprise
library provides a `migrate_enterprise_catalogs <https://github.com/edx/edx-enterprise/blob/master/enterprise/management/commands/migrate_enterprise_catalogs.py>`_
management command that will copy those existing catalogs and their metadata into your local catalog service.

First, make sure to run `docker-compose down` in this repo.
Then from your **devstack** directory, do the following:

   #. ``make dev.up.lms+redis``
   #. ``make lms-shell``
   #. ``./manage.py lms migrate_enterprise_catalogs --api_user enterprise_catalog_worker``

Advanced Setup Outside Docker
=============================
The following is provided for informational purposes only. You can likely ignore this section.

Local/Private Settings
----------------------
When developing locally, it may be useful to have settings overrides that you do not wish to commit to the repository.
If you need such overrides, create a file :file:`catalog/settings/private.py`. This file's values are
read by :file:`catalog/settings/local.py`, but ignored by Git.

Configure edX OAuth
-------------------
This service relies on the LMS server as the OAuth 2.0 authentication provider.

Configuring Enterprise catalog service to communicate with other IDAs using OAuth requires registering a new client with the authentication
provider (LMS) and updating the Django settings for this project with the generated client credentials.

A new OAuth 2.0 client can be created when using Devstack by visiting ``http://127.0.0.1:18000/admin/oauth2_provider/application/``.
    1. Click the :guilabel:`Add Application` button.
    2. Leave the user field blank.
    3. Specify the name of this service, ``Enterprise catalog service``, as the client name.
    4. Set the :guilabel:`URL` to the root path of this service: ``http://127.0.0.1:8003/``.
    5. Set the :guilabel:`Redirect URL` to the complete endpoint: ``http://127.0.0.1:18150/complete/edx-oauth2/``.
    6. Copy the :guilabel:`Client ID` and :guilabel:`Client Secret` values. They will be used later.
    7. Select :guilabel:`Confidential` as the client type.
    8. Select :guilabel:`Authorization code` as the authorization grant type.
    9. Click :guilabel:`Save`.



Now that you have the client credentials, you can update your settings (ideally in
:file:`catalog/settings/local.py`). The table below describes the relevant settings.

+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+
| Setting                           | Description                      | Value                                                                    |
+===================================+==================================+==========================================================================+
| SOCIAL_AUTH_EDX_OAUTH2_KEY        | SSO OAuth 2.0 client key         | (This should be set to the value generated when the client was created.) |
+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+
| SOCIAL_AUTH_EDX_OAUTH2_SECRET     | SSO OAuth 2.0 client secret      | (This should be set to the value generated when the client was created.) |
+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+
| SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT   | OAuth 2.0 authentication URL     | http://127.0.0.1:18000/oauth2                                            |
+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+
| BACKEND_SERVICE_EDX_OAUTH2_KEY    | IDA<->IDA OAuth 2.0 client key   | (This should be set to the value generated when the client was created.) |
+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+
| BACKEND_SERVICE_EDX_OAUTH2_SECRET | IDA<->IDA OAuth 2.0 client secret| (This should be set to the value generated when the client was created.) |
+-----------------------------------+----------------------------------+--------------------------------------------------------------------------+


Run migrations
--------------
Local installations use SQLite by default. If you choose to use another database backend, make sure you have updated
your settings and created the database (if necessary). Migrations can be run with `Django's migrate command`_.

.. code-block:: bash

    $ python manage.py migrate

.. _Django's migrate command: https://docs.djangoproject.com/en/1.11/ref/django-admin/#django-admin-migrate


Run the server
--------------
The server can be run with `Django's runserver command`_. If you opt to run on a different port, make sure you update
OAuth2 client via LMS admin.

.. code-block:: bash

    $ python manage.py runserver 8003

.. _Django's runserver command: https://docs.djangoproject.com/en/1.11/ref/django-admin/#runserver-port-or-address-port


