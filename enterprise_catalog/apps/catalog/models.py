import collections
import json
from logging import getLogger
from uuid import uuid4

from config_models.models import ConfigurationModel
from django.conf import settings
from django.db import IntegrityError, OperationalError, models, transaction
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from edx_rbac.models import UserRole, UserRoleAssignment
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.api.v1.utils import (
    get_enterprise_utm_context,
    get_most_recent_modified_time,
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
    CONTENT_COURSE_TYPE_ALLOW_LIST,
    CONTENT_TYPE_CHOICES,
    COURSE,
    COURSE_RUN,
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_ENTITLEMENT_MODE,
    PROGRAM,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.utils import (
    batch,
    get_content_filter_hash,
    get_content_key,
    get_content_type,
    get_parent_content_key,
    localized_utcnow,
)


LOGGER = getLogger(__name__)


class CatalogQuery(TimeStampedModel):
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
        max_length=32,
        editable=False,
    )

    uuid = models.UUIDField(
        unique=True,
        default=uuid4,
        editable=False,
    )

    title = models.CharField(
        null=True,
        unique=True,
        max_length=100
    )

    include_exec_ed_2u_courses = models.BooleanField(
        default=False,
        help_text=_(
            "Specifies whether the catalog is allowed to include exec ed (2U) courses.  This means that, "
            "when the content_filter specifies that 'course' content types should be included in the catalog, "
            "executive-education-2u course types won't be excluded from the content of the associated catalog."
        ),
    )

    class Meta:
        verbose_name = _("Catalog Query")
        verbose_name_plural = _("Catalog Queries")
        app_label = 'catalog'
        unique_together = (
            ('content_filter_hash', 'include_exec_ed_2u_courses'),
        )

    def save(self, *args, **kwargs):
        self.content_filter_hash = get_content_filter_hash(self.content_filter)
        super().save(*args, **kwargs)

    def pretty_print_content_filter(self):
        """
        Prints the content filter in an indented, more easily readable format.
        """
        return json.dumps(self.content_filter, indent=4)

    @classmethod
    def get_by_uuid(cls, uuid):
        try:
            return cls.objects.get(uuid=uuid)
        except cls.DoesNotExist:
            return None

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

    @cached_property
    def enterprise_customer(self):
        """
        A cached (for the life of this EnterpriseCatalog instance) EnterpriseCustomerDetails instance
        for this catalog's customer uuid.
        """
        return EnterpriseCustomerDetails(self.enterprise_uuid)

    def get_catalog_content_diff(self, content_keys):
        """
        Generate a catalog diff based on a provided list of content keys and what currently exists with the catalog's
        metadata.

        Arguments:
            content_keys: (list) A list of string content keys used to calculate the diff on the catalog.

        Returns:
            items_not_found: (list) A list of objects representing the content keys that were provided but not found
                under the catalog.
            items_not_included: (list) A list of objects representing the content keys not provided but were found under
                the catalog.
            items_found: (list) A list of objects representing content keys that were provided and found, paired with
                most recent updated at timestamp.

        A content key is considered contained within the catalog when:
          - associated metadata contains the specified content key.
          - associated metadata contains the specified content key as a parent (to handle when
            a catalog only contains course runs but a course id is searched).
          - associated metadata contains the specified content key in a nested course run (to
            handle when a catalog only contains courses but a course run id is searched).
        """
        found_content_keys = set()
        items_not_included = []
        items_found = []
        items_not_found = set()

        # cannot determine if specified content keys are part of catalog when a catalog query doesn't exist.
        if not self.catalog_query:
            return [items_not_found], items_not_included, items_found

        distinct_content_keys = set(content_keys)
        for content in self.content_metadata.all().values('modified', 'content_key'):
            content_key = content.get('content_key')
            found_content_keys.add(content_key)
            content_modified = get_most_recent_modified_time(
                content.get('modified'), self.modified, self.enterprise_customer.last_modified_date
            )
            if content_key in distinct_content_keys:
                items_found.append({
                    "content_key": content_key,
                    "date_updated": content_modified
                })
            else:
                items_not_included.append({'content_key': content_key})

        items_not_found = distinct_content_keys - found_content_keys
        return [{'content_key': item} for item in items_not_found], items_not_included, items_found

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

    def filter_content_keys(self, content_keys):
        """
        Determines whether content_keys are part of the catalog.

        Arguments:
            content_keys: (set) A set of string content keys to be filtered based on the catalog.

        Returns:
            items_included: (set) A filtered set of content keys contained in the catalog.

        This method handles the following scenarios:
          - associated metadata contains the specified content key.
          - associated metadata contains the specified content key as a parent (when a catalog only contains
           course runs but a course id is searched).
        """
        # cannot determine if specified content keys are part of catalog when catalog
        # query doesn't exist or no content keys are provided.
        if not self.catalog_query or not content_keys:
            return set()

        content_keys = set(content_keys)

        # construct a query on the associated catalog's content metadata to return metadata
        # where content_key and parent_content_key matches the specified content_keys to
        # handle the following cases where the catalog:
        #   - contains courses and the specified content_keys are course ids
        #   - contains course runs and the specified content_keys are course ids
        query = Q(content_key__in=content_keys) | Q(parent_content_key__in=content_keys)

        items_included = set()
        for content in self.content_metadata.filter(query).all():
            if content.content_key in content_keys:
                items_included.add(content.content_key)
            elif content.parent_content_key in content_keys:
                items_included.add(content.parent_content_key)
        return items_included

    def get_content_enrollment_url(self, content_metadata):
        """
        Return an enrollment page url based on the catalog information for the given content metadata record.

        If the enterprise customer's Learner Portal (LP) is enabled, the LP course page URL is returned.

        Arguments:
            content_metadata (ContentMetadata): The record for which an enrollment URL is returned.
        Returns:
            (str): Enterprise landing page URL OR Enterprise Learner Portal course page URL.
        """
        if content_metadata.content_type not in (COURSE, COURSE_RUN):
            return None

        content_key = content_metadata.content_key
        parent_content_key = content_metadata.parent_content_key

        if not content_key:
            return None

        params = get_enterprise_utm_context(self.enterprise_name)
        if self.publish_audit_enrollment_urls:
            params['audit'] = 'true'

        if content_metadata.is_exec_ed_2u_course:
            if not self.catalog_query.include_exec_ed_2u_courses:
                return None
            url, entitlement_sku = self._get_exec_ed_2u_enrollment_url(content_metadata)
            if not entitlement_sku:
                warning = 'No sku found for exec ed 2u course: %s in catalog %s'
                LOGGER.warning(warning, content_metadata.content_key, self.uuid)
                return None
            params['sku'] = entitlement_sku
        elif self._can_enroll_via_learner_portal(content_key):
            course_key = content_key
            if parent_content_key:
                # If parent_content_key is truthy, we know this is a course run.
                # We must add a `course_run_key` value to the query params,
                # so that we can render the correct info in the learner portal course page,
                # and so that the learner is enrolled
                # in the intended course run.
                course_key = parent_content_key
                params['course_run_key'] = content_key
            url = '{}/{}/course/{}'.format(
                settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL,
                self.enterprise_customer.slug,
                course_key
            )
        else:
            # Catalog param only needed for legacy (non-learner-portal) enrollment URLs
            params['catalog'] = self.uuid
            url = '{}/enterprise/{}/course/{}/enroll/'.format(
                settings.LMS_BASE_URL,
                self.enterprise_uuid,
                content_key,
            )

        return update_query_parameters(url, params)

    def _get_exec_ed_2u_enrollment_url(self, content_metadata):
        entitlement_sku = None
        for entitlement in content_metadata.json_metadata.get('entitlements', []):
            if entitlement['mode'] == EXEC_ED_2U_ENTITLEMENT_MODE:
                entitlement_sku = entitlement.get('sku')
        return (
            '{}/executive-education-2u/checkout'.format(settings.ECOMMERCE_BASE_URL),
            entitlement_sku,
        )

    def _can_enroll_via_learner_portal(self, content_key):
        """
        These changes are temporary until offers are implemented in the learner portal.
        See ENT-5968
        """
        if not self.enterprise_customer.learner_portal_enabled:
            return False

        is_integrated_customer_with_subsidies_and_offers = (
            str(self.enterprise_uuid) in
            settings.INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS
        )
        if not is_integrated_customer_with_subsidies_and_offers:
            return True

        # Customers in the special `INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS` list
        # must have the content_key contained in an active catalog for this method to return True.
        active_catalogs = EnterpriseCatalog.objects.filter(
            uuid__in=self.enterprise_customer.active_catalogs
        )
        for catalog in active_catalogs:
            contains_content_items = catalog.contains_content_keys([content_key])
            if contains_content_items:
                return True

        return False

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
            "The key represents this content's parent. For example for course_runs content their parent course key."
        )
    )

    # one course can be associated with many programs and one program can contain many courses.
    associated_content_metadata = models.ManyToManyField('self', blank=True)

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

    @property
    def is_exec_ed_2u_course(self):
        # pylint: disable=no-member
        return self.content_type == COURSE and self.json_metadata.get('course_type') == EXEC_ED_2U_COURSE_TYPE

    @property 
    def aggregation_key(self):
        return self.json_metadata.get('aggregation_key')

    @classmethod
    def recently_modified_records(cls, time_delta):
        """
        Returns the ContentMetadata records modified in the range(now - time_delta, now).
        """
        range_start = localized_utcnow() - time_delta
        range_end = localized_utcnow()
        return cls.objects.filter(
            modified__range=(range_start, range_end),
        )

    @classmethod
    def get_child_records(cls, content_metadata):
        """
        Returns all child records of the given ContentMetadata instance.
        """
        return cls.objects.filter(parent_content_key=content_metadata.content_key)

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


