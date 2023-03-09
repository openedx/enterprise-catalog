Pivoting to Content Uuids as preferred primary identifiers
==========================================================

Status
------

Accepted

Context
-------
There is a lot of back and forth between Enterprise services relating to handling and consuming content. However
the ways in which content is identified by each system varies. Examples of this are (but are not limited to)-
course entitlements being tied to content UUIDs while course enrollments point to a course run, the Enterprise Service
storing and relying on content keys to identify content metadata objects, and Enterprise MFE's using aggregation key
to query Algolia. Now that the Enterprise Subsidy service is defining relations between transactions and content, we
need to decide on an common content identifier that will be recommended across Enterprise systems.


Decision
--------
The Enterprise approach to identifying content will shift towards-

1) Aggregation key will become deprecated; it’s a field computed by course-discovery for search purposes, but it’s not a
persisted field on any content metadata model/table.

2) Content UUID is added to the Enterprise Catalog service's Content Metadata table as a queryable field and is
extracted from Course Discovery's response payload at time of content ingestion in the Catalog Service.

3) Content UUID is the recommended primary content identifier for content types across the Enterprise product. However,
we will continue to support `content_key` from the key field of content metadata records in the Course Discovery service.

4) The Enterprise Catalog api serves as a central point of conversion between key and uuid content identification types used in
the enterprise product. The service will also allow for the discovery of an aggregation key by either `key` or `uuid` but will
not support querying by aggregation key.


Consequences
------------

Content key was previously considered to be Enterprise content's primary identifier. This pivot reverses past
decisions and means that work to implement `content_key` as a primary identifier will be halted. Importantly though,
this does not require a change to previous implementations, and provides an easily accessible conversion tool from
older identifiers to UUID. It does mean that the Enterprise Subsidy service, being central to many Enterprise systems,
will have to track both `content_key` and `content_uuid` so that it can more easily join content that has relied on the
past identifier in addition to areas that use the UUID field.

Alternatives considered
-----------------------

We considered pivoting to other existing content identifiers like aggregation key, as well as keeping the existing
pattern of using `content_key` as the primary identifier. However, the universality of UUID across all content types,
as well as the uniformity of the UUID format in said content types means UUID lends itself nicely as the preferred key.
As such, `content key` will be kept as a secondary identifier and supported where it's already in use. Furthermore,
it's valid for certain records to reference both identifiers if helpful, with little to no risk.
