import collections
import json
from logging import getLogger
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext as _
from edx_rbac.models import UserRole, UserRoleAssignment
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.api.v1.utils import (
    get_enterprise_utm_context,
    update_query_parameters,
)
from enterprise_catalog.apps.api_client.discovery_cache import (
    CatalogQueryMetadata,
)
from enterprise_catalog.apps.api_client.enterprise_cache import (
    EnterpriseCustomerDetails,
)
from enterprise_catalog.apps.catalog.constants import (
    ACCESS_TO_ALL_ENTERPRISES_TOKEN,
    CONTENT_TYPE_CHOICES,
    COURSE,
    PROGRAM,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.utils import (
    get_content_filter_hash,
    get_content_key,
    get_content_type,
    get_parent_content_key,
    get_sorted_string_from_json,
)


LOGGER = getLogger(__name__)


class CatalogQuery(models.Model):
    """
    Stores a re-usable catalog query.

    .. no_pii:
    """

    content_filter = JSONField(
        blank=False,
        null=False,
        default=dict,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "Query parameters which will be used to filter the discovery service's search/all "
            "endpoint results, specified as a JSON object."
        )
    )
    content_filter_hash = models.CharField(
        null=True,
        unique=True,
        max_length=32,
        editable=False,
    )

    class Meta:
        verbose_name = _("Catalog Query")
        verbose_name_plural = _("Catalog Queries")
        app_label = 'catalog'

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.content_filter_hash = get_content_filter_hash(self.content_filter)
        super().save(*args, **kwargs)

    def pretty_print_content_filter(self):
        """
        Prints the content filter in an indented, more easily readable format.
        """
        return json.dumps(self.content_filter, indent=4)

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "CatalogQuery with content_filter_hash '{content_filter_hash}' "
            "and content_filter '{content_filter}'>".format(
                content_filter_hash=self.content_filter_hash,
                content_filter=self.pretty_print_content_filter(),
            )
        )


