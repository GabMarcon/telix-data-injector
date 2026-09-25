import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_requests_session(pool_size: int = 5) -> requests.Session:
    """Cria uma sessão HTTP com Connection Pooling e Auto-Retry."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session