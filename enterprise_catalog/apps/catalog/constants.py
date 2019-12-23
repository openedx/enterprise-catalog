import json


# ContentMetadata content_type choices
COURSE = 'course'
COURSE_RUN = 'course_run'
PROGRAM = 'program'
CONTENT_TYPE_CHOICES = [
    (COURSE, 'Course'),
    (COURSE_RUN, 'Course Run'),
    (PROGRAM, 'Program'),
]

# Course mode sorting based on slug
COURSE_MODE_SORT_ORDER = ['verified', 'professional', 'no-id-professional', 'audit', 'honor']

def json_serialized_course_modes():
    """
    :return: serialized course modes.
    """
    return json.dumps(COURSE_MODE_SORT_ORDER)
