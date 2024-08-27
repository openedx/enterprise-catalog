"""
Constants for api app.
"""

# Per-view cache timeouts
CONTAINS_CONTENT_ITEMS_VIEW_CACHE_TIMEOUT_SECONDS = 60 * 30
CURATION_CONFIG_READ_ONLY_VIEW_CACHE_TIMEOUT_SECONDS = 60 * 30
HIGHLIGHT_SET_READ_ONLY_VIEW_CACHE_TIMEOUT_SECONDS = 60 * 30


class CourseMode():
    """
    Content metadata course mode keys.

    Copied from https://github.com/edx/edx-platform/blob/831a8bcc/common/djangoapps/course_modes/models.py#L164
    """
    HONOR = "honor"
    PROFESSIONAL = "professional"
    VERIFIED = "verified"
    AUDIT = "audit"
    NO_ID_PROFESSIONAL_MODE = "no-id-professional"
    CREDIT_MODE = "credit"
    MASTERS = "masters"
    EXECUTIVE_EDUCATION = "executive-education"
    PAID_EXECUTIVE_EDUCATION = "paid-executive-education"
    UNPAID_EXECUTIVE_EDUCATION = "unpaid-executive-education"
    PAID_BOOTCAMP = "paid-bootcamp"
    UNPAID_BOOTCAMP = "unpaid-bootcamp"
