"""Tests for POST /api/v1/wanted/batch-translate."""
import pytest
from unittest.mock import patch


@pytest.fixture
def client(temp_db):
    from app import create_app
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c


class TestBatchTranslate:
    def test_missing_item_ids(self, client):
        resp = client.post('/api/v1/wanted/batch-translate',
                           json={},
                           content_type='application/json')
        assert resp.status_code == 400
        assert 'item_ids' in resp.get_json().get('error', '')

    def test_empty_item_ids(self, client):
        resp = client.post('/api/v1/wanted/batch-translate',
                           json={'item_ids': []},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_valid_item_ids_queued(self, client):
        with patch('routes.wanted._retranslate_item', return_value='job-abc-123') as mock_rt:
            resp = client.post('/api/v1/wanted/batch-translate',
                               json={'item_ids': [1, 2, 3]},
                               content_type='application/json')
        assert resp.status_code == 202
        data = resp.get_json()
        assert data['queued'] == 3
        assert mock_rt.call_count == 3

    def test_item_not_found_skipped(self, client):
        with patch('routes.wanted._retranslate_item', return_value=None):
            resp = client.post('/api/v1/wanted/batch-translate',
                               json={'item_ids': [9999]},
                               content_type='application/json')
        assert resp.status_code == 202
        assert resp.get_json()['queued'] == 0
