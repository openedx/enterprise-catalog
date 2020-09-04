Getting Started
===============


Starting from scratch
---------------------

If you have not already done so, install create/activate a Python 3.5 or 3.8 `virtualenv`_.
Unless otherwise stated, assume all terminal code below
is executed within the virtualenv.

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/

You will also need to install docker.


Initialize and Provision
~~~~~~~~~~~~~~~~~~~~~~~~

    1. Clone the enterprise-catalog repo and **cd into that directory**
    2. Verify that your virtual environment is active and all requirements installed (`make requirements`) before proceeding
    3. Uncomment `TODO` in .env file
    4. Run the following to provision a new enterprise catalog environment::
        $ ./decentralized_devstack/provision.sh

Viewing Enterprise Catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~

Once the server is up and running you can view the enterprise catalog at http://localhost:18160/admin.

You can login with the username *edx* and password *edx*.


Toggle between decentralized_devstack and normal devstack
---------------------------------------------------------

