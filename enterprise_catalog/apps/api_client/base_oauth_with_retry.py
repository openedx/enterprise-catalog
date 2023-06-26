from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException

from .base_oauth import BaseOAuthClient


class EnterpriseRetry(Retry):
    """
    A class to tweak which Exceptions are considered retryable by Retry
    """

    def _is_read_error(self, err: Exception) -> bool:
        """Errors that occur after the request has been started, so we should
        assume that the server began processing it.
        """
        super_result = super()._is_read_error(err)
        # this is triggered by a ProtocolError but isnt in the stack
        local_result = isinstance(err, RequestException)
        return super_result or local_result


class BaseOAuthClientWithRetry(BaseOAuthClient):
    """
    Base class for OAuth API clients wrapped in Retry.
    The value of exponential backoff (with jitter) is discussed here:
    https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    """
    def __init__(
            self,
            backoff_factor=2,
            max_retries=3,
            backoff_jitter=1,
            allowed_methods=Retry.DEFAULT_ALLOWED_METHODS,
            **kwargs
    ):
        super().__init__(**kwargs)
        retry = EnterpriseRetry(
            total=max_retries,
            backoff_factor=backoff_factor,
            backoff_jitter=backoff_jitter,
            allowed_methods=allowed_methods,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.client.mount('http://', adapter)
        self.client.mount('https://', adapter)
