=====================================
Enterprise Catalog Architecture Guide
=====================================

.. contents:: Table of Contents
   :depth: 3
   :local:

Introduction
============

Enterprise Catalog is a Django-based microservice within the edX ecosystem that manages enterprise customer catalogs. It acts as an intermediary between enterprise customers and the course catalog, providing curated content based on enterprise-specific requirements and filters.

This service is designed to handle enterprise customers who need customized views of the edX course catalog, with features like content curation, search integration, and bulk content management.

Target Audience
===============

This document is written for developers who are:

- New to the edX ecosystem
- Working on Enterprise Catalog service
- Need to understand the service architecture and integrations
- Planning to extend or maintain the service

High-Level Service Purpose
==========================

Enterprise Catalog serves three main purposes:

1. **Content Curation**: Filter and organize course content for enterprise customers
2. **Catalog Management**: Associate enterprises with specific content collections
3. **Search Integration**: Provide search capabilities through Algolia integration

System Architecture Overview
=============================

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │                     edX Ecosystem                               │
    │                                                                 │
    │  ┌──────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
    │  │ LMS (edxapp)     │    │ Enterprise      │    │ Course      │ │
    │  │ ┌──────────────┐ │    │ Catalog Service │    │ Discovery   │ │
    │  │ │edx-enterprise│ │◄──►│                 │───>│ Service     │ │
    │  │ │  (library)   │ │    │                 │    │             │ │
    │  │ └──────────────┘ │    └─────────────────┘    └─────────────┘ │
    │  │                  │             ▲                             │
    │  └──────────────────┘             │                             │
    └─────────────────────────────────────────────────────────────────┘
                                       │
           ┌───────────────────────────────────────────────────────────┐
           │                Core Dependencies                          │
           │                                                           │
           │         ┌─────────────┐    ┌─────────────┐                │
           │         │   MySQL     │    │ Redis/      │                │
           │         │ Database    │    │ Celery      │                │
           │         │             │    │ Task Queue  │                │
           │         └─────────────┘    └─────────────┘                │
           └───────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                           ┌─────────────────────┐
                           │ External Services   │
                           │                     │
                           │ • Algolia Search    │
                           └─────────────────────┘

Core Components
===============

Django Applications Structure
-----------------------------

The service is organized into several Django applications, each with specific responsibilities:

.. code-block:: text

    enterprise_catalog/
    ├── apps/
    │   ├── catalog/          # Core catalog and content metadata models; core business logic
    │   ├── api/              # REST API endpoints (v1, v2)
    │   ├── api_client/       # External service integrations
    │   ├── curation/         # Content curation and highlights
    │   ├── ai_curation/      # AI-powered content recommendations
    │   ├── video_catalog/    # Video content metadata management
    │   ├── jobs/             # Enterprise jobs data integration
    │   ├── academy/          # Academy content metadata organization
    │   ├── core/             # Shared utilities and base models
    │   └── track/            # Analytics and tracking
    └── settings/             # Environment-specific configurations

Key Data Models
---------------

The service centers around these core models:

**EnterpriseCatalog**
  Associates enterprise customers with content filters and catalog queries

**CatalogQuery**
  Defines reusable content filtering rules using JSON-based parameters

**ContentMetadata**
  Local cache of course/program metadata from Discovery Service

**RestrictedCourseMetadata**
  Query-specific versions of courses with filtered restricted runs

**EnterpriseCatalogRoleAssignment**
  Manages user permissions for catalog operations

