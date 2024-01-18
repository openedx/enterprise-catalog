from uuid import uuid4

from django.db import models
from django.utils.translation import gettext as _
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    LEARNER_PATHWAY,
    PROGRAM,
)
from enterprise_catalog.apps.catalog.models import ContentMetadata


class EnterpriseCurationConfig(TimeStampedModel):
    """
    Top-level container for all curations related to an enterprise.
    What's nice about this model:
    * Top-level container to hold anything related to catalog curation for an enterprise
    (there might be a time where we want types of curation besides highlights).
    * Gives us place to grow horizontally for fields related to a single enterprise's curation behavior.

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
        unique=True,
        db_index=True,
    )
    is_highlight_feature_active = models.BooleanField(
        null=False,
        default=True,
    )
    can_only_view_highlight_sets = models.BooleanField(
        null=False,
        default=False,
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Enterprise curation")
        verbose_name_plural = _("Enterprise curations")
        app_label = 'curation'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return f"<EnterpriseCurationConfig ({self.uuid}) for EnterpriseCustomer '{self.enterprise_uuid}'>"


class HighlightSet(TimeStampedModel):
    """
    One enterprise curation may produce multiple catalog highlight sets.
    What's nice about this model:
    * Could have multiple highlight sets per customer.
    * Could have multiple highlight sets per catalog (maybe we don't want to allow this now, but
    we might want it for highlight cohorts later).

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
        # It was decided during a 2022-11-08 standup to allow duplicate-named HighlightSets, at least for the MVP.
        unique=False,
    )
    enterprise_curation = models.ForeignKey(
        EnterpriseCurationConfig,
        blank=False,
        null=False,
        related_name='catalog_highlights',
        on_delete=models.deletion.CASCADE,
    )
    # can the learners see it?
    is_published = models.BooleanField(
        default=False,
        null=False,
    )
    history = HistoricalRecords()

    class Meta:
        app_label = 'curation'

    @property
    def card_image_url(self):
        """
        Returns the card image URL representing this highlight set.

        Notes:
        * `card_image_url` is derived by using the image of the earliest content added by the enterprise admin.  That
          way, the image is deterministic, and relatively stable after subsequent modifications of the highlight set
          selections.  After the initial highlight set creation, the only thing that can change the highlight set card
          image is removal of the first content added.

        Returns:
            str: URL of the selected card image.  None if no card image is found.
        """
        # In our add_content() view function, multiple requested content keys may be added in the same transaction, but
        # in practice that still results in distinct `created` values, which means we can still use that field for
        # sorting without worrying about duplicates.
        sorted_content = self.highlighted_content.order_by('created')

        # Finally, pick an image.  Ostensibly, it's that of the first highlighted content, but we also want to make sure
        # that we pick an existing card image.
        for content in sorted_content:
            url = content.card_image_url
            if url:
                return url

        # At this stage, one of the following must be true:
        #   * this highlight set does not contain any content, or
        #   * no content in this highlight set contains a card image.
        return None


class HighlightedContent(TimeStampedModel):
    """
    One HighlightSet can contain 0 or more HighlightedContent records.

    What's nice about this model:
    * Can highlight any kind of content that lives in enterprise-catalog
    (courses, programs, or course runs if necessary - though maybe we want to block that?)
    * Can use counts() in views that add highlights to enforce a max highlight content count per set.

    TODO: is there a way to easily record which catalog(s) were applicable for the enterprise
    when some content was added to the highlight set?

    .. no_pii:
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
    )
    catalog_highlight_set = models.ForeignKey(
        HighlightSet,
        blank=False,
        null=True,
        related_name='highlighted_content',
        on_delete=models.deletion.CASCADE,
    )
    content_metadata = models.ForeignKey(
        ContentMetadata,
        blank=False,
        null=True,
        related_name='highlighted_content',
        on_delete=models.deletion.CASCADE,
    )
    history = HistoricalRecords()

    class Meta:
        app_label = 'curation'
        unique_together = ('catalog_highlight_set', 'content_metadata')

    @property
    def content_type(self):
        """
        Returns the content type of the associated ContentMetadata.
        """
        if not self.content_metadata:
            return None
        return self.content_metadata.content_type

    @property
    def content_key(self):
        """
        Returns the content key of the associated ContentMetadata.
        """
        if not self.content_metadata:
            return None
        return self.content_metadata.content_key

    @property
    def aggregation_key(self):
        """
        Returns the aggregation key of the associated ContentMetadata.
        """
        if not self.content_metadata:
            return None
        return self.content_metadata.aggregation_key

    @property
    def title(self):
        """
        Returns the title from the raw metadata of the associated ContentMetadata object.
        """
        if not self.content_metadata:
            return None
        return self.content_metadata.json_metadata.get('title')  # pylint: disable=no-member

    @property
    def course_run_statuses(self):
        """
        Returns the status of the associated ContentMetadata.
        """
        if not self.content_metadata:
            return None
        return self.content_metadata.json_metadata.get('course_run_statuses')  # pylint: disable=no-member

    @property
    def card_image_url(self):
        """
        Returns the image URL from the raw metadata of the associated ContentMetadata object.

        Returns:
            str: URL of the card image.  None if no card image is found.
        """
        if not self.content_metadata:
            return None

        content_type = self.content_type
        # aside: pylint doesn't know that self.content_metadata.json_metadata is dict-like, so we have to silence all
        # the warnings.
        if content_type == COURSE:
            return self.content_metadata.json_metadata.get('image_url')  # pylint: disable=no-member
        if content_type == COURSE_RUN:
            return self.content_metadata.json_metadata.get('image_url')  # pylint: disable=no-member
        elif content_type == PROGRAM:
            return self.content_metadata.json_metadata.get('card_image_url')  # pylint: disable=no-member
        elif content_type == LEARNER_PATHWAY:
            try:
                # pylint: disable=invalid-sequence-index
                return self.content_metadata.json_metadata['card_image']['card']['url']
            except (KeyError, TypeError):
                # KeyError covers the case where any of the keys along the path are missing,
                # TypeError covers the case where any of the values along the path are JSON null.
                return None
        else:
            # Defend against case where we add more content types before updating this code.
            return None

    @property
    def authoring_organizations(self):
        """
        Fetch the authoring organizations from the raw metadata of the associated ContentMetadata object.

        Notes:
        * There may be more than one authoring organization.
        * The following content types are unsupported, and result in an empty list:
          - `COURSERUN` content logically does have an authoring organization, but the metadata blob only contains the
            UUID of the org instead of a pretty name.
          - `LEARNER_PATHWAY` similar to courseruns, this content type doesn't have content metdata blobs with _direct_
            references to organiation pretty names, just course and program content keys.

        Returns:
            list of dict: Metadata about each found authoring organization.
        """
        if not self.content_metadata:
            return []

        content_type = self.content_type
        owners = []
        if content_type == COURSE:
            owners = self.content_metadata.json_metadata.get('owners')  # pylint: disable=no-member
        elif content_type == PROGRAM:
            owners = self.content_metadata.json_metadata.get('authoring_organizations')  # pylint: disable=no-member

        return [
            {
                'uuid': owner['uuid'],
                'name': owner['name'],
                'logo_image_url': owner['logo_image_url'],
            }
            for owner in owners
        ]
