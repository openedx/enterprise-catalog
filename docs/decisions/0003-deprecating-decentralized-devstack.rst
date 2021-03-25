==================================
Deprecating Decentralized Devstack
==================================


Status
------

Accepted

Context
-------

In `decision 0001`_ we considered replacing `Devstack`_ with Decentralized Devstack, a framework for devstack where each IDA would have and own its own devstack. To test out the new framework, a prototype was created for enterprise-catalog. After some user testing and some ideation, it was decided that edX would not try to move towads Decentralized Devstack and instead would opt to do improvements on `Devstack`_.

Decision
--------

Deprecated Decentralized Devstack prototype.

Consequences
------------

All files/changes related to implementation of Decentralized Devstack will be removed from enterprise-catalog.

.. _Devstack: https://github.com/edx/devstack
.. _decision 0001: https://github.com/edx/enterprise-catalog/blob/master/docs/decisions/0001-adding-lms-data-dump.rst
