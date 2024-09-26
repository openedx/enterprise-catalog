"""
Management command for fetching jobs skills from taxonomy connector
"""
import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.jobs.models import Job, JobSkill


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for fetching job skills from taxonomy connector

    Example Usage:
    >> python manage.py fetch_jobs_skills
    """
    help = (
        'Fetch the skills associated with jobs from taxonomy connector'
    )

    def _process_job_skills(self, results):
        """
        Process the job skills fetched from taxonomy connector.
        """
        for result in results:
            try:
                job, _ = Job.objects.update_or_create(
                    job_id=result.get('id'),
                    title=result.get('name'),
                    description=result.get('description'),
                    external_id=result.get('external_id')
                )
                job_skills = result.get('skills')
                for item in job_skills:
                    skill = item.get('skill')
                    JobSkill.objects.update_or_create(
                        job=job,
                        skill_id=skill.get('id'),
                        name=skill.get('name'),
                        significance=item.get('significance')
                    )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                job_id = result.get('id')
                logger.exception(f'Could not store job skills. job id {job_id} {exc}')

    def handle(self, *args, **options):
        """
        Fetch the skills associated with jobs from taxonomy connector.
        """
        page = 1
        try:
            results, has_next = DiscoveryApiClient().get_jobs_skills(page=page)
            self._process_job_skills(results)

            while has_next:
                page += 1
                results, has_next = DiscoveryApiClient().get_jobs_skills(page=page)
                self._process_job_skills(results)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(f'Could not retrieve job skills for page {page} {exc}')
