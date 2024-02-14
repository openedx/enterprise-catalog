Incremental Content Metadata Updating
=====================================


Status
------
Draft


Context
-------
The Enterprise Catalog Service implicitly relies on external services as sources of truth for content surfaced to
organizations within the suite of enterprise products and tools. For the most part this external source of truth has
been assumed to be the `course-discovery` service. The ``update_content_metadata`` job has relied on `course-discovery`
to not only expose the content metadata of courses, programs and pathways but also to determine customer catalog
associations with specific subsets of content, meaning enterprise curated content filters are evaluated externally as a
black box solution to what content belongs to which customers. This is burdensome to both the catalog service as it has
little control over how the underlying content filtering logic functions and to the external service as redundant data
must be requested for each and every query filter. Should the catalog service own the responsibility of determining the
associations between a single piece of content and any of the customers' catalogs, not only would we just have to
request all data a single time from external sources for bulk jobs, but we could also easily support creation, updates
and deletes of single pieces of content communicated to the catalog service on an individual basis.

Decision
--------
The existing indexing process begins with executing catalog queries against `search/all` to determine which
courses exist and belong to which catalogs. In order for incremental updates to work we first need to provide the
opposite semantic and instead be able to determine catalog membership from a given piece of content (rather than
courses from a given catalog). We can make use of the new `apps.catalog.filters` python implementation which can take a
catalog query and a piece of content metadata and determine if the content matches the query (without the use of course
discovery).

We will implement a two sided approach to content updating that will be introduced as parallel work to existing
``update_content_metadata`` tasks and can eventually replace old infrastructure. The first method will be a bulk
job similar to the current ``update_content_metadata`` task to query external sources of content and update any records
should they mismatch using `apps.catalog.filters` to determine the query-content association sets. And second, an event
signal receiver which will process any individual content update events that are received. The intention is for the
majority of updates in the catalog service to happen at the moment they are updated in their external source and the
signal is fired, only to be cleaned up and verified by the bulk job later on should something go wrong.

While this new process will remove the need to constantly query and burden the `course-discovery` search/all endpoint
we will still most likely need to request the full metadata of each course/content object similar to how the current
task handles the flow.

An event receiver based approach to individual content updates also opens up our possibilities to ingesting content
from other sources of truth that are hooked up to the edx event-bus. This means that it will be easier for enterprise
to ingest content from many sources, instead of relying on those services first going through course-discovery.


Consequences
------------
As alluded to earlier, this change means that we will no longer have to repeatedly request data from course-discovery's
search/all endpoint as we won't need to rely on the service to do our filtering logic, which was one of the main
contributing factors as to the long run time of the ``update_content_metadata`` task. Additionally, housing
our own filtering logic will allow us to maintain and tweak/improve upon the functionality should we want additional
features.

The signal based individual updates will also mean that we will have a significantly smaller window of lag for content
updates propagating throughout the enterprise system.


Alternatives Considered
-----------------------
There are a number of ways that individual content updates could be communicated to the catalog service. Event-bus
based signal handling restricts the catalog service to sources of truth that have integrated with the event bus
service/software. We considered instead exposing an api endpoint that would take in a content update event and process
the data as needed, however it was decided that this approach is brittle and prone to losing updates in transit as
it would be difficult to ensure the update was fully communicated and processed by the catalog service should anything
go wrong.
