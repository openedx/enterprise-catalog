import logging

from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException

from .base_oauth import BaseOAuthClient


logger = logging.getLogger(__name__)


class EnterpriseRetry(Retry):
    """
    A class to tweak which Exceptions are considered retryable by Retry
    """

    def _is_read_error(self, err: Exception) -> bool:
        """
        Extending this method to account for requests.exceptions.RequestException
        """
        super_result = super()._is_read_error(err)
        # this is triggered by a ProtocolError but isnt in the stack
        local_result = isinstance(err, RequestException)
        return super_result or local_result

    def increment(
        self,
        method=None,
        url=None,
        response=None,
        error=None,
        _pool=None,
        _stacktrace=None,
    ):
        """
        This method is called before every retry, adding logging.
        """
        logger.info(f'EnterpriseRetry retrying {method} to {url}...')
        return super().increment(method, url, response, error, _pool, _stacktrace)


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
