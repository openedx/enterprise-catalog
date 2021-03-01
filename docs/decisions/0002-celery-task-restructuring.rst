Celery Task Restructuring
=========================

Status
------

Accepted (circa February 2021)

Context
-------

We update the content of enterprise catalogs and rebuild our Algolia search index on a regular basis.
"Updating the content" here means that we update which content is included in which catalog, based
on the result of requests to the course-discovery service's ``/api/v1/search/all/`` endpoint.  It also
means that we update the metadata associated with those content records, based both on the response
from the ``/search/all`` endpoint, as well as the response from the ``/api/v1/courses`` discovery endpoint.

Currently, in the course of doing daily or ad-hoc updates of enterprise catalogs,
we end up processing the same catalog query over and over, in order to refresh metadata and
re-index algolia.  These are expensive and time-consuming operations, and the tendency for them
to occur repeatedly in a short window of time increases the risk of some failure modes occurring.

There are three tasks included in this dance of updates:

* ``update_catalog_metadata_task`` which updates the association of ``ContentMetadata`` records to
  ``CatalogQuery`` records, and does a partial update of the metadata records' ``json_metadata`` field.
* ``update_full_content_metadata_task`` which does a full update of the metadata records' ``json_metadata``
  based on a request to the discovery service's ``/api/v1/courses`` endpoint.
* ``index_enterprise_catalog_courses_in_algolia_task`` which rebuilds the Algolia index with a series of
  partial-update requests.

We really only need the ``update_full_content_metadata_task`` to run for the sake of
``index_enterprise_catalog_courses_in_algolia_task`` .  Here’s a quick sketch of a series of events that could occur::

  update_metadata(1) # gets a lock and updates catalog query 1
  update_metadata(2) # gets a lock and updates query 2
  update_metadata(2) # lock was already acquired, do nothing

  # .... there could be any number of attempts to update_metadata() here
  # but assume that no more than an hour passes in the meantime
  update_metadata(37) # get lock and update catalog query 37

  # Now these last two things happen exactly once each, one
  # after the other.
  # First, update all of the content metadata we have - don't accept
  # a list of it as a parameter any more.
  update_full_content_metadata_task()
  
  # Then reindex algolia with every piece of content metadata
  # and importantly, on the content-catalog associations, we have.
  index_enterprise_catalog_courses_in_algolia()

Decision
--------

We want our celery tasks around this update/re-indexing to behave as follows:

1. ``update_catalog_metadata_task`` should not be able to run on the same ``CatalogQuery`` id more than once
   in a given time period (an hour).  This is like a "lock" or "semaphore".
2. ``update_full_content_metadata_task`` should wait for any ``update_catalog_metadata_tasks`` that have started
   in a recent window of time to finish before starting.  It should also not execute more
   than once in a given time period.
3. ``index_enterprise_catalog_courses_in_algolia_task`` should wait for any ``update_full_content_metadata_tasks``
   that have started in a recent window of time to finish before starting.  It should also not execute more than
   once in a given time period.

When talking about locking tasks for a period of time below, we almost always mean an hour.

Use a TaskResult celery backend
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

https://github.com/celery/django-celery-results  will let us use a Django model called ``TaskResult``
as a celery results backend, thus making it easy to inspect the state of tasks with a given name/kwargs/etc.
Inspecting the state of arbitrary tasks from within tasks makes it easy to achieve
the desired locking and waiting behaviors described above.

An example ``TaskResult`` instance::

  mysql> select * from django_celery_results_taskresult\G
  *************************** 1. row ***************************
                id: 1
           task_id: 5ed8f88d-0ea3-4ac0-a1e1-6df94a9c9c57
            status: SUCCESS
      content_type: application/json
  content_encoding: utf-8
            result: null
         date_done: 2021-02-05 20:42:29.852773
         traceback: NULL
              meta: {"children": []}
         task_args: []
       task_kwargs: {"catalog_query_id": 4}
         task_name: enterprise_catalog.apps.api.tasks.update_catalog_metadata_task
            worker: celery@worker.catalog.enterprise
      date_created: 2021-02-05 20:42:26.091833

Set the DB isolation level to read-committed
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

From the django-celery-results docs:

  `Some databases use a default transaction isolation level that isn’t suitable for polling tables for changes.
  In MySQL the default transaction isolation level is REPEATABLE-READ: meaning the transaction won’t see
  changes made by other transactions until the current transaction is committed.`

``REPEATABLE-READ`` is in fact the isolation level for the enterprise_catalog database.  We'll
change this to ``READ-COMMITTED`` at the Django DB settings level.  If we didn't do this, we'd
have to take more care when attempting to observe state change from a transaction in task B from
within a different transaction in task A.