Django Models Relationship Diagram
-----------------------------------

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                         Core Catalog Models
    │
    │  ┌─────────────────┐              ┌─────────────────┐
    │  │  CatalogQuery   │              │EnterpriseCatalog│
    │  │                 │              │                 │
    │  │ • content_filter│◄─────────────│• catalog_query  │
    │  │ • uuid          │    1:many    │ • enterprise_   │
    │  │ • title         │              │   uuid          │
    │  │                 │              │ • title         │
    │  └─────────────────┘              │ • enabled_course│
    │           │                       │   _modes        │
    │           │                       └─────────────────┘
    │           │ many:many
    │           │
    │           ▼                       ┌─────────────────┐              ┌───────────
    │  ┌─────────────────┐              │RestrictedCourse │              │RestrictedRun
    │  │ ContentMetadata │              │ Metadata        │              │AllowedForRestricted
    │  │                 │              │                 │              │Course
    │  │ • content_key   │◄─────────────│• unrestricted_  │◄─────────────│
    │  │ • content_type  │    1:many    │  parent         │   many:many  │• course
    │  │ • parent_content│              │• catalog_query  │              │• run
    │  │   _key          │              │• content_key    │              │
    │  │ • json_metadata │              │• _json_metadata │              └───────────
    │  │                 │              │                 │
    │  └─────────────────┘              └─────────────────┘
    │           │                                 │
    │           │ self-referential                │
    │           │ many:many                       │
    │           │ (associated_content_metadata)   │
    │           ▼                                 ▼
    │  ┌─────────────────┐              ┌─────────────────┐
    │  │ ContentMetadata │              │ CatalogQuery    │
    │  │ (programs,      │              │                 │
    │  │  courses)       │              │                 │
    │  └─────────────────┘              └─────────────────┘
    └─────────────────────────────────────────────────────────────────────────────────


**Key Relationships:**

1. **EnterpriseCatalog ↔ CatalogQuery**: One-to-many (each catalog has one query, queries can be reused)

2. **CatalogQuery ↔ ContentMetadata**: Many-to-many (queries filter content, content can match multiple queries)

3. **ContentMetadata ↔ ContentMetadata**: Self-referential many-to-many for course-program associations

4. **RestrictedCourseMetadata ↔ ContentMetadata**: One-to-many (restricted version points to unrestricted parent)

5. **RestrictedCourseMetadata ↔ CatalogQuery**: Many-to-one (restricted versions are query-specific)

Normalized Metadata for Downstream Consumers
=============================================

Enterprise Catalog provides normalized metadata fields that are critical for
downstream consumers who need consistent data structures across different course types.

Background and Problem
-----------------------

Course metadata structure varies significantly depending on the course type:

- **Open Courses**: Date information (start, end, enrollment deadlines) exists within course run objects
- **Executive Education Courses**: Date information exists in the top-level course's ``additional_metadata`` field

This inconsistency creates challenges for downstream consumers:

1. **Business Logic Complexity**: Consumers need course-type-specific logic to extract basic information like dates
2. **Data Misinterpretation**: It's unclear which date sources are authoritative for different course types
3. **Implementation Burden**: Each consumer must implement their own normalization logic

Solution: Normalized Metadata Fields
------------------------------------

Enterprise Catalog automatically generates two normalized metadata fields for every course:

**normalized_metadata**
  A consistent schema at the course level that normalizes key fields across all course types

**normalized_metadata_by_run**
  A dictionary mapping each course run key to its normalized metadata, providing run-specific normalized data

Normalized Schema Structure
---------------------------

The normalized metadata includes standardized fields:

.. code-block:: json

    {
        "start_date": "2023-03-01T00:00:00Z",
        "end_date": "2023-04-09T23:59:59Z",
        "enroll_by_date": "2023-02-01T00:00:00Z",
        "content_price": 2900,
        "upgrade_deadline": "2023-02-15T23:59:59Z"
    }

**Field Descriptions:**

- ``start_date``: When the course/run begins
- ``end_date``: When the course/run concludes
- ``enroll_by_date``: Enrollment deadline
- ``content_price``: Normalized price (defaults to 0.0 for free content)
- ``upgrade_deadline``: Deadline for upgrading to paid track

Data Flow and Generation
------------------------

