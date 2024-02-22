"""
Throttle classes for AI Curation API.
"""
from rest_framework.throttling import AnonRateThrottle


class AICurationThrottle(AnonRateThrottle):
    rate = '10/minute'
