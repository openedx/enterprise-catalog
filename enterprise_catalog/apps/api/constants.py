"""
Constants for api app.
"""


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
