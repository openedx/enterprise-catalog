Allowing inclusion of exec ed content in Catalog Queries
========================================================

Status
------

Accepted (circa September 2022)

Context
-------

We currently do not allow course content with type ``executive-education-2u`` to be associated
with any ``CatalogQuery`` record (and therefore, no such content is included in any ``EnterpriseCatalog``).
This type of course is currently excluded from all catalogs, because there is not yet a
way to purchase or enroll in such courses from edX enterprise interfaces.
We'd like to selectively allow such content to be associated with queries/catalogs, with
the expectation that there *will soon* be a mechanism by which learners can make
subsidized purchases/enrollments in these courses.  See https://github.com/openedx/ecommerce/pull/3785 for
such a mechanism.

Decision
--------

We created a new field, ``CatalogQuery.include_exec_ed_2u_courses``, which when ``True`` for
a ``CatalogQuery`` record, indicates that course content with type ``executive-education-2u``
is allowed to be associated with that record (although it is in the purview of the record's ``content_filter``
to ensure that such courses are included in the ``CatalogQuery``).

To accomodate situations where two catalogs/queries want to include content from a common
``content_filter``, except one wants to exclude exec ed content (by setting include_exec_ed_2u_courses to False),
and the other wants to include such content (by setting the same field to ``True``), we changed
the unique constraint on the ``CatalogQuery`` model to be unique on the
``(content_filter_hash, include_exec_ed_2u_courses)`` fields.

Consequences
------------

``content_filter_hash`` alone is no longer enough to uniquely identify a ``CatalogQuery`` record.

Alternatives considered
-----------------------

We considered toggling the inclusion of executive education content based on a key
specified in the ``content_filter`` of a query.  We rejected this, because the ``content_filter``
is really a query sent to the search component of the course-discovery service, and we
disliked the idea of "jamming" extra meaning into that field.  We felt
it better to be as explicit as possible about toggling the inclusion of this content.