class EnterpriseCatalog(TimeStampedModel):
    """
    Associates a stored catalog query with an enterprise customer.

    .. no_pii:
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
    )
    title = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    enterprise_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
    )
    enterprise_name = models.CharField(
        max_length=255,
        blank=True,
    )
    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=True,
        related_name='enterprise_catalogs',
        on_delete=models.deletion.SET_NULL,
    )
    enabled_course_modes = JSONField(
        default=json_serialized_course_modes,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_('Ordered list of enrollment modes which can be displayed to learners for course runs in'
                    ' this catalog.'),
    )
    publish_audit_enrollment_urls = models.BooleanField(
        default=False,
        help_text=_(
            "Specifies whether courses should be published with direct-to-audit enrollment URLs."
        ),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Enterprise Catalog")
        verbose_name_plural = _("Enterprise Catalogs")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<EnterpriseCatalog with UUID '{uuid}' "
            "for EnterpriseCustomer '{enterprise_uuid}'>".format(
                uuid=self.uuid,
                enterprise_uuid=self.enterprise_uuid
            )
        )

    @property
    def content_metadata(self):
        """
        Helper to retrieve the content metadata associated with the catalog.

        Returns:
            Queryset: The queryset of associated content metadata
        """
        if not self.catalog_query:
            return ContentMetadata.objects.none()
        return self.catalog_query.contentmetadata_set.all()

    def contains_content_keys(self, content_keys):
        """
        Determines whether content_keys are part of the catalog.

        Return True if catalog contains the courses, course runs, and/or programs specified by
        the given content key(s), else False.

        A content key is considered contained within the catalog when:
          - associated metadata contains the specified content key.
          - associated metadata contains the specified content key as a parent (to handle when
            a catalog only contains course runs but a course id is searched).
          - associated metadata contains the specified content key in a nested course run (to
            handle when a catalog only contains courses but a course run id is searched).
        """
        # cannot determine if specified content keys are part of catalog when catalog
        # query doesn't exist or no content keys are provided.
        if not self.catalog_query or not content_keys:
            return False

        content_keys = set(content_keys)

        # construct a query on the associated catalog's content metadata to return metadata
        # where content_key and parent_content_key matches the specified content_keys to
        # handle the following cases where the catalog:
        #   - contains courses and the specified content_keys are course ids
        #   - contains course runs and the specified content_keys are course ids
        #   - contains course runs and the specified content_keys are course run ids
        #   - contains programs and the specified content_keys are program ids
        query = Q(content_key__in=content_keys) | Q(parent_content_key__in=content_keys)

        # retrieve content metadata objects for the specified content keys to get a set of
        # parent content keys, i.e. course ids associated with the specified content_keys
        # (if any) to handle the following case:
        #   - catalog contains courses and the specified content_keys are course run ids.
        searched_metadata = ContentMetadata.objects.filter(content_key__in=content_keys)
        parent_content_keys = {
            metadata.parent_content_key
            for metadata in searched_metadata
            if metadata.parent_content_key
        }
        query |= Q(content_key__in=parent_content_keys)

        # if the filtered content metadata exists, the specified content_keys exist in the catalog
        return self.content_metadata.filter(query).exists()

    def get_content_enrollment_url(self, content_resource, content_key, parent_content_key):
        """
        Return enterprise content enrollment page url with the catalog information for the given content key.

        If the enterprise customer's Learner Portal (LP) is enabled, the LP course page URL is returned.

        Arguments:
            content_resource (str): The content resource to use in the URL (i.e., "course", "program")
            content_key (str): The content key for the course to be displayed.
            parent_content_key (str): The content key for the course that is parent of the given course run key.
                                      This argument will be None if a course or program key is passed.

        Returns:
            (str): Enterprise landing page URL OR Enterprise Learner Portal course page URL.
        """
        if not (content_key and content_resource):
            return None

        params = get_enterprise_utm_context(self.enterprise_name)
        if self.publish_audit_enrollment_urls:
            params['audit'] = 'true'

        enterprise_customer = EnterpriseCustomerDetails(self.enterprise_uuid)
        learner_portal_enabled = enterprise_customer.learner_portal_enabled
        if learner_portal_enabled and content_resource is not PROGRAM:
            # parent_content_key is our way of telling if this is a course run
            # since this function is never called with COURSE_RUN as content_resource
            if parent_content_key:
                course_key = parent_content_key
                # adding course_run_key to the params for rendering the correct info
                # on the LP course page and enrolling in the intended course run
                params['course_run_key'] = content_key
            else:
                course_key = content_key
            url = '{}/{}/course/{}'.format(
                settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL,
                enterprise_customer.slug,
                course_key
            )
        else:
            # Catalog param only needed for legacy (non-LP) enrollment URL
            params['catalog'] = self.uuid
            url = '{}/enterprise/{}/{}/{}/enroll/'.format(
                settings.LMS_BASE_URL,
                self.enterprise_uuid,
                content_resource,
                content_key,
            )

        return update_query_parameters(url, params)

    def get_xapi_activity_id(self, content_resource, content_key):
        """
        Return enterprise xAPI activity identifier with the catalog information
        for the given content key.  Note that the xAPI activity identifier is a
        well-formed IRI/URI but not necessarily a resolvable URL.

        Arguments:
            content_resource (str): The content resource to use in the URL (i.e., "course", "program")
            content_key (str): The content key for the course to be displayed.

        Returns:
            (str): Enterprise landing page url.
        """
        if not content_key or not content_resource:
            return None
        xapi_activity_id = '{}/xapi/activities/{}/{}'.format(
            settings.LMS_BASE_URL,
            content_resource,
            content_key,
        )
        return xapi_activity_id


class ContentMetadata(TimeStampedModel):
    """
    Stores the JSON metadata for a piece of content, such as a course, course run, or program.
    The metadata is retrieved from the Discovery service /search/all endpoint.

    .. no_pii:
    """

    content_key = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        help_text=_(
            "The key that represents a piece of content, such as a course, course run, or program."
        )
    )
    content_type = models.CharField(
        max_length=255,
        choices=CONTENT_TYPE_CHOICES,
        blank=False,
        null=False,
    )
    parent_content_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=_(
            "The key that represents this content's parent, such as a course or program."
        )
    )
    json_metadata = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "The metadata about a particular piece content as retrieved from the discovery service's search/all "
            "endpoint results, specified as a JSON object."
        )
    )
    catalog_queries = models.ManyToManyField(CatalogQuery)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Content Metadata")
        verbose_name_plural = _("Content Metadata")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<ContentMetadata for '{content_key}'>".format(
                content_key=self.content_key
            )
        )


def content_metadata_with_type_course():
    """
    Find all ContentMetadata records with a content type of "course".
    """
    content_metadata = ContentMetadata.objects.filter(content_type=COURSE)

    if not content_metadata:
        LOGGER.error('There are no ContentMetadata records of content type "%s".', COURSE)
        return None

    return content_metadata


def associate_content_metadata_with_query(metadata, catalog_query):
    """
    Creates or (possibly) updates a ContentMetadata object for each entry in `metadata`,
    and then associates that object with the `catalog_query` provided.
    Only updates an existing ContentMetadata object if its `json_metadata` field
    differs from the data provided in `metadata`.

    Arguments:
        metadata (list): List of content metadata dictionaries.
        catalog_query (CatalogQuery): CatalogQuery object

    Returns:
        list: The list of content_keys for the metadata associated with the query.
    """
    metadata_list = []
    for entry in metadata:
        content_key = get_content_key(entry)
        defaults = {
            'content_key': content_key,
            'json_metadata': entry,
            'parent_content_key': get_parent_content_key(entry),
            'content_type': get_content_type(entry),
        }

        try:
            existing_metadata = ContentMetadata.objects.get(content_key=content_key)
        except ContentMetadata.DoesNotExist:
            existing_metadata = None

        if existing_metadata:
            if get_sorted_string_from_json(entry) == get_sorted_string_from_json(existing_metadata.json_metadata):
                # Only update the existing ContentMetadata object if its json has changed,
                # but still associate it with the query
                metadata_list.append(existing_metadata)
                continue

            for key, value in defaults.items():
                setattr(existing_metadata, key, value)
            existing_metadata.save()
        else:
            existing_metadata = ContentMetadata.objects.create(**defaults)

        metadata_list.append(existing_metadata)

    # Setting `clear=True` will remove all prior relationships between
    # the CatalogQuery's associated ContentMetadata objects
    # before setting all new relationships from `metadata_list`.
    # https://docs.djangoproject.com/en/2.2/ref/models/relations/#django.db.models.fields.related.RelatedManager.set
    catalog_query.contentmetadata_set.set(metadata_list, clear=True)
    associated_content_keys = [metadata.content_key for metadata in metadata_list]
    return associated_content_keys


class EnterpriseCatalogFeatureRole(UserRole):
    """
    User role definitions specific to Enterprise Catalog.
     .. no_pii:
    """

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return f"EnterpriseCatalogFeatureRole(name={self.name})"

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class EnterpriseCatalogRoleAssignment(UserRoleAssignment):
    """
    Model to map users to an EnterpriseCatalogFeatureRole.
     .. no_pii:
    """

    role_class = EnterpriseCatalogFeatureRole
    enterprise_id = models.UUIDField(blank=True, null=True, verbose_name='Enterprise Customer UUID')

    def get_context(self):
        """
        Return the enterprise customer id or `*` if the user has access to all resources.
        """
        if self.enterprise_id:
            # converting the UUID('ee5e6b3a-069a-4947-bb8d-d2dbc323396c') to 'ee5e6b3a-069a-4947-bb8d-d2dbc323396c'
            return str(self.enterprise_id)
        return ACCESS_TO_ALL_ENTERPRISES_TOKEN

    @classmethod
    def user_assignments_for_role_name(cls, user, role_name):
        """
        Returns assignments for a given user and role name.
        """
        return cls.objects.filter(user__id=user.id, role__name=role_name)

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "EnterpriseCatalogRoleAssignment(name={name}, user={user})".format(
            name=self.role.name,  # pylint: disable=no-member
            user=self.user.id,
        )

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class TaskLock(TimeStampedModel):
    """
    A model which indicates if a task with some name is "locked" from re-execution
    on some "key" (key ~= input, but not necessarily the exact args list) for some time period.
    Really meant for celery tasks, though it doesn't _have_ to be a celery task.

    ex. I have a task named "all_of_the_things()" and it does a lot of work.
    Calling `all_of_the_things('books')` will give me all of the things about books.
    Sometimes, a series of `all_of_the_things('books')` invocations might occur over a short time period,
    say, 12 invocations in the span of 2 minutes.  But each of those 12 invocations are likely to have
    the same side-effect and output.  So I'd really like the first invocation to get a lock for say, 60 minutes,
    so that any of the remaining invocations of `all_of_the_things('books')` are not excuted
    in that 60 minute window.

    At the start of the `all_of_the_things()` method body, I could do something like:

    if not TaskLock.acquire(
        task_name='all_of_the_things',
        task_id=self.id,
        lock_key='books',
        lock_expires_at=datetime.utcnow() + datetime.timedelta(hours=1),
    ):
        print('Lock already acquired, not doing anything')
        return
    ...
    """

    # Which task/function are we locking?
    task_name = models.CharField(max_length=255, db_index=True)

    # What is the key that we're locking on?
    lock_key = models.CharField(max_length=1023, db_index=True)

    # What was the identifier of the acquiring task?
    acquiring_task_id = models.CharField(max_length=255, db_index=True)

    # When does the lock expire?
    lock_expires_at = models.DateTimeField(blank=True, null=True, default=datetime.utcnow, db_index=True)

    @classmethod
    def acquire(cls, task_name, lock_key, acquiring_task_id, , expires_at):
        """
        find any unexpired locks for this (task, key), if one exists, return False.
        If there aren't any, acquire the lock with a new TaskLock record and return True.
        """
        if cls.objects.filter(
            task_name=task_name,
            lock_key=lock_key,
            lock_expires_at__gte=datetime.utcnow(),
        ).exists():
            return False

        cls.objects.create(
            task_name=task_name,
            lock_key=lock_key,
            acquiring_task_id=acquiring_task_id,
            lock_expires_at__gte=datetime.utcnow(),
        )
        return True


def update_contentmetadata_from_discovery(catalog_query):
    """
    Takes a CatalogQuery, uses cache or the Discovery API client to
    retrieve associated metadata, and then creates/updates ContentMetadata objects.

    Omits expired course runs from the updated metadata to match old
    edx-enterprise implementation.

    Args:
        catalog_query (CatalogQuery): The catalog query to pass to discovery's /search/all endpoint.
    Returns:
        list of str: Returns the content keys that were associated from the query results.
    """

    # metadata will be an empty dict if unavailable from cache or API.
    metadata = CatalogQueryMetadata(catalog_query).metadata

    # associate content metadata with a catalog query only when we get valid results
    # back from the discovery service. if metadata is `None`, an error occurred while
    # calling discovery and we should not proceed with the below association logic.
    if metadata:
        metadata_content_keys = [get_content_key(entry) for entry in metadata]
        LOGGER.info(
            'Retrieved %d content items (%d unique) from course-discovery for catalog query %s',
            len(metadata_content_keys),
            len(set(metadata_content_keys)),
            catalog_query,
        )

        associated_content_keys = associate_content_metadata_with_query(metadata, catalog_query)
        LOGGER.info(
            'Associated %d content items (%d unique) with catalog query %s',
            len(associated_content_keys),
            len(set(associated_content_keys)),
            catalog_query,
        )

        return associated_content_keys

    return None
