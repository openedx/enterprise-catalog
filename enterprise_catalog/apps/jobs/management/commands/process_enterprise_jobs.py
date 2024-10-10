"""
Management command for associating jobs with enterprises
"""
import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog
from enterprise_catalog.apps.jobs.models import Job, JobEnterprise, JobSkill


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for associating jobs with enterprises via common skills

    Example Usage:
    >> python manage.py process_enterprise_jobs
    """
    help = (
        'Associate jobs with enterprises via common skills'
    )

    def handle(self, *args, **options):
        """
        Associate jobs with enterprises via common skills
        """
        logger.info("Generating enterprise job association...")
        algolia_client = get_initialized_algolia_client()
        enterprise_uuids = set()
        enterprise_catalogs = EnterpriseCatalog.objects.all()
        for enterprise_catalog in enterprise_catalogs:
            enterprise_uuids.add(enterprise_catalog.enterprise_uuid)

        jobs = Job.objects.all()
        associated_jobs = set()
        for enterprise_uuid in enterprise_uuids:
            for job in jobs:
                try:
                    job_skills = JobSkill.objects.filter(job=job).order_by('-significance')[:3]  # Get top 3 skills
                    search_query = {
                        'filters': f'(skill_names:{job_skills[0].name} OR \
                            skill_names:{job_skills[1].name} OR \
                            skill_names:{job_skills[2]}.name) AND \
                            enterprise_customer_uuids:{enterprise_uuid}',
                        'maxFacetHits': 50
                    }
                    response = algolia_client.algolia_index.search_for_facet_values('skill_names', '', search_query)
                    for hit in response.get('facetHits', []):
                        if hit.get('count') > 1:
                            JobEnterprise.objects.update_or_create(
                                job=job,
                                enterprise_uuid=enterprise_uuid
                            )
                            associated_jobs.add(job.job_id)
                            break
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.error(
                        '[PROCESS_ENTERPRISE_JOBS] Failure in processing \
                        enterprise "%s" and job: "%s".',
                        enterprise_uuid,
                        job.job_id,
                        exc_info=True
                    )
                else:
                    JobEnterprise.objects.all().exclude(job_id__in=associated_jobs).delete()
