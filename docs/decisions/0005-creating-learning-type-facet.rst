Grouping and indexing of content and course type
================================================

Status
------

Pending (December 2022)

Context
-------

There exists a disconnect between what product and ux want for enterprise content categorization, and what exists
today in enterprise's source of truth (the Discovery Service). Currently, Executive Education is grouped with other edX
course content under the same content type (course), while programs and pathways hold seperate values. This contradicts
the mocks, ACs and visions for the enterprise product suite, where customers have access to all distinct learning types.
We would like to maintain our current system of categorization while also allowing Executive Education content to be a
faceted value of content in Algolia, without breaking any existing dependencies on the content_type facet.

Decision
--------

We create a new indexed and faceted field in algolia, ``learning_type``, which will act very similar to Discovery's
`content_type`. However `learning_type` will allow for the enterprise team to account for situations like this; where there
in a sub-grouping of content that needs to be surfaced to users along side the parent `content_type` groupings.

Consequences
------------

Further bloating Algolia data. Rule of developing universal standards (https://xkcd.com/927/).

Alternatives considered
-----------------------

We considered instead of creating a new faceted field, to override the `content_type` Algolia field for Executive Education courses
but chose to forego that option as to not run the risk of changing requirements/behaviors for consumers of the existing field.