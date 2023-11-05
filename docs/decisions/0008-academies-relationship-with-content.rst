Academies relationship with content libraries
=============================================

Status
------

Draft


Context
-------
Academies are off the shelf, subject-specific curations of the edX/2U catalog and a variety of services to create
a more transformative, focused, rigorous learning experience within a specific vertical. Where academies differ
from content libraries(e.g. edX/2u catalog) is their scope and focus. Academies are a larger investment made by
a company that is committed to developing a specific set of core competencies within its workforce as a
competitive advantage. Examples of the types of features that could separate an academy from a content library
include (but are not limited to):

-- Coaching.
-- Pre- and post-test competency assessments.
-- Projects / capstones.
-- Events.
-- Multiple varieties of content: courses, programs, videos, articles.
-- Cohort/group experiences.

We will build a series of features that an Academy can support, with the tooling to turn features on and off.
From a market-facing perspective, this will allow us to deliver two distinct looking offerings: a basic,
“off the shelf” academy that can be supplied to any standard contract, and a “premium” academy that appeals to
customers looking to run more comprehensive programs and spend much more per learner.


Solution Approach
-----------------
The Academy will have the following broad software modules:

1: A metadata component to define the edx learning content membership in an Academy.
2: A progress component to track learner progress in an Academy. 
3: An event management suite for scheduling, managing academy related events.

All of the above will have associated user facing and backend systems. As part of MVP, the first module above
will be developed.


Decision
--------
From a code perspective, an Academy has many similarities to how an Enterprise is stored and managed.
The Enterprise Catalog service has a lot of code for associating enterprises with learning content and
creating indexes in Algolia. Academies can reuse all of this body of work already present in the enterprise-catalog. 

Each Academy will have a many-to-many relationship to the enterprise catalogs. A many-to-many relationship is
necessary since academies can span enterprises and catalogs. Academy uuids will get indexed into
Algolia via the existing indexing routines in enterprise-catalog repository


Consequences
------------

A large amount of Algolia indexing code in the enterprise-catalog repository will be reused, thus reducing the
time to market. This also entails a tight coupling to the enterprise catalog. 


Alternatives considered
-----------------------

We considered adding Academies to the edx-discovery search, similar to what was implemented for Pathways. We also
looked at creating a many to many relationship of an Academy and CatalogQuery. Creating a brand new edx-Academies
service was also evaluated. All of these approaches trigger significant complexity to the MVP. Once we are confident
that the MVP is a success and have a more refined path for the premium version of the product, we can re-evaluate
the above decision and consider these alternatives again.
