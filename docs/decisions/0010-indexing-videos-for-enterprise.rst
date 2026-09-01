Indexing videos for search and driving enrollments
==================================================

Status
------

Draft


Context
-------
Microlearning, broadly defined, are short form educational experiences (<30 minutes) that are designed to deliver against a specific learning objective while minimizing learner fatigue. The scope of this decision record is a microlearning experience that focuses on videos. The videos will be utilized to market the associated course to prospective learners and help drive enrollments, which will eventually result in an increase of revenue.


Solution Architecture
---------------------
The videos will be indexed in Algolia for discoverability via search in the Enterprise Learner Portal. Since the video-course relationship resides in lms (edx-platform), api clients will be used to pull that information into enterprise-catalog, similar to how it is done for video skill tagging (https://github.com/openedx/course-discovery/blob/a0124cae632d44300f479ae59850499c4b7b6809/course_discovery/apps/taxonomy_support/providers.py#L254). Once pulled into enterprise-catalog, the video metadata will be stored as a new app "video_catalog" (https://github.com/openedx/enterprise-catalog/tree/master/enterprise_catalog/apps). This new app will be responsible for 3 primary tasks: firstly to pull and store video metadata from lms, secondly to generate Algolia sized text summary of video transcripts using generative AI and finally to interact with existing Algolia indexing routines to add the video as a full-fledged Algolia object similar to courses, programs and pathways.


Decision
--------
Video catalog is an enterprise catalog and should reside within the Enterprise Catalog service. Video and course metadata relationships can be easily managed while existing indexing routines in enterprise-catalog repository can be reused.


Consequences
------------

A large amount of Algolia indexing code in the enterprise-catalog repository will be reused, thus reducing the
time to market. This also entails a tight coupling to the enterprise catalog. 


Alternatives considered
-----------------------

We considered adding Videos to the edx-discovery search, similar to what is implemented for Courses, Programs and Pathways. Since, this feature is enterprise specific, we did not see much benefit in adding the extra Discovery hop, which could trigger significant complexity due to another layer of indexing in elasticsearch.