.. code-block:: text

    Course Discovery → Enterprise Catalog → Normalization Process
                           │
                           ▼
                    ┌─────────────────────────────────────────┐
                    │ NormalizedContentMetadataSerializer     │
                    │                                         │
                    │ Input:                                  │
                    │ • course_metadata (full course data)    │
                    │ • course_run_metadata (specific run)    │
                    │                                         │
                    │ Processing:                             │
                    │ • Detects course type (Open vs Exec Ed)│
                    │ • Extracts dates from appropriate       │
                    │   source (course_runs vs additional_   │
                    │   metadata)                             │
                    │ • Calculates normalized pricing        │
                    │ • Standardizes field names/formats     │
                    │                                         │
                    │ Output:                                 │
                    │ • normalized_metadata (course-level)    │
                    │ • normalized_metadata_by_run (per-run) │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │ ContentMetadata.json_metadata           │
                    │                                         │
                    │ {                                       │
                    │   "original_fields": "...",             │
                    │   "normalized_metadata": {...},         │
                    │   "normalized_metadata_by_run": {       │
                    │     "course-v1:edX+CS101+2023": {...},  │
                    │     "course-v1:edX+CS101+2024": {...}   │
                    │   }                                     │
                    │ }                                       │
                    └─────────────────────────────────────────┘

Consumer Benefits
-----------------

**1. Simplified Integration**
   Downstream consumers no longer need course-type-specific logic:

.. code-block:: javascript

    // Instead of this course-type-aware logic:
    function getStartDate(course) {
        if (course.course_type === 'executive-education-2u') {
            return course.additional_metadata?.start_date;
        } else {
            return course.advertised_course_run?.start;
        }
    }

    // Consumers can use consistent normalized fields:
    function getStartDate(course) {
        return course.normalized_metadata?.start_date;
    }

**2. Algolia Search Integration**
   Normalized metadata is indexed in Algolia, enabling:

   - Consistent filtering across course types
   - Simplified search result rendering
   - Unified faceting and sorting

**3. API Response Consistency**
   All Enterprise Catalog API responses include normalized metadata, providing:

   - Backwards compatibility (original fields preserved)
   - Forward compatibility (new normalized fields available)
   - Reduced client-side complexity

Data Flow Architecture
======================

Content Synchronization Flow
----------------------------

.. code-block:: text

    Discovery Service → Content Sync → Enterprise Catalog → Algolia Index
                           │
                           ▼
                    ┌─────────────────┐
                    │ Management      │
                    │ Commands        │
                    │                 │
                    │ • update_       │
                    │   content_      │
                    │   metadata      │
                    │                 │
                    │ • update_full_  │
                    │   content_      │
                    │   metadata      │
                    │                 │
                    │ • reindex_      │
                    │   algolia       │
                    └─────────────────┘

External Service Integrations
==============================

Course Discovery Service
-------------------------

**Purpose**: Source of truth for all course and program metadata

**Integration Pattern**:
- Pull-based synchronization via management commands
- RESTful API communication
- Periodic data refresh using management commands which can be run on schedules. Many invoke async celery tasks
  to execute business logic.

**Key Endpoints Used**:
- ``/api/v1/search/all/`` - Bulk content retrieval
- ``/api/v1/courses/`` - Individual course details
- ``/api/v1/programs/`` - Program information

LMS (edxapp/edx-platform)
---------------------------------

**Purpose**: User authentication and enterprise customer data

**Integration Pattern**:
- JWT token-based authentication
- Session-based user context
- Enterprise customer validation

edx-enterprise Library (within LMS)
------------------------------------

**Purpose**: Enterprise customer configuration and user management

**Integration Pattern**:
- Python library installed in LMS (edxapp)
- User-enterprise association validation
- Customer feature flag retrieval

Algolia Search Platform
-----------------------

**Purpose**: Fast search and content discovery

**Integration Pattern**:
- Content indexing via management commands
- Real-time search queries from frontend
- Faceted search and filtering

.. code-block:: text

    Content Updates → Algolia Indexing → Search Results
                          │
                          ▼
                   ┌─────────────────┐
                   │ Index Structure │
                   │                 │
                   │ • Courses       │
                   │ • Programs      │
                   │ • Learning      │
                   │   Paths         │
                   │ • Videos        │
                   └─────────────────┘

Celery Task Processing
----------------------

