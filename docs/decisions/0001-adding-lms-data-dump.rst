Adding lms data dump
====================

Status
------

Accepted

Context
-------

Enterprise-catalog will be one of the first services to test Decentralized Devstack (DD). One of the goals for DD is to minimize or even eliminate the need to run any migrations in lms to develop in enterprise-catalog. To do this, we decided to use premade data dumps on necessary data for lms.

Since this is the begining of DD, the methods of providing necessary data to a general service's DD has not been established. A generalized solution has been proposed in `OEP-37`_, but it does not yet exist.

.. _OEP-37: https://github.com/edx/open-edx-proposals/pull/118


Decision
--------

In lieu of general method to provide data and in need to develop and test quickly, we've decided to place necessary lms mongo and sql data dumps in /lms_mongo_dump directory. The hope is to use this temporary data dump for testing and if this method proves promising, develop a more general solution for providing data.

Consequences
------------

The lms data dump will live in enterprise-catalog git repository.
