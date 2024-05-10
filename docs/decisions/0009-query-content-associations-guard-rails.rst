Query Content Associations Guard Rails
======================================

Status
------

Accepted

Context
-------
We have on occasion seen moments where Discovery has reported an extreme number of incorrect content records associated
with customer queries. Almost entirely in these situations we have seen the system right itself after some time and
return the expected number of records. While ensuring for normal variance and content modification rates, we want to
catch and prevent moments where Discovery or other sources of truth erroneously reports an extreme loss or gain of
content associated with a query.

Decision
--------
The ``associate_content_metadata_with_query`` method will now consider the size of the existing query/content
association list as compared to the list of content to update to. Should the content association update surpass a
configurable threshold, the update to the content associations will be blocked and the old state will be retained.

To be considered for a threshold cutoff, the requester of ``associate_content_metadata_with_query`` must meet the
following criteria:
- The existing set of content associations must exceed a configurable cutoff
- The query must have not been modified today
- The change in number of content association records must exceed a configurable percentage, both in a positive and
negative direction (ie the query loses or gains more than x% of its prior number of records)

Consequences
------------
Content associations will not be updated in specific cases, causing stagnant data to be displayed to customers. The
guardrail is also not loud/destructive in that it will log a warning about its action but not stop the process, just
returning the existing content metadata association set. However, given the high levels of the thresholds set, it is
intended that this only happens when the alternative of letting the content association update going through would be
more disruptive to the customer's experience than to continue using old data. It is also intended that the check on the
``modified`` field value will ensure there is a direct and easy way to allow a large content associations update to go
through.