**Purpose**: Asynchronous task execution for data synchronization

**Task Types**:
- Content metadata synchronization
- Algolia index updates
- Bulk data processing
- Periodic maintenance tasks

Authorization and Permissions
=============================

The service implements AuthN and AuthZ via a combination of JWTs and edx-rbac

JWT-Based Authorization
-----------------------

**Source**: LMS authentication system
**Mechanism**: JWT tokens in HTTP cookies
**Scope**: Basic enterprise user validation

.. code-block:: text

    LMS Authentication → JWT Token → Enterprise Catalog Validation
                            │
                            ▼
                    ┌─────────────────┐
                    │ Token Contains: │
                    │                 │
                    │ • User ID       │
                    │ • Enterprise ID │
                    │ • Roles         │
                    │ • Permissions   │
                    └─────────────────┘

Role-Based Access Control (RBAC)
---------------------------------

**Source**: Enterprise Catalog internal system
**Mechanism**: ``EnterpriseCatalogRoleAssignment`` model
**Scope**: Fine-grained permission control

**Available Roles**:
- ``enterprise_catalog_admin`` - Full catalog management
- ``enterprise_catalog_learner`` - Read-only access
- ``enterprise_openedx_operator`` - Cross-enterprise operations

Deployment Architecture
=======================

Container Architecture
-----------------------

The local service runs in a containerized environment:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │                     Docker Environment                          │
    │                                                                 │
    │  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
    │  │ Enterprise      │    │ Celery Worker   │    │ MySQL        │ │
    │  │ Catalog Web     │    │ Container       │    │ Database     │ │
    │  │ Container       │    │                 │    │              │ │
    │  │                 │    │ • Task          │    │              │ │
    │  │ • Django App    │    │   Processing    │    │              │ │
    │  │ • Gunicorn      │    │ • Content Sync  │    │              │ │
    │  │ • Static Files  │    │ • Indexing      │    │              │ │
    │  └─────────────────┘    └─────────────────┘    └──────────────┘ │
    │                                                                 │
    │  ┌─────────────────┐                                            │
    │  │ Redis Container │                                            │
    │  │                 │                                            │
    │  │ • Celery Broker │                                            │
    │  │ • Task Queue    │                                            │
    │  │ • Result Store  │                                            │
    │  └─────────────────┘                                            │
    └─────────────────────────────────────────────────────────────────┘

Development Workflow
====================

Key Development Commands
------------------------

**Content Management**:

.. code-block:: bash

    # Sync content from Discovery Service
    ./manage.py update_content_metadata --force

    # Update Algolia search index
    ./manage.py reindex_algolia --force

    # Apply database migrations
    ./manage.py migrate

**Testing and Quality**:

.. code-block:: bash

    # Run full test suite
    make test

    # Code quality checks
    make quality

    # Complete validation
    make validate

API Structure
=============

The service exposes RESTful APIs, here are several top-level entities it exposes:

- ``/enterprise-catalogs/`` - Catalog CRUD operations
- ``/enterprise-customer/`` - Customer-specific catalog views
- ``/catalog-queries/`` - Content filter management
- ``/content-metadata/`` - Content information retrieval

Common Integration Patterns
============================

Content Filtering
------------------

Enterprise catalogs use JSON-based content filters:

.. code-block:: json

    {
        "content_type": ["course", "program"],
        "partner": ["edx"],
        "level_type": ["Beginner", "Intermediate"],
        "availability": ["Current", "Starting Soon"]
    }

Troubleshooting Guide
=====================

Common Issues
-------------

**Content Not Updating**:
1. Check Celery worker logs: ``make worker-logs``
2. Verify Discovery Service connectivity
3. Run manual sync: ``./manage.py update_content_metadata --force``

**Search Results Empty**:
1. Check Algolia index status
2. Verify catalog query filters
3. Rebuild index: ``./manage.py reindex_algolia --force``

**Permission Denied**:
1. Verify JWT token validity
2. Check role assignments in admin
3. Confirm enterprise customer association