def _get_defaults_from_metadata(entry, exists=False):
    """
    Given a metadata entry from course-discovery's /search/all API endpoint, this function determines the
    default values to be used when creating/updating ContentMetadata objects (e.g., content_key).

    Regardless of content type, ContentMetadata objects will have its content_key, parent_content_key, and
    content_type fields updated to reflect the most current state. However, the json_metadata field is only
    conditionally included as part of the update.

    For net-new ContentMetadata objects, json_metadata is always included, determined by the ``exists``
    argument. However, for existing ContentMetadata objects, the logic is a bit more complex. For course runs
    and programs, the json_metadata field should always be fully overwritten with the metadata from /search/all.
    For courses, the existing json_metadata in the ContentMetadata database object should be merged with a minimal
    subset of fields that are known to exist only in the /search/all API response. This ensures we are not losing
    potentially critical fields in this service's ``get_content_metadata`` API endpoint by overwriting the full
    course metadata, which happens through the update_full_content_metadata_task.

    Arguments:
        entry (dict): A dictionary representing the metadata about some content from /search/all API response.
        exists (bool): True if the metadata already exists in the DB, False if not.

    Returns:
        dict: A dictionary containing the new defaults for the a ContentMetadata object.
    """
    content_key = get_content_key(entry)
    parent_content_key = get_parent_content_key(entry)
    content_type = get_content_type(entry)
    defaults = {
        'content_key': content_key,
        'parent_content_key': parent_content_key,
        'content_type': content_type,
    }
    if content_type == 'course' and exists:
        # Only include the json_metadata fields from /search/all that is not present in the
        # full course metadata to avoid changing the ``get_content_metadata`` API contract.
        entry_minimal = {}
        for field in settings.COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL:
            if value := entry.get(field):
                entry_minimal[field] = value
        if entry_minimal:
            defaults.update({'json_metadata': entry_minimal})
    elif not exists or (content_type != 'course'):
        # Update json_metadata for non-courses when ContentMetadata object already exists. Also,
        # always include json_metadata (regardless of content type) if ContentMetadata object
        # does not yet exist in the database.
        defaults.update({'json_metadata': entry})
    return defaults


