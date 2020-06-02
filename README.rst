Enterprise catalog service  |Travis|_ |Codecov|_
===================================================
.. |Travis| image:: https://travis-ci.org/edx/enterprise-catalog.svg?branch=master
.. _Travis: https://travis-ci.org/edx/enterprise-catalog

.. |Codecov| image:: http://codecov.io/github/edx/enterprise-catalog/coverage.svg?branch=master
.. _Codecov: http://codecov.io/github/edx/enterprise-catalog?branch=master

A Django-based microservice for handling Enterprise catalogs, associating enterprise customers with curated courses from the full course catalog.

Getting Started
---------------

Check out the `initial steps <docs/getting_started.rst>`_ for getting started with the Enterprise catalog service.

Using ``django-silk`` for database/performance profiling
--------------------------------------------------------

``django-silk`` provides middleware to intercept/store HTTP requests and database queries for the purpose of profiling and inspection. For example,
you may want to examine the response times, number of database queries made, and the raw SQL the Django ORM creates to make database queries.

To use ``django-silk`` during local development to profile requests and database queries:

#. ``make dev.up.build`` (this will install ``django-silk`` if it hasn't already been installed)
#. ``make app-shell``
#. ``./manage.py migrate silk`` to run ``django-silk``'s migrations.
#. Navigate to http://localhost:18160/silk/ for the Django Silk UI.
#. Make any request (e.g., http://localhost:18160/api/v1/enterprise-catalogs/) and check back on the Silk UI.
#. The request you made should appear in the Django Silk UI. From here, click on the request to view its details.

``django-silk`` can also be used to profile specific code blocks within a function/method through the `silk_profile` decorator and/or context manager:

.. code-block::
    :linenos:

    from silk.profiling.profiler import silk_profile

    class EnterpriseCatalogGetContentMetadata(BaseViewSet, GenericAPIView):
      @silk_profile(name='get_enterprise_catalog')
      def get_enterprise_catalog(self):
          uuid = self.kwargs.get('uuid')
          return get_object_or_404(EnterpriseCatalog, uuid=uuid)

    class EnterpriseCatalogGetContentMetadata(BaseViewSet, GenericAPIView):
      def get_enterprise_catalog(self):
        with silk_profile(name='get_enterprise_catalog'):
            uuid = self.kwargs.get('uuid')
            return get_object_or_404(EnterpriseCatalog, uuid=uuid)

See https://github.com/jazzband/django-silk for more advanced usage.

License
-------

The code in this repository is licensed under version 3 of the AGPL unless otherwise noted. Please see the LICENSE_ file for details.

.. _LICENSE: https://github.com/edx/enterprise-catalog/blob/master/LICENSE

How To Contribute
-----------------

Contributions are welcome. Please read `How To Contribute <https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst>`_ for details. Even though it was written with ``edx-platform`` in mind, these guidelines should be followed for Open edX code in general.

Reporting Security Issues
-------------------------

Please do not report security issues in public. Please email security@edx.org.

Get Help
--------

Ask questions and discuss this project on `Slack <https://openedx.slack.com/messages/general/>`_ or in the `edx-code Google Group <https://groups.google.com/forum/#!forum/edx-code>`_.
