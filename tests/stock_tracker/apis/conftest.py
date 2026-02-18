import pytest
from fastapi.testclient import TestClient
from stock_tracker.apis.stock_tracker_backend import app


@pytest.fixture
def client():
    return TestClient(app)
