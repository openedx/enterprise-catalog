Incremental Algolia Indexing
============================


Status
------
Draft


Context
-------
The Enterprise Catalog Service produces an Algolia-based search index of its Content Metadata and Course Catalog
database. This index is entirely rebuilt at least nightly, working off a compendium of content records
resulting in a wholesale replacement of the prior Algolia index. This job is time consuming and memory intensive.
This job also relies heavily on separate but required processes responsible for retrieving filtered subsets of
content from external sources of truth, primarily Course Discovery, where synchronous tasks must be regularly
run in specific orders. This results in a system that is brittle - either entirely successful or entirely unsuccessful.


Solution Approach
-----------------
The goals should include:
- Implement new tasks that run alongside/augment the existing indexer until we’re able to entirely cut-over
- Support all current metadata types but doesn’t need to support them all on day 1
- Support multiple methods of triggering: event bus, on-demand from django admin, on a schedule, from the existing
update_content_metadata job, etc.
    - Invocation of the new indexing process should not be reliant on separate processes run synchronously before hand.
- Higher parallelization factor, i.e. 1 content item per celery task worker (and no task group coordination required)
- Provide a content-oriented method of determining content catalog membership that's not reliant on external services.


Decision
--------
We want to follow updates to content with individual and incremental updates to Algolia. To do this we both create
new functionality and reuse some existing functionality of our Algolia indexing infrastructure.

First is to address the way in which and the moments when we choose to invoke the process of indexing. Previously,
the bulk indexing logic was reliant on a completely separate task synchronously completing. In order to bulk index,
content records needed to be bulk updated. The update_content_metadata job's purpose is two fold, one is to ingest content
metadata from external service providers and standardize its format and enterprise representation, and two is to
build associations between said metadata records and customer catalogs by way of catalog query inclusion. Once this
information is entirely read and saved within the catalog service, the system is then ready to snapshot the state of
content in the form of algolia objects and entirely rebuild and replace our algolia index.

This first A then B approach to wholesale rebuilding our indices is both time and resource intensive as well as brittle
and prone to outages. Not to mention the system is slow to fix should a partial or full error occur, as
everything must be rerun in a specific order.

To remediate these symptoms, indexing content records will be dealt with on an individual object-shard/content metadata
object basis and will happen at the moment a record is saved to the ContentMetadata table. Tying the indexing process
to the model ``post_save()`` will decouple the task from any other time consuming, bulk job. In order to combat
redundant/unneeded requests, the record will be evaluated on two levels before an indexing task is kicked off. First
the contents metadata (modified_at) must be bumped from what's previously stored. Secondly, the content must have
associations with queries within the service.

In order to incrementally update the Algolia index we need to introduce the ability to replace individual
object-shard documents in the index (today we just replace the whole index). This can be implemented by creating
methods to determine which Algolia object-shards exist for a piece of content. Once we have relevant IDs we are able to
determine if a create, update, or delete of them is required and can highjack existing processes that bulk construct
our algolia objects except on an individual basis. For simplicity sake an update will likely be a delete followed by
the creation of new objects.

Incremental updates, through the act of saving individual records, will need to be triggered by something - such as
polling of updated content from Course Discovery, consumption of event-bus events, and/or triggering based on a nightly
Course Discovery crawl or Django Admin button. However it is not the responsibility of the indexer, nor this ADR
to determine when those events should occur, and in fact the indexing process should be able to handle any source of
content metadata record updating processes.


Consequences
------------
Ideally this incremental process will allow us to provide a closer to real-time index using fewer resources. It will
also provide us with more flexibility about including non-course-discovery content in catalogs because we will
no-longer rely on a query to course-discovery's `search/all` endpoint and instead rely on the metadata records in the
catalog service, regardless of it's source.


Alternatives Considered
-----------------------
No alternatives were considered.
