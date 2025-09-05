Getting Started
===============

If you have not already done so, create/activate a `virtualenv`_. Unless otherwise stated, assume all terminal code
below is executed within the virtualenv.

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/


Initialize and Provision
------------------------
    1. Start and provision the edX `devstack <https://github.com/openedx/devstack>`_, as enterprise-catalog currently relies on devstack
    2. Verify that your virtual environment is active before proceeding
    3. Clone the enterprise-catalog repo and **cd into that directory**
    4. Run *make dev.provision* to provision a new enterprise catalog environment
    5. Run *make dev.init* to start the enterprise catalog app and run migrations

Viewing Enterprise Catalog
--------------------------
Once the server is up and running you can view the enterprise catalog at http://localhost:18160/admin.

You can login with the username *edx* and password *edx*.

Admin Access
------------
To access the Django admin pages in stage or production, follow the instructions in https://openedx.atlassian.net/wiki/spaces/SRE/pages/691568641/Django+Administration
on "Django Admin Pages for Newer Microservices". Please contact the enterprise titans squad if you need someone to grant you admin access.

Makefile Commands
--------------------
The `Makefile <../Makefile>`_ includes numerous commands to start the service, but the basic commands are the following:

Start the Docker containers to run the enterprise catalog servers

.. code-block:: bash

    $ make dev.up

Open the shell to the enterprise catalog container for manual commands

.. code-block:: bash

    $ make app-shell

Open the logs in the enterprise catalog container

.. code-block:: bash

    $ make app-logs

Migrating Catalog Data from LMS to the Catalog Service
------------------------------------------------------
You may already have enterprise catalog data persisted in your local LMS (edx-platform) database.  The edx-enterprise
library provides a `migrate_enterprise_catalogs <https://github.com/openedx/edx-enterprise/blob/master/enterprise/management/commands/migrate_enterprise_catalogs.py>`_
management command that will copy those existing catalogs and their metadata into your local catalog service.  From your **devstack** directory, do the following:

   #. ``make dev.up.lms+redis``
   #. ``make lms-shell``
   #. ``./manage.py lms migrate_enterprise_catalogs --api_user enterprise-catalog_worker``

Running Management Commands Locally
-----------------------------------
There are several management commands we use to synchronize data from the couse-discovery service into
enterprise-catalog, and to update the content of our search index.  To run these locally, you'll want to use
``make app-shell`` to enter an app container's bash shell, and then execute the command as written below.
Each of these management commands will enqueue 1 or more asynchronous celery tasks with a similar name.
Therefor, you'll want to open another terminal window and run ``make worker-logs`` to view any log output
from the celery tasks enqueued by these commands:

- ``./manage.py update_content_metadata`` This will ask the discovery service's ``/api/v1/search..`` endpoint
  for all the content, along with some metadata about the content, associated with all of the Enterprise Catalog
  objects in your service.  It will then associate that content to the appropriate catalogs.  Lastly, it will
  ask for additional metadata (again from the discovery service, using ``/api/v1/courses``)
  for all content records of type ``course``  and update the enterprise-catalog content metadata records accordingly.
- ``./manage.py update_full_content_metadata`` This does only the fetching of additional course metadata as
  described above.
- ``./manage.py reindex_algolia`` This will rebuild our Algolia search index; it won't work locally unless
  you configure your local enterprise-catalog service to point at a real Algolia index (like in a staging environment).

The celery tasks that underly these commands are configured to not run on the same input more than once every
60 minutes - see the `Architectural Decisions Record <../decisions/0002-celery-task-restructuring.rst>`_
that explain the rationale and implementation of this design.  Typically, trying to run one of these tasks a second
time in the same hour window will result in a ``TaskRecentlyRun`` error and no actual work will be done.

**Note** You can can add a ``--force`` option to each of these commands; doing so will force the underlying celery
task to run, regardless of how recently the same task with the same input was run in the past.

Running Management Commands in Stage or Prod environments
---------------------------------------------------------

The three commands described in the previous section each have corresponding jobs in argocd.tools.edx.org
under 'prod-enterprise-catalog' section.
``update_content_metadata`` and ``reindex_algolia`` are both run on a daily cron (so that new learning content that matches
an existing content filter will be included in appropriate catalogs as the content is published).  Since these jobs
only execute the underlying management commands, they are subject to the same hour-long "lock".  In case you
need to run the same job on the same input more frequently, the jobs can be run manually with the '--force' command in argocd.


Permissions
-----------

Requests against endpoints of this service are authorized via two mechanisms:

   #. JWT Roles, which are encoded inside a JWT cookie that is provided by the LMS.
   #. Feature-based Role Assignments, which are persisted in the database via the `EnterpriseCatalogRoleAssignment` model.

To get a JWT role defined inside your cookie, do the following:

   #. Create a new System-wide role assignment for your user: http://localhost:18000/admin/enterprise/systemwideenterpriseuserroleassignment/
   #. If you want the user to have admin access to all enterprises/catalogs, create the assignment with the `enterprise_openedx_operator` role.
   #. Otherwise, use the `enterprise_catalog_admin` role.  This will grant admin permissions on any Enterprise the user is a member of.
   #. Add your user to any Enterprises you want them to be an admin of: http://localhost:18000/admin/enterprise/enterprisecustomer/{enterprise_uuid}/manage_learners
   #. Log out and log back in as the user - this will refresh their JWT cookie.
   #. As a demonstration that this worked, use your browser's dev tools, find the `edx-jwt-cookie-header-payload` cookie and copy its content.
      Paste the encoded content into https://jwt.io.  The decoded payload section should have a `roles` field defined that looks like::

        "roles": [
            "enterprise_catalog_admin:{some-enterprise-uuid}",
            "enterprise_learner:{another-enterprise-uuid}",
            "enterprise_openedx_operator:*"
        ]
   #. Make a request to e.g. http://localhost:18160/api/v1/enterprise-catalogs/?format=json. For this example endpoint, you should get a response payload that looks like::

        {
          "count": 2,
          "next": null,
          "previous": null,
          "results": [
            {
              "uuid": "7467c9d2-433c-4f7e-ba2e-c5c7798527b2",
              "title": "All Content",
              "enterprise_customer": "378d5bf0-f67d-4bf7-8b2a-cbbc53d0f772"
            },
            {
              "uuid": "482a8a38-f60d-4250-8f93-402cd5f69d3b",
              "title": "All Course Runs",
              "enterprise_customer": "70699d54-7504-4429-8295-e1c0ec68dbc7"
            }
          ]
        }

How to define a role with a feature-based assignment:

   #. Add a new assignment via http://localhost:18160/admin/catalog/enterprisecatalogroleassignment/ using your user's
      email address and the `enterprise_catalog_admin` role to grant admin permissions.
   #. Grant permissions to catalogs of specific enterprises using the `Enterprise Customer UUID` field.  Leaving this
      field null will result in the user having the role applied for ALL enterprises/catalogs.
   #. Go ahead and make the request.  The role should take affect immediately after the assignment record is saved -
      you don't have to worry about logging out, cookies, or request headers.

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


