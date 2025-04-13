"""
Video Catalog Errors
"""


class VideoCatalogError(Exception):
    pass


class TranscriptSummaryMissingError(VideoCatalogError):
    """Transcript summary is not available for a language"""
