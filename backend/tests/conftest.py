import pytest, requests, os

BASE_URL = "https://semester-sync-7.preview.emergentagent.com"

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s
