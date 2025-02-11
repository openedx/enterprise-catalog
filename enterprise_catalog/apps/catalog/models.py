import collections
import copy
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
from enterprise_catalog.apps.api_client.discovery import (
    CatalogQueryMetadata,
    DiscoveryApiClient,
)
from enterprise_catalog.apps.api_client.enterprise_cache import (
    EnterpriseCustomerDetails,
)
from enterprise_catalog.apps.catalog.constants import (
    ACCESS_TO_ALL_ENTERPRISES_TOKEN,
    AGGREGATION_KEY_PREFIX,
    CONTENT_COURSE_TYPE_ALLOW_LIST,
    CONTENT_PRODUCT_SOURCE_ALLOW_LIST,
    CONTENT_TYPE_CHOICES,
    COURSE,
    COURSE_RUN,
    COURSE_RUN_RESTRICTION_TYPE_KEY,
    EXEC_ED_2U_COURSE_TYPE,
    EXEC_ED_2U_ENTITLEMENT_MODE,
    PROGRAM,
    QUERY_FOR_RESTRICTED_RUNS,
    RESTRICTED_RUNS_ALLOWED_KEY,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    get_advertised_course_run,
    get_course_first_paid_enrollable_seat_price,
)
from enterprise_catalog.apps.catalog.utils import (
    batch,
    enterprise_proxy_login_url,
    get_content_filter_hash,
    get_content_key,
    get_content_type,
    get_content_uuid,
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
        unique=True,
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

    class Meta:
        verbose_name = _("Catalog Query")
        verbose_name_plural = _("Catalog Queries")
        app_label = 'catalog'

    def save(self, *args, **kwargs):
        self.content_filter_hash = get_content_filter_hash(self.content_filter)
        super().save(*args, **kwargs)

    def pretty_print_content_filter(self):
        """
        Prints the content filter in an indented, more easily readable format.
        """
        return json.dumps(self.content_filter, indent=4)

    @cached_property
    def restricted_runs_allowed(self):
        """
        Return a dict of restricted course <-> run mappings by
        course key, e.g.
        ```
        "edX+FUN": [
            "course-v1:edX+FUN+3T2024"
        ]
        ```
        """
        mapping = self.content_filter.get(RESTRICTED_RUNS_ALLOWED_KEY)  # pylint: disable=no-member
        if not mapping:
            return None
        if not isinstance(mapping, dict):
            LOGGER.error('%s restricted runs value is not a dict', self)
            return None
        return {
            course_key.removeprefix(AGGREGATION_KEY_PREFIX): course_run_list
            for course_key, course_run_list in mapping.items()
        }

    @cached_property
    def restricted_courses_by_run_key(self):
        """
        Returns a reverse mapping of self.restricted_runs_allowed, e.g.
        ```
        {
            "course-v1:edX+FUN+3T2024": "edX+FUN",
            "course-v1:edX+FUN+3T2025": "edX+FUN",
            "course-v1:edX+GAMES+3T2024": "edX+GAMES",
        }
        ```

        Returns an empty dict if no restricted runs are allowed for this CatalogQuery.
        """
        if not self.restricted_runs_allowed:
            return {}

        restricted_courses_by_run = {}
        for course_key, restricted_run_list in self.restricted_runs_allowed.items():
            for run_key in restricted_run_list:
                restricted_courses_by_run[run_key] = course_key
        return restricted_courses_by_run

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
            f"<CatalogQuery: ({self.id}) with content_filter_hash '{self.content_filter_hash}' "
            f"and content_filter '{self.pretty_print_content_filter()}'>"
        )

    def short_str_for_listings(self):
        """
        Return *short* human-readable string representation for listings.
        """
        return (
            f"<CatalogQuery: ({self.id}) with UUID '{self.uuid}'>"
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
            Queryset of ContentMetadata: The queryset of associated content metadata
        """
        if not self.catalog_query:
            return ContentMetadata.objects.none()
        return self.catalog_query.contentmetadata_set.prefetch_related(
            'restricted_run_allowed_for_restricted_course'
        ).filter(
            # Exclude all restricted runs (heuristic is that a run is assumed
            # restricted if it is mapped to a restricted course via
            # RestrictedRunAllowedForRestrictedCourse).
            restricted_run_allowed_for_restricted_course__isnull=True,
        )

    @property
    def content_metadata_with_restricted(self):
        """
        Same as self.content_metadata, but dynamically replace course json_metadata
        with the correct version containing restricted runs allowed by the current
        catalog query.

        The technique to dynamically override ContentMetadata.json_metadata is a
        combination of two things:
        1. This method setting the `restricted_course_metadata_for_catalog_query`
           attribute in the queryset to get the correct RestrictedCourseMetadata, and
        2. The ContentMetdata.json_metadata attribute being a property that
           dynamically uses (1) or falls back to the stored value in _json_metadata.

        Returns:
            Queryset of ContentMetadata: Same as self.content_metadata, but courses may have augmented
            json_metadata.
        """
        if not self.catalog_query:
            return ContentMetadata.objects.none()
        related_contentmetadata = self.catalog_query.contentmetadata_set
        # Provide json_metadata overrides via dynamic attribute if any restricted runs are allowed.
        if self.catalog_query.restricted_runs_allowed:
            # FYI: prefetch causes a performance penalty by introducing a 2nd database query.
            related_contentmetadata = related_contentmetadata.prefetch_restricted_overrides(
                catalog_query=self.catalog_query,
            )

        return related_contentmetadata.all()

    @cached_property
    def restricted_runs_allowed(self):
        return self.catalog_query.restricted_runs_allowed

    @cached_property
    def restricted_courses_by_run_key(self):
        return self.catalog_query.restricted_courses_by_run_key

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

    def get_matching_content(self, content_keys, include_restricted=False):
        """
        Returns the set of content contained within this catalog that matches
        any of the course keys, course run keys, or programs keys specified by
        the given ``content_keys`` argument.

        A content key is considered contained within the catalog when:
          - any metadata associated with the catalog has an exact ``content_key`` value that is contained
            in the provided ``content_keys`` list.
          - any metadata associated with the catalog has a ``parent_content_key`` value that is contained
            in the ``content_keys`` list (to handle cases when a catalog contains only
            course runs, but course ids are provided in the ``content_keys`` argument).
          - any metadata associated with the catalog has a nested course run with a ``key`` that is contained
            in the ``content_keys`` list (to handle cases when a catalog contains only courses,
            but course run keys are provided in the ``content_keys`` argument).
        """
        # We cannot determine which content keys are part of this catalog when the catalog
        # query doesn't exist, or when no content keys are provided.
        if not self.catalog_query or not content_keys:
            return ContentMetadata.objects.none()

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
        if include_restricted and self.catalog_query.restricted_runs_allowed:
            # Only hide restricted runs that are not allowed by the current catalog.
            searched_metadata = searched_metadata.prefetch_related(
                'restricted_run_allowed_for_restricted_course'
            ).exclude(
                # Find all restricted runs allowed by a RestrictedCourseMetadata related to the
                # current CatalogQuery. Do NOT exclude those.
                ~Q(restricted_run_allowed_for_restricted_course__course__catalog_query=self.catalog_query)
                # Exclude all other restricted runs. A run is assumed of type restricted if it
                # is related to at least one RestrictedRunAllowedForRestrictedCourse.
                & Q(restricted_run_allowed_for_restricted_course__isnull=False)
            )
        else:
            # Hide ALL restricted runs.
            searched_metadata = searched_metadata.exclude(
                restricted_run_allowed_for_restricted_course__isnull=False
            )
        parent_content_keys = {
            metadata.parent_content_key
            for metadata in searched_metadata
            if metadata.parent_content_key
        }
        query |= Q(content_key__in=parent_content_keys)
        if include_restricted:
            return self.content_metadata_with_restricted.filter(query)
        else:
            return self.content_metadata.filter(query)

    def contains_content_keys(self, content_keys, include_restricted=False):
        """
        Determines whether the given ``content_keys`` are part of the catalog.

        Returns True if this catalog contains the courses, course runs, and/or programs specified by
        the given content key(s), else False.

        A content key is considered contained within the catalog when:
          - any metadata associated with the catalog has an exact ``content_key`` value that is contained
            in the provided ``content_keys`` list.
          - any metadata associated with the catalog has a ``parent_content_key`` value that is contained
            in the ``content_keys`` list (to handle cases when a catalog contains only
            course runs, but course ids are provided in the ``content_keys`` argument).
          - any metadata associated with the catalog has a nested course run with a ``key`` that is contained
            in the ``content_keys`` list (to handle cases when a catalog contains only courses,
            but course run keys are provided in the ``content_keys`` argument).
        """
        included_content = self.get_matching_content(content_keys, include_restricted=include_restricted)
        return included_content.exists()

    def filter_content_keys(self, content_keys, include_restricted=False):
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
        if include_restricted:
            accessible_metadata_qs = self.content_metadata_with_restricted
        else:
            accessible_metadata_qs = self.content_metadata
        for content in accessible_metadata_qs.filter(query).all():
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

        can_enroll_with_learner_portal = self._can_enroll_via_learner_portal

        if content_metadata.is_exec_ed_2u_course:
            exec_ed_enroll_url, exec_ed_entitlement_sku = self._get_exec_ed_2u_enrollment_url(
                content_metadata,
                enterprise_slug=self.enterprise_customer.slug,
                use_learner_portal=can_enroll_with_learner_portal,
            )
            if can_enroll_with_learner_portal:
                return update_query_parameters(exec_ed_enroll_url, params)

            if not exec_ed_entitlement_sku:
                warning = 'No sku found for exec ed 2u course: %s in catalog %s'
                LOGGER.warning(warning, content_metadata.content_key, self.uuid)
                return None

            params['sku'] = exec_ed_entitlement_sku
            exec_ed_proxy_login_enrollment_url = enterprise_proxy_login_url(
                self.enterprise_customer.slug,
                next_url=update_query_parameters(exec_ed_enroll_url, params)
            )
            return exec_ed_proxy_login_enrollment_url
        elif can_enroll_with_learner_portal:
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

            course_run_key = content_key
            if not parent_content_key:
                if advertised_course_run := get_advertised_course_run(content_metadata.json_metadata):
                    course_run_key = advertised_course_run['key']
            url = '{}/enterprise/{}/course/{}/enroll/'.format(
                settings.LMS_BASE_URL,
                self.enterprise_uuid,
                course_run_key,
            )

        return update_query_parameters(url, params)

    def _get_exec_ed_2u_enrollment_url(self, content_metadata, enterprise_slug, use_learner_portal):
        if use_learner_portal:
            return (
                f"{settings.ENTERPRISE_LEARNER_PORTAL_BASE_URL}/{enterprise_slug}/"
                f"executive-education-2u/course/{content_metadata.content_key}",
                None
            )

        entitlement_sku = None
        for entitlement in content_metadata.json_metadata.get('entitlements', []):
            if entitlement['mode'] == EXEC_ED_2U_ENTITLEMENT_MODE:
                entitlement_sku = entitlement.get('sku')

        return (
            f"{settings.ECOMMERCE_BASE_URL}/executive-education-2u/checkout",
            entitlement_sku,
        )

    @property
    def _can_enroll_via_learner_portal(self):
        """
        Check whether the enterprise customer has the learner portal enabled.
        """
        if not self.enterprise_customer.learner_portal_enabled:
            return False
        return True

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


class ContentMetadataQuerySet(models.QuerySet):
    """
    Customer queryset for ContentMetadata providing convenience methods to augment the results.
    """

    def prefetch_restricted_overrides(self, catalog_query=None):
        """
        Augment this queryset by fetching "override" metadata if any exist for a given
        CatalogQuery.  The `json_metadata` attribute of courses returned by this new
        queryset will be overridden if a related RestrictedCourseMetadata exists.
        """
        # If catalog_query is None, look for the "canonical" RestrictedCourseMetadata
        # object which has a NULL catalog_query.
        catalog_query_filter = {'catalog_query': catalog_query} if catalog_query else {'catalog_query__isnull': True}
        return self.prefetch_related(
            models.Prefetch(
                'restricted_courses',
                queryset=RestrictedCourseMetadata.objects.filter(**catalog_query_filter),
                to_attr='restricted_course_metadata_for_catalog_query',
            )
        )


class ContentMetadataManager(models.Manager):
    """
    Customer manager for ContentMetadata that forces the `modified` field
    to be updated during `bulk_update()`.
    """

    def bulk_update(self, objs, fields, batch_size=None):
        """
        Updates the `modified` time of each object, and then
        does the usual bulk update, with `modified` as also
        a field to save.
        """
        last_modified = localized_utcnow()
        for obj in objs:
            obj.modified = last_modified
        fields += ['modified']

        super().bulk_update(objs, fields, batch_size=batch_size)


class BaseContentMetadata(TimeStampedModel):
    """
    Common ContentMetadata fields.
    """
    class Meta:
        abstract = True

    content_uuid = models.UUIDField(
        null=True,
        blank=True,
        max_length=32,
        unique=False,
        verbose_name='Content UUID',
        help_text=_(
            "The UUID that represents a piece of content. This value is usually a secondary identifier to content_key "
            "in the enterprise environment."
        )
    )
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
    _json_metadata = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        db_column='json_metadata',
        help_text=_(
            "The metadata about a particular piece content as retrieved from the discovery service's search/all "
            "endpoint results, specified as a JSON object."
        )
    )

    objects = ContentMetadataManager()

    @property
    def is_exec_ed_2u_course(self):
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

    @property
    def json_metadata(self):
        return self._json_metadata

    @json_metadata.setter
    def json_metadata(self, new_json_metadata):
        self._json_metadata = new_json_metadata

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return f"<{self.__class__.__name__} for '{self.content_key}'>"


class ContentMetadata(BaseContentMetadata):
    """
    Stores the JSON metadata for a piece of content, such as a course, course run, or program.
    The metadata is retrieved from the Discovery service /search/all endpoint.

    .. no_pii:
    """
    class Meta:
        verbose_name = _("Content Metadata")
        verbose_name_plural = _("Content Metadata")
        app_label = 'catalog'

    # one course can be associated with many programs and one program can contain many courses.
    associated_content_metadata = models.ManyToManyField('self', blank=True)

    # one course can be part of many CatalogQueries and one CatalogQuery can contain many courses.
    catalog_queries = models.ManyToManyField(CatalogQuery)

    history = HistoricalRecords()

    objects = ContentMetadataManager().from_queryset(ContentMetadataQuerySet)()

    @property
    def json_metadata(self):
        """
        Use the CatalogQuery-specific version of a course json_metadata if one exists
        (potentially containing restricted runs allowed by that CatatlogQuery),
        otherwise fall back to the standard unrestricted-only version.
        """
        restricted_course_metadata_for_catalog_query = getattr(
            self,
            'restricted_course_metadata_for_catalog_query',
            None,
        )
        # Truthy means that the requester wants to see restricted runs AND restricted
        # runs were actually found for this specific course and the requester's
        # specific Catalog.
        if restricted_course_metadata_for_catalog_query:
            # pylint: disable=protected-access, unsubscriptable-object
            return restricted_course_metadata_for_catalog_query[0]._json_metadata
        return self._json_metadata

    @json_metadata.setter
    def json_metadata(self, new_json_metadata):
        self._json_metadata = new_json_metadata


class RestrictedCourseMetadata(BaseContentMetadata):
    """
    Copies of courses, but one copy for each CatalogQuery which explicitly
    allows any restricted runs of the course.

    .. no_pii:
    """
    class Meta:
        verbose_name = _("Restricted Course Metadata")
        verbose_name_plural = _("Restricted Course Metadata")
        app_label = 'catalog'
        unique_together = ('content_key', 'catalog_query')

    history = HistoricalRecords()

    # Overwrite content_key from BaseContentMetadata in order to change unique
    # to False. Use unique_together to allow multiple copies of the same course
    # (one for each catalog query.
    content_key = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=False,
        help_text=_(
            "The key that represents a piece of content, such as a course, course run, or program."
        )
    )
    unrestricted_parent = models.ForeignKey(
        ContentMetadata,
        blank=False,
        null=True,
        related_name='restricted_courses',
        on_delete=models.deletion.SET_NULL,
    )
    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=True,
        related_name='restricted_content_metadata',
        on_delete=models.deletion.SET_NULL,
    )
    restricted_run_allowed_for_restricted_course = models.ManyToManyField(
        ContentMetadata,
        through='RestrictedRunAllowedForRestrictedCourse',
        through_fields=('course', 'run'),
    )
    history = HistoricalRecords()

    def __str__(self):
        """
        Return human-readable string representation.
        """
        catalog_query_id = self.catalog_query.id if self.catalog_query else None
        return f"<{self.__class__.__name__} for '{self.content_key}' and CatalogQuery ({catalog_query_id})>"

    @staticmethod
    def allowed_runs_for_course(course_metadata_dict, catalog_query):
        """
        Given a ``course_metadata_dict``, returns a filtered list of ``course_runs``
        containing only unrestricted runs and restricted runs that are allowed by
        the provided ``catalog_query``.
        """
        restricted_runs = RestrictedCourseMetadata.restricted_runs_for_course(course_metadata_dict, catalog_query)
        unrestricted_runs = [
            run for run in course_metadata_dict['course_runs']
            if run.get(COURSE_RUN_RESTRICTION_TYPE_KEY) is None
        ]
        return unrestricted_runs + restricted_runs

    @staticmethod
    def restricted_runs_for_course(course_metadata_dict, catalog_query):
        """
        Given a ``course_metadata_dict``, returns a filtered list of ``course_runs``
        containing only restricted runs that are allowed by
        the provided ``catalog_query``.
        """
        allowed_restricted_runs = catalog_query.restricted_runs_allowed.get(course_metadata_dict['key'], [])
        return [
            run for run in course_metadata_dict['course_runs']
            if run['key'] in allowed_restricted_runs
        ]

    @property
    def restricted_run_dicts(self):
        return self.restricted_runs_for_course(self.json_metadata, self.catalog_query)

    def update_metadata(self, course_metadata_dict, is_full_update=False):
        """
        Updates and saves the json_metadata for this restricted course.
        Params:
          course_metadata_dict: A dictionary of course metadata
            fetched from either /api/v1/search/all *or* /api/v1/courses (course-discovery).
          is_full_update: Whether the course metadata provided is fetched from /api/v1/courses.
            If so, we fully update the json_metadata of this record with those contents, otherwise
            the update is trimmed down by `_get_defaults_from_metadata()`. Defaults to False.
        """
        if self.catalog_query:
            filtered_metadata = self.filter_restricted_runs(course_metadata_dict, self.catalog_query)
        else:
            filtered_metadata = course_metadata_dict

        if is_full_update:
            self._json_metadata.update(filtered_metadata)
        else:
            # We care about preserving the values of the "plucked"
            # fields iterated through in `_get_defaults_from_metadata()`
            # when we're doing a non-full update
            # (i.e. an update from a course-discovery api/v1/search/all payload)
            self._json_metadata.update(
                _get_defaults_from_metadata(filtered_metadata)['_json_metadata'],
            )
        self.save()

    def update_course_run_relationships(self):
        """
        Updates the relationships between restricted course runs, this
        restricted course, and this restricted course's catalog_query.
        """
        existing_relationships = list(self.catalog_query.contentmetadata_set.filter(
            parent_content_key=self.content_key,
        ).values_list('content_key', flat=True))
        LOGGER.info(
            '%s has existing course run relationships %s prior to updating',
            self, existing_relationships,
        )

        restricted_runs = []

        for course_run_dict in self.restricted_run_dicts:
            course_run_record = self.update_or_create_run(
                course_run_key=get_content_key(course_run_dict),
                parent_content_key=self.content_key,
                course_run_dict=course_run_dict,
            )
            restricted_runs.append(course_run_record)

        # We use a set() here, with clear=True, to clear and then reset the related allowed runs
        # for this restricted course. This is necessary in the case that a previously-allowed
        # run becomes unassociated from the restricted course.
        self.restricted_run_allowed_for_restricted_course.set(restricted_runs, clear=True)
        LOGGER.info('Updated restricted runs of %s to %s', self, restricted_runs)
        self.refresh_from_db()

    @classmethod
    def update_or_create_run(cls, course_run_key, parent_content_key, course_run_dict):
        """
        Helper to create a course run ContentMetadata record, provided a content key,
        a parent course key, and a dictionary of course run metadata.
        """
        defaults = _get_defaults_from_metadata(course_run_dict)
        defaults['parent_content_key'] = parent_content_key
        # We have to conditionally pop these fields from defaults to keep them from
        # being used in the UPDATE statement, because the nested course run
        # data from the /api/v1/search/all payload *does not* include the
        # course run uuid or aggregation key, which are used by
        # _get_defaults_from_metadata() to compute the content type and parent key.
        # We additionally pop the content_key field because it's another primary
        # identifier used to uniquely identify the record in the non-defaults arguments
        # in update_or_create() below.
        for key in ['content_key', 'content_uuid', 'parent_content_key', 'content_type']:
            if not defaults.get(key):
                defaults.pop(key)
        course_run_record, _ = ContentMetadata.objects.update_or_create(
            content_key=course_run_key,
            content_type=COURSE_RUN,
            defaults=defaults,
        )
        return course_run_record

    @classmethod
    def _store_record(cls, course_metadata_dict, catalog_query=None, is_full_update=False):
        """
        Given a course metadata dictionary, stores a corresponding
        ``RestrictedContentMetadata`` record. Raises if the content key
        is not of type 'course', or if a corresponding unrestricted parent
        record cannot be found.
        """
        content_type = course_metadata_dict.get('content_type')
        if content_type != COURSE:
            raise Exception('Can only store RestrictedContentMetadata with content type of course')

        course_key = course_metadata_dict['key']
        parent_record = ContentMetadata.objects.get(content_key=course_key, content_type=COURSE)

        defaults = {}
        if content_uuid := get_content_uuid(course_metadata_dict):
            defaults['content_uuid'] = content_uuid

        record, _ = cls.objects.get_or_create(
            content_key=course_key,
            content_type=COURSE,
            unrestricted_parent=parent_record,
            catalog_query=catalog_query,
            defaults=defaults,
        )
        record.update_metadata(course_metadata_dict, is_full_update=is_full_update)
        return record

    @classmethod
    def store_canonical_record(cls, course_metadata_dict, is_full_update=False):
        """
        Stores the canonical copy of this record, which will include all existing
        course runs for a course, regardless of their restriction status. The canonical
        record will *not* have a related catalog query.
        """
        return cls._store_record(course_metadata_dict, is_full_update=is_full_update)

    @classmethod
    def store_record_with_query(cls, course_metadata_dict, catalog_query, is_full_update=False):
        """
        Stores a restricted course record containing only unrestricted course runs
        and the restricted course runs explicitly allowed by the provided catalog query.
        """
        course_record = cls._store_record(course_metadata_dict, catalog_query, is_full_update=is_full_update)
        course_record.update_course_run_relationships()
        return course_record

    @classmethod
    def filter_restricted_runs(cls, course_metadata_dict, catalog_query):
        """
        Returns a copy of ``course_metadata_dict`` whose course_runs list
        contains only unrestricted runs and restricted runs that are allowed
        by the provided ``catalog_query``, and whose ``course_runs_keys``,
        ``course_run_statuses``, and ``first_enrollable_paid_seat_price`` items
        are updated to take only these allowed runs into account.
        """
        filtered_metadata = copy.deepcopy(course_metadata_dict)

        allowed_runs = []
        allowed_statuses = set()
        allowed_keys = []

        for run in cls.allowed_runs_for_course(filtered_metadata, catalog_query):
            allowed_runs.append(run)
            allowed_statuses.add(run.get('status'))
            allowed_keys.append(run['key'])

        filtered_metadata['course_runs'] = allowed_runs
        filtered_metadata['course_run_keys'] = allowed_keys
        filtered_metadata['course_run_statuses'] = sorted(list(allowed_statuses))
        filtered_metadata['first_enrollable_paid_seat_price'] = get_course_first_paid_enrollable_seat_price(
            filtered_metadata,
        )

        return filtered_metadata


class RestrictedRunAllowedForRestrictedCourse(TimeStampedModel):
    """
    Mapping table to relate RestrictedCourseMetadata objects to restricted runs in ContentMetadata.

    A run should be mapped to a restricted course IFF the RestrictedCourseMetadata's
    catalog query explicitly allows the run. This mapping table should be generated by the
    update-content-metadata task.

    .. no_pii:
    """
    course = models.ForeignKey(
        RestrictedCourseMetadata,
        blank=False,
        null=True,
        on_delete=models.deletion.SET_NULL,
    )
    run = models.ForeignKey(
        ContentMetadata,
        blank=False,
        null=True,
        related_name='restricted_run_allowed_for_restricted_course',
        on_delete=models.deletion.SET_NULL,
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


def _restricted_content_defaults(entry):
    """
    Helper to populate the update_or_create() ``defaults``
    for restricted content.
    """
    defaults = {'_json_metadata': entry}
    if content_uuid := entry.get('uuid'):
        defaults['content_uuid'] = content_uuid
    return defaults


def _get_defaults_from_metadata(entry, exists=False):
    """
    Given a metadata entry from course-discovery's /search/all API endpoint, this function determines the
    default values to be used when creating/updating ContentMetadata objects (e.g., content_key).

    Regardless of content type, ContentMetadata objects will have its content_key, content_uuid, parent_content_key,
    and content_type fields updated to reflect the most current state. However, the json_metadata field is only
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
    content_uuid = get_content_uuid(entry)
    defaults = {
        'content_uuid': content_uuid,
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
            defaults.update({'_json_metadata': entry_minimal})
    elif not exists or (content_type != 'course'):
        # Update json_metadata for non-courses when ContentMetadata object already exists. Also,
        # always include json_metadata (regardless of content type) if ContentMetadata object
        # does not yet exist in the database.
        defaults.update({'_json_metadata': entry})
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


def _update_existing_content_metadata(existing_metadata_defaults, existing_metadata_by_key, dry_run=False):
    """
    Iterates through existing ContentMetadata database objects, updating the values of various
    fields based on the defaults provided.

    Arguments:
        existing_metadata_defaults (list): List of default values for various fields
            to update the existing ContentMetadata database objects.
        existing_metadata_by_key (dict): Dictionary of existing ContentMetadata database objects to
            update by content_key.
        dry_run (boolean): Logs rather than commits updated content metadata

    Returns:
        list: List of ContentMetadata objects that were updated.
    """
    metadata_list = []
    for defaults in existing_metadata_defaults:
        content_metadata = existing_metadata_by_key.get(defaults['content_key'])
        if content_metadata:
            for key, value in defaults.items():
                if key == '_json_metadata':
                    # merge new json_metadata with old json_metadata (i.e., don't replace it fully)
                    content_metadata._json_metadata.update(value)  # pylint: disable=protected-access
                else:
                    # replace attributes with new values
                    setattr(content_metadata, key, value)
            metadata_list.append(content_metadata)

    if dry_run:
        LOGGER.info(f"[Dry Run] Number of Content Metadata records that would have been updated: {len(metadata_list)}")
        for metadata in metadata_list:
            LOGGER.info(f"[Dry Run] Skipping Content Metadata update: {metadata}")
    else:
        metadata_fields_to_update = ['content_key', 'parent_content_key', 'content_type', '_json_metadata']
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


def _create_new_content_metadata(nonexisting_metadata_defaults, dry_run=False):
    """
    Creates new ContentMetadata database objects based on the defaults provided. This is done through an atomic
    database transaction.

    Arguments:
        nonexisting_metadata_defaults (list): List of default values for various fields to create
            non-existing ContentMetadata database objects.
        dry_run (boolean): Logs rather than commits newly-created content metadata.

    Returns:
        list: List of ContentMetadata objects that were created (or logged if dry_run=True).
    """
    metadata_list = []
    try:
        with transaction.atomic():
            for defaults in nonexisting_metadata_defaults:
                if dry_run:
                    content_metadata = ContentMetadata(**defaults)
                    LOGGER.info(f"Created {content_metadata}")
                else:
                    content_metadata = ContentMetadata.objects.create(**defaults)
                metadata_list.append(content_metadata)
    except IntegrityError:
        LOGGER.exception('_create_new_content_metadata ran into an issue while creating new ContentMetadata objects.')
    return metadata_list


def _fetch_product_source(metadata_entry):
    product_source = metadata_entry.get('product_source')
    if isinstance(product_source, dict):
        return product_source.get('slug')
    else:
        return product_source


def _should_allow_metadata(metadata_entry, catalog_query=None):
    """
    Determines if an object from Discovery meets our criteria for indexing

    Arguments:
        metadata_entry: A single content metadata dictionary.

    Returns:
        bool: If we should save the metadata as a ContentMetaData object
    """
    entry_product_source = _fetch_product_source(metadata_entry)
    if entry_product_source is not None and entry_product_source.lower() not in CONTENT_PRODUCT_SOURCE_ALLOW_LIST:
        LOGGER.warning(
            '(ENT-7893.a) catalog query %s disallows metadata not in source allow list %s',
            catalog_query.id,
            metadata_entry.get('key'),
        )
        return False
    # make sure to exclude exec ed course runs
    content_type = get_content_type(metadata_entry)
    if content_type != 'course':
        return True
    entry_course_type = metadata_entry.get('course_type')
    # allowing None here accounts for pre-existing tests, dirty prod data
    if entry_course_type is None or entry_course_type in CONTENT_COURSE_TYPE_ALLOW_LIST:
        return True
    return False


def create_content_metadata(metadata, catalog_query=None, dry_run=False):
    """
    Creates or updates a ContentMetadata object.

    Arguments:
        metadata (list): List of content metadata dictionaries.
        catalog_query (CatalogQuery): Catalog Query object.
        dry_run (boolean): Logs rather than commits content metadata additions.

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
        updated_metadata = _update_existing_content_metadata(
            existing_metadata_defaults,
            existing_metadata_by_key,
            dry_run
        )
        metadata_list.extend(updated_metadata)

        # Create new ContentMetadata records
        created_metadata = _create_new_content_metadata(nonexisting_metadata_defaults, dry_run)
        metadata_list.extend(created_metadata)

    return metadata_list


def _check_content_association_threshold(catalog_query, metadata_list):
    """
    Helper method to check a given catalog query's content metadata association set and compare it to a new set of
    metadata records. Should the two sets of records differ in size beyond a configurable percentage value, and are
    evaluated to be applicable, this method returns True, indicating the threshold of difference has been met.

    Applicability for the threshold is defined as such:
    - The existing set of content associations must exceed a configurable cutoff value
    - The query must have not been modified today, meaning it's stale
    - The change in number of content association records must exceed a configurable percentage, both in a positive and
    negative direction (ie the query loses or gains more than x% of its prior number of records)
    """
    existing_relations_size = catalog_query.contentmetadata_set.count()
    new_relations_size = len(metadata_list)
    # To prevent false positives, this content association action stop gap will only apply to reasonably sized
    # content sets
    LOGGER.info(
        '_check_content_association_threshold is checking the guardrail consideration floor of: %s for query: %s',
        settings.CATALOG_CONTENT_INCLUSION_GUARDRAIL_CONSIDERATION_FLOOR,
        catalog_query,
    )
    if existing_relations_size > settings.CATALOG_CONTENT_INCLUSION_GUARDRAIL_CONSIDERATION_FLOOR:
        # If the catalog query hasn't been modified yet today, means there's no immediate reason for such a
        # large change in content associations
        LOGGER.info(
            '_check_content_association_threshold is checking the modified value: %s of query: %s as compared to '
            'todays date: %s',
            catalog_query.modified.date(),
            catalog_query,
            localized_utcnow().date(),
        )
        if catalog_query.modified.date() < localized_utcnow().date():
            # Check if the association of content results in a percentage change of
            # `CATALOG_CONTENT_INCLUSION_GUARDRAIL_ALLOWABLE_DELTA` of content items from the query's content set.
            percent_change = abs((new_relations_size - existing_relations_size) / existing_relations_size)
            LOGGER.info(
                '_check_content_association_threshold is checking the percent change: %s of query: %s as compared to '
                'the threshold: %s',
                percent_change,
                catalog_query,
                settings.CATALOG_CONTENT_INCLUSION_GUARDRAIL_ALLOWABLE_DELTA,
            )
            if percent_change > settings.CATALOG_CONTENT_INCLUSION_GUARDRAIL_ALLOWABLE_DELTA:
                LOGGER.warning(
                    "[CONTENT_DELTA_WARNING] associate_content_metadata_with_query is requested to set query: "
                    "%s to a content metadata set of length of %s when it previous had a content metadata set length "
                    "of:%s. The current threshold cutoff is a delta of: %s content remaining. The update has been "
                    "prevented.",
                    catalog_query,
                    new_relations_size,
                    existing_relations_size,
                    settings.CATALOG_CONTENT_INCLUSION_GUARDRAIL_ALLOWABLE_DELTA,
                )
                return True
            elif percent_change > settings.CATALOG_CONTENT_ASSOCIATIONS_CONTENT_DELTA_WARNING_THRESHOLD:
                LOGGER.warning(
                    "[CONTENT_DELTA_WARNING] associate_content_metadata_with_query hit the warning threshold: %s "
                    "while setting query: %s to a content metadata set of length of %s when it previous had a content "
                    "metadata set length of:%s.",
                    settings.CATALOG_CONTENT_ASSOCIATIONS_CONTENT_DELTA_WARNING_THRESHOLD,
                    catalog_query,
                    new_relations_size,
                    existing_relations_size,
                )
    return False


def associate_content_metadata_with_query(metadata, catalog_query, dry_run=False):
    """
    Creates or updates a ContentMetadata object for each entry in `metadata`,
    and then associates that object with the `catalog_query` provided.

    Arguments:
        metadata (list): List of content metadata dictionaries.
        catalog_query (CatalogQuery): CatalogQuery object
        dry_run (boolean): Logs rather than commits updated content metadata.

    Returns:
        list: The list of content_keys for the metadata associated with the query.
    """
    metadata_list = create_content_metadata(metadata, catalog_query, dry_run)
    # Stop gap if the new metadata list is extremely different from the current one
    if _check_content_association_threshold(catalog_query, metadata_list):
        return list(catalog_query.contentmetadata_set.values_list('content_key', flat=True))
    # Setting `clear=True` will remove all prior relationships between
    # the CatalogQuery's associated ContentMetadata objects
    # before setting all new relationships from `metadata_list`.
    # https://docs.djangoproject.com/en/2.2/ref/models/relations/#django.db.models.fields.related.RelatedManager.set
    if dry_run:
        old_metadata_count = catalog_query.contentmetadata_set.count()
        new_metadata_count = len(metadata_list)
        if old_metadata_count != new_metadata_count:
            LOGGER.info('[Dry Run] Updated metadata count ({} -> {}) for {}'.format(
                old_metadata_count, new_metadata_count, catalog_query))
    else:
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


def update_contentmetadata_from_discovery(catalog_query, dry_run=False):
    """
    Takes a CatalogQuery, uses cache or the Discovery API client to
    retrieve associated metadata, and then creates/updates ContentMetadata objects.

    Omits expired course runs from the updated metadata to match old
    edx-enterprise implementation.

    Args:
        catalog_query (CatalogQuery): The catalog query to pass to discovery's /search/all endpoint.
        dry_run (boolean): Logs rather than commits updated content metadata.
    Returns:
        list of str: Returns the content keys that were associated from the query results.
    """

    try:
        # metadata will be an empty dict if unavailable from cache or API.
        metadata = CatalogQueryMetadata(catalog_query).metadata
    except Exception as exc:
        LOGGER.exception(f'update_contentmetadata_from_discovery failed {catalog_query}')
        raise exc

    if not metadata:
        return []

    # associate content metadata with a catalog query only when we get valid results
    # back from the discovery service. if metadata is `None`, an error occurred while
    # calling discovery and we should not proceed with the below association logic.
    metadata_content_keys = [get_content_key(entry) for entry in metadata]
    LOGGER.info(
        'Retrieved %d content items (%d unique) from course-discovery for catalog query %s',
        len(metadata_content_keys),
        len(set(metadata_content_keys)),
        catalog_query,
    )

    associated_content_keys = associate_content_metadata_with_query(metadata, catalog_query, dry_run)
    LOGGER.info(
        'Associated %d content items (%d unique) with catalog query %s',
        len(associated_content_keys),
        len(set(associated_content_keys)),
        catalog_query,
    )

    restricted_content_keys = synchronize_restricted_content(catalog_query, dry_run=dry_run)
    return associated_content_keys + restricted_content_keys


def synchronize_restricted_content(catalog_query, dry_run=False):
    """
    Fetch and assoicate any permitted restricted courses for the given catalog_query.
    """
    if not getattr(settings, 'SHOULD_FETCH_RESTRICTED_COURSE_RUNS', False):
        return []

    if not catalog_query.restricted_runs_allowed:
        return []

    restricted_course_keys = list(catalog_query.restricted_runs_allowed.keys())
    content_filter = {
        'content_type': COURSE,
        'key': restricted_course_keys,
    }
    discovery_client = DiscoveryApiClient()
    course_payload = discovery_client.retrieve_metadata_for_content_filter(
        content_filter, QUERY_FOR_RESTRICTED_RUNS,
    )

    results = []
    for course_dict in course_payload:
        LOGGER.info('Storing restricted course %s for catalog_query %s', course_dict.get('key'), catalog_query.id)
        if dry_run:
            continue

        RestrictedCourseMetadata.store_canonical_record(course_dict)
        restricted_course_record = RestrictedCourseMetadata.store_record_with_query(
            course_dict, catalog_query,
        )
        results.append(restricted_course_record.content_key)

    restricted_course_run_keys = list(catalog_query.restricted_courses_by_run_key.keys())
    run_content_filter = {
        'content_type': COURSE_RUN,
        'key': restricted_course_run_keys,
    }
    course_run_payload = discovery_client.retrieve_metadata_for_content_filter(
        run_content_filter, QUERY_FOR_RESTRICTED_RUNS,
    )
    for course_run_dict in course_run_payload:
        course_run_key = get_content_key(course_run_dict)
        LOGGER.info(
            'Storing restricted course run %s for catalog_query %s',
            course_run_dict.get('key'), catalog_query.id,
        )
        if dry_run:
            continue

        # These are "top-level" course run dictionaries, which have aggregation_keys
        # from which we can determine the parent course key.
        course_run_record = RestrictedCourseMetadata.update_or_create_run(
            course_run_key=course_run_key,
            parent_content_key=get_parent_content_key(course_run_dict),
            course_run_dict=course_run_dict,
        )
        results.append(course_run_record.content_key)
    return results


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