Modify the update catalog metadata task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``update_catalog_metadata_task`` should not be able to run on the same ``CatalogQuery`` id more than once
in a given time period.  This will prevent "double-work" being done, particularly from
the context of the enterprise-catalog ``/refresh_metadata`` endpoint, where we frequently see multiple
requests to update the same catalog query within a short time window.

The task will now save each ``ContentMetadata`` record associated with the catalog query it operates on,
even if that record's ``json_metadata`` field did not change.  This is for the sake of the changes to the tasks
described below, which will now look for recently-modified metadata records to do full updates and reindexing of.

Modify the update full content metadata task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are two situations in which we update metadata and reindex algolia -
a management command (that's typically executed daily), and via a ``/refresh_metadata`` endpoint,
which might be hit in rapid succession by edx-enterprise due to a catalog query change.  

For the management command, we want to run ``update_catalog_metadata_task`` for every (active) ``CatalogQuery``.
We can block until that is all done.  Once it’s done, the ``update_full_content_metadata_task`` should be invoked.
Finally, once we have the full metadata, invoke ``index_enterprise_catalog_courses_in_algolia``.

For the endpoint: the tricky part here is that we don’t know when we’re “done” with a burst of requests -
we might get 2 catalogs to update over the course of 2 seconds,
or we might get a sequence of 1000 requests over several minutes.
This is where the power of both a lock and a “countdown” come in handy.

* The ``update_full_content_metadata_task`` will no longer accept any arguments describing which ``ContentMetdata``
  records to update.  Instead, it will look for recently-modified records and do a full update of them.
* The task will now wait for any ``update_catalog_metadata_tasks`` that have started
  in a recent window of time to finish before starting.  If one such task is found
  in an unfinished state, this task will will raise a ``Retry`` exception (and check for running, prerequisite tasks
  again when the retry occurs).  The task will retry up to 5 times, with a 5 minute countdown/delay on the first
  retry, and a 10 minute countdown on subsequent retries.
* It will not execute more than once in a given time period.

Modify the Algolia reindexing task
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The motivations for the changes to ``update_full_content_metadata_task`` apply equally well to
``index_enterprise_catalog_courses_in_algolia`` - we want to combine the use of a lock/semaphore and
a retry/countdown to ensure that we're reindexing only what needs reindexing and not doing it too often.

* The Algolia reindexing task will no longer accept any arguments describing which ``ContentMetdata``
  records to re-index.  Instead, it will look for recently-modified records and rebuild the index for those records.
  For this task, "recently-modified" means "in the past two hours", because our daily cron schedule is configured
  to have the Algolia index update job run 2 hours after the job to update catalog metadata starts.
* The task will now wait for any ``update_full_content_metadata_tasks`` that have started
  in a recent window of time to finish before starting - we want a complete metadata record
  before updating it in our search index.  If one such task is found
  in an unfinished state, this task will will raise a ``Retry`` exception (and check for running, prerequisite tasks
  again when the retry occurs).  The task will retry up to 5 times, with a 5 minute countdown/delay on the first
  retry, and a 10 minute countdown on subsequent retries.
* It will not execute more than once in a given time period.

Consequences
------------

It's now harder to "force" run these tasks/jobs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We've backlogged some work to make these tasks accept a ``force`` argument which should cause
them to run even if they have run recently.  This supports both local development purposes
and unexpected production environment purposes.

The ``update_catalog_metadata_task`` still does "too much"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We should make this task more granular by having it deal only with the association of
catalog queries to metadata records - it should **not** use metadata dictionaries
to populate the ``ContentMetadata.json_metadata`` field just because it is available from
``/api/v1/search/all``.  Instead, this task should use ``/api/v1/search/all`` as the
source-of-truth about which content keys belong to which ``CatalogQuery`` records, and then stop.

The ``update_full_content_metadata_task`` should rely on course-discovery's ``/api/v1/{courses,coureruns,programs}``
endpoints to fetch the full metadata of our ``ContentMetadata`` records.

We've backlogged work to actualize this.

Old TaskResult records should be cleaned up
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These records only serve a functional purpose for around a day, due to the nature of the locking/retrying
described above.  They serve some purpose for the sake of debugging and observability beyond that,
but certainly after a point (say, three months), they become nearly useless.  We should periodically
delete old ``TaskResult`` instances.

We've backlogged work to actualize this.

References
----------

* `Detailed metadata tasks flowchart`_
* `Algolia indexing flowchart`_
* `Update/reindex mgmt commands flowchart`_


.. _Detailed metadata tasks flowchart: https://github.com/edx/enterprise-catalog/blob/master/docs/update-metadata-tasks-detailed-flowchart-2021-feb.png
.. _Algolia indexing flowchart: https://github.com/edx/enterprise-catalog/blob/master/docs/index-algolia-task-flowchart-2021-feb.png
.. _Update/reindex mgmt commands flowchart: https://github.com/edx/enterprise-catalog/blob/master/docs/update-content-metadata-mgmt-cmd-flowchart-2021-feb.png
