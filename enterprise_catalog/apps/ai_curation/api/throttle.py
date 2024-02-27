"""
Throttle classes for AI Curation API.
"""
from rest_framework.throttling import AnonRateThrottle


class PostAICurationThrottle(AnonRateThrottle):
    rate = '10/minute'

    def allow_request(self, request, view):
        if request.method == "POST":
            return super().allow_request(request, view)
        return True


class GetAICurationThrottle(AnonRateThrottle):
    rate = '1/second'

    def allow_request(self, request, view):
        if request.method == "GET":
            return super().allow_request(request, view)
        return True
