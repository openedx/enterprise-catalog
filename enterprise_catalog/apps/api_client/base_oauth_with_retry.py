from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_oauth import BaseOAuthClient


class BaseOAuthClientWithRetry(BaseOAuthClient):
    """
    Base class for OAuth API clients wrapped in Retry.
    """
    def __init__(self, backoff_factor=2, max_retries=3, **kwargs):
        super().__init__(**kwargs)
        retry = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.client.mount('http://', adapter)
        self.client.mount('https://', adapter)
