"""
Serializers for the AI Curation API.
"""
from rest_framework import serializers


class AICurationSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """
    Serializer for AI Curation.
    """
    query = serializers.CharField(max_length=300)
    catalog_name = serializers.CharField()
