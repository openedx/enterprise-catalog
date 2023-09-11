Normalized metadata across course types
=======================================

Status
------

Accepted

Context
-------

Course metadata is structured dependent on its course type. That is, certain attributes within the course metadata (e.g., dates) exist on a course run for Open Courses and within an `additional_metadata` field for Executive Education courses. This data discrepency makes it challenging for both business logic within the enterprise-catalog service and for downstream consumers of the service to reason about the data appropriately based on the course type. As a result, this could lead to misinterpretting whether dates are correct for a particular course as it's not evident which date sources should be used depending on which course type we're working with.

In the enterprise-catalog service, there is business logic that detects when dealing with an Executive Education course type and replaces the dates defined in the course run associated with the `advertised_course_run_uuid` with the dates defined on the top-level course record's `additional_metadata` attribute. While this ensures a consistent schema when reading dates across course types, it's not immediately evident that this business logic takes place; it's all too easy to assume the dates in the `advertised_course_run_uuid` are incorrect for Executive Education courses (need implicit knowledge about the enterprise-catalog service).

Decision
--------

To mitigate these concernbs, we introduced a `normalized_metadata` attribute on the JSON object stored for each `ContentMetadata` object in the database. Its purpose is to be a consistent schema across all course types (e.g., Open Courses and Executive Education) to improve clarity and reduce confusion around where certain metadata such as start/end dates should be pulled.

The `normalized_metadata` attribute will be exposed on all CRUD APIs in enterprise-catalog when surfacing JSON metadata about a course. The `normalized_metadata` attribute will also be indexed in Algolia such that the already-transformed course metadata is available to clients such as micro-frontends when displaying search results.


Consequences
------------

By adding `normalized_metadata`, we are introducing some conflicting strategies around parsing dates across course types (e.g., Open Course vs. Executive Education) in the short term. For example, when we determine whether a course's registration deadline has passed, we continue to parse the disparate data sources depending on the course type (i.e., if an Open Course, use advertised course run data; if an Executive Education course, use `additional_metadata` data).

Similarly, when we update the `ContentMetadata` records with full metadata from course-discovery for Executive Education courses, we still override the dates for the advertised course run from the dates specified in `additional_metadata`. While this mostly leads to being able to pull dates from the advertised course run across both Open Courses and Executive Education courses, it leads to confusion around whether the dates have been transformed and their accuracy since this business logic is not necessarily evident to consumers.

The decision to introduce a `normalized_metadata` attribute does not intend to immediately change existing business logic as described above. That is, this decision intends to be additive only such that these other places can be adapted incrementally over time as consuming clients and users likely rely on the current structure of these data today.


Alternatives considered
-----------------------

We considered updating existing business logic to rely solely on the newly added `normalized_metadata` attribute. However, this was deferred in favor of making these changes additive-only. This deferral was to de-risk the work for existing implementations and applications that consume these data as they exist today.