def _partition_content_metadata_defaults(batched_metadata, existing_metadata_by_key):
    """
    Given a batch of metadata entries and a list of existing ContentMetadata objects, this function
    determines the default fields to use for creates/updates depending on whether a database object exists
    for each metadata entry.

    Arguments:
        batched_metadata (list): List of metadata entries from the /search/all API response.
        existing_metadata_by_key (dict): Dictionary of existing ContentMetadata objects in the
            database by content key.

    Returns:
        (existing_metadata_defaults, nonexisting_metadata_defaults): Tuple containing lists of both
            the default fields for ContentMetadata objects that already exist in the DB and for ContentMetadata
            objects that will be newly created.
    """
    existing_metadata_defaults = [
        _get_defaults_from_metadata(entry, exists=True)
        for entry in batched_metadata
        if get_content_key(entry) in existing_metadata_by_key
    ]
    nonexisting_metadata_defaults = [
        _get_defaults_from_metadata(entry)
        for entry in batched_metadata
        if not get_content_key(entry) in existing_metadata_by_key
    ]
    return existing_metadata_defaults, nonexisting_metadata_defaults


def _update_existing_content_metadata(existing_metadata_defaults, existing_metadata_by_key):
    """
    Iterates through existing ContentMetadata database objects, updating the values of various
    fields based on the defaults provided.

    Arguments:
        existing_metadata_defaults (list): List of default values for various fields
            to update the existing ContentMetadata database objects.
        existing_metadata_by_key (dict): Dictionary of existing ContentMetadata database objects to
            update by content_key.

    Returns:
        list: List of ContentMetadata objects that were updated.
    """
    metadata_list = []
    for defaults in existing_metadata_defaults:
        content_metadata = existing_metadata_by_key.get(defaults['content_key'])
        if content_metadata:
            for key, value in defaults.items():
                if key == 'json_metadata':
                    # merge new json_metadata with old json_metadata (i.e., don't replace it fully)
                    content_metadata.json_metadata.update(value)
                else:
                    # replace attributes with new values
                    setattr(content_metadata, key, value)
            metadata_list.append(content_metadata)

    metadata_fields_to_update = ['content_key', 'parent_content_key', 'content_type', 'json_metadata']
    batch_size = settings.UPDATE_EXISTING_CONTENT_METADATA_BATCH_SIZE
    for batched_metadata in batch(metadata_list, batch_size=batch_size):
        try:
            ContentMetadata.objects.bulk_update(
                batched_metadata,
                metadata_fields_to_update,
                batch_size=batch_size,
            )
        except OperationalError:
            content_keys = [record.content_key for record in batched_metadata]
            log_message = 'Operational error while updating batch of ContentMetadata objects with keys: %s'
            LOGGER.exception(log_message, content_keys)
            raise
    return metadata_list


