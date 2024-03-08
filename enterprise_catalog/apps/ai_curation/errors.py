"""
AI curation errors
"""

USER_MESSAGE = "Something went wrong. Please wait a minute and try again. If the issue persists, please reach out to your contact at edX."  # pylint: disable=line-too-long


class AICurationError(Exception):
    def __init__(self, message=USER_MESSAGE, dev_message=None, status_code=None):
        super().__init__(message)
        self.message = message
        self.dev_message = dev_message or message
        self.status_code = status_code


class InvalidJSONResponseError(AICurationError):
    """Invalid JSON response received"""
