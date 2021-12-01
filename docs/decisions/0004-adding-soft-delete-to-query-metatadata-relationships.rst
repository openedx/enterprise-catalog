====================================================
Adding Soft Delete to Query / Metadata relationships
====================================================


Status
------

Draft

Context
-------

There has been a customer feature request that requires has required us to start capturing the times at which content is dropped from catalog queries. This has lead us to designing a soft deletion manager for models.

Decision
--------

Create a reusable soft deletion queryset, manager and model. The new `SoftDeletionModel` can be added to any customized model and that model will have access to removed objects under the `<Model>.all_objects` manager (SoftDeletionManager). This manager retrieves either a query set (`SoftDeletionQuerySet`) filtering by `deleted_at=None` or simply returning all objects. The `SoftDeletionModel` will have an added hard_delete method for complete removing records.

Consequences
------------

Hard removing either FK from a many to many's custom through table that subclasses the `SoftDeletionModel`' must manually remove the records from the through model before removing the related objects.