def _create_new_content_metadata(nonexisting_metadata_defaults):
    """
    Creates new ContentMetadata database objects based on the defaults provided. This is done through an atomic
    database transaction.

    Arguments:
        nonexisting_metadata_defaults (list): List of default values for various fields to create
            non-existing ContentMetadata database objects.

    Returns:
        list: List of ContentMetadata objects that were created.
    """
    metadata_list = []
    try:
        with transaction.atomic():
            for defaults in nonexisting_metadata_defaults:
                content_metadata = ContentMetadata.objects.create(**defaults)
                metadata_list.append(content_metadata)
    except IntegrityError:
        LOGGER.exception('_create_new_content_metadata ran into an issue while creating new ContentMetadata objects.')
    return metadata_list


def _should_allow_metadata(metadata_entry, catalog_query=None):
    """
    Determines if an object from Discovery meets our criteria for indexing

    Arguments:
        metadata_entry: A single content metadata dictionary.

    Returns:
        bool: If we should save the metadata as a ContentMetaData object
    """
    if get_content_type(metadata_entry) != 'course':
        return True
    entry_course_type = metadata_entry.get('course_type')
    # allowing None here accounts for pre-existing tests, dirty prod data
    if entry_course_type is None or entry_course_type in CONTENT_COURSE_TYPE_ALLOW_LIST:
        return True
    # check if the content is allowed by the customer's query preferences
    if catalog_query and catalog_query.include_exec_ed_2u_courses and entry_course_type == EXEC_ED_2U_COURSE_TYPE:
        return True
    return False


def create_content_metadata(metadata, catalog_query=None):
    """
    Creates or updates a ContentMetadata object.

    Arguments:
        metadata (list): List of content metadata dictionaries.
        catalog_query (CatalogQuery): Catalog Query object.

    Returns:
        list: The list of ContentMetaData.
    """
    metadata_list = []
    for batched_metadata in batch(metadata, batch_size=100):
        content_keys = []
        filtered_batched_metadata = []
        for entry in batched_metadata:
            # Exclude exec ed courses from being ingested unless the query specifies that they are allowed
            if _should_allow_metadata(entry, catalog_query):
                content_keys.append(get_content_key(entry))
                filtered_batched_metadata.append(entry)
        existing_metadata = ContentMetadata.objects.filter(content_key__in=content_keys)
        existing_metadata_by_key = {metadata.content_key: metadata for metadata in existing_metadata}
        existing_metadata_defaults, nonexisting_metadata_defaults = _partition_content_metadata_defaults(
            filtered_batched_metadata, existing_metadata_by_key
        )

        # Update existing ContentMetadata records
        updated_metadata = _update_existing_content_metadata(existing_metadata_defaults, existing_metadata_by_key)
        metadata_list.extend(updated_metadata)

        # Create new ContentMetadata records
        created_metadata = _create_new_content_metadata(nonexisting_metadata_defaults)
        metadata_list.extend(created_metadata)

    return metadata_list


def associate_content_metadata_with_query(metadata, catalog_query):
    """
    Creates or updates a ContentMetadata object for each entry in `metadata`,
    and then associates that object with the `catalog_query` provided.

    Arguments:
        metadata (list): List of content metadata dictionaries.
        catalog_query (CatalogQuery): CatalogQuery object

    Returns:
        list: The list of content_keys for the metadata associated with the query.
    """
    metadata_list = create_content_metadata(metadata, catalog_query)

    # Setting `clear=True` will remove all prior relationships between
    # the CatalogQuery's associated ContentMetadata objects
    # before setting all new relationships from `metadata_list`.
    # https://docs.djangoproject.com/en/2.2/ref/models/relations/#django.db.models.fields.related.RelatedManager.set
    catalog_query.contentmetadata_set.set(metadata_list, clear=True)
    associated_content_keys = [metadata.content_key for metadata in metadata_list]
    return associated_content_keys


def create_course_associated_programs(programs, course_content_metadata):
    """
    Creates or updates a ContentMetadata object for each entry in `programs`,
    and then associates that object with the `course_content_metadata` provided.

    Arguments:
        programs (list): List of program metadata dictionaries extracted from course.
        course_content_metadata (ContentMetadata): ContentMetaData object

    Returns:
        list: The list of content_keys for the metadata associated with the query.
    """
    for program in programs:
        program['aggregation_key'] = f'program:{program["uuid"]}'
        program['content_type'] = 'program'
    metadata_list = create_content_metadata(programs)

    # remove existing associated_content_metadata relationship between program and courses before adding new relation
    course_content_metadata.associated_content_metadata.remove(
        *course_content_metadata.associated_content_metadata.filter(content_type=PROGRAM)
    )
    course_content_metadata.associated_content_metadata.add(*metadata_list)

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

    try:
        # metadata will be an empty dict if unavailable from cache or API.
        metadata = CatalogQueryMetadata(catalog_query).metadata
    except Exception as exc:
        LOGGER.exception('update_contentmetadata_from_discovery ran into an issue while talking to DiscoveryAPI.')
        raise exc

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

    return []


class CatalogUpdateCommandConfig(ConfigurationModel):
    """
    Model that specifies a ``force`` option
    for all of the catalog-updating (or reindexing)
    management commands.
    """
    force = models.BooleanField(
        default=False,
        help_text=_(
            "If true, will force the command's underlying celery tasks "
            "to run regardless of how recently the same task, on the same input, "
            "has been successfully executed."
        ),
    )
    no_async = models.BooleanField(
        default=False,
        help_text=_(
            "If true, for management commands that respect this field, "
            "celery tasks will not be apply_async()'d, but instead "
            "exectue as regular python functions."
        ),
    )

    @classmethod
    def current_options(cls):
        """
        Returns a dictionary of options from this config model.
        """
        current_config = cls.current()
        if current_config.enabled:
            return {
                'force': current_config.force,
                'no_async': current_config.no_async,
            }
        return {}
