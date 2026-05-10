import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import api
from api import app

class TestAPI(unittest.TestCase):

    def setUp(self):
        """Set up Flask test client and test API key before each test."""
        app.config['TESTING'] = True
        self.client = app.test_client()
        api.VALID_API_KEYS = {'test-key'}

    def test_health_check_returns_200(self):
        """Health endpoint should always return 200 with required fields."""
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('status', data)
        self.assertIn('database', data)
        self.assertIn('timestamp', data)
        self.assertIn('api', data)

    def test_add_metric_no_api_key(self):
        """POST without API key should return 401."""
        response = self.client.post('/api/v1/metrics', json={})
        self.assertEqual(response.status_code, 401)

    def test_add_metric_wrong_api_key(self):
        """POST with wrong API key should return 401."""
        response = self.client.post(
            '/api/v1/metrics',
            json={},
            headers={"X-API-Key": "wrong-key"}
        )
        self.assertEqual(response.status_code, 401)

    def test_get_metrics_no_api_key(self):
        """GET without API key should return 401."""
        response = self.client.get('/api/v1/metrics')
        self.assertEqual(response.status_code, 401)

    def test_add_metric_missing_host(self):
        """POST missing host field should return 400."""
        response = self.client.post(
            '/api/v1/metrics',
            json={
                "ip": "10.0.0.1",
                "metrics": {"cpu_usage": 10.0, "mem_used_mb": 512.0, "disk_free_gb": 20.0}
            },
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 400)

    def test_add_metric_missing_ip(self):
        """POST missing ip field should return 400."""
        response = self.client.post(
            '/api/v1/metrics',
            json={
                "host": "10.0.0.1",
                "metrics": {"cpu_usage": 10.0, "mem_used_mb": 512.0, "disk_free_gb": 20.0}
            },
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 400)

    def test_add_metric_missing_metrics(self):
        """POST missing metrics fields should return 400."""
        response = self.client.post(
            '/api/v1/metrics',
            json={
                "host": "10.0.0.1",
                "ip": "10.0.0.1",
                "metrics": {}
            },
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 400)

    @patch('api.get_sql_connection')
    def test_add_metric_success(self, mock_conn):
        """POST with valid data and API key should return 201."""
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        response = self.client.post(
            '/api/v1/metrics',
            json={
                "host": "10.0.0.1",
                "ip": "10.0.0.1",
                "metrics": {
                    "cpu_usage": 45.0,
                    "mem_used_mb": 512.0,
                    "disk_free_gb": 20.0
                }
            },
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['host'], '10.0.0.1')
        
        # Verify timestamp is present and in correct format
        self.assertIn('timestamp', data)
        timestamp_str = data['timestamp']
        # Parse timestamp and verify it's approximately now (within 5 seconds)
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        time_diff = abs((now - timestamp).total_seconds())
        self.assertLess(time_diff, 5, f"Timestamp {timestamp_str} differs from now by {time_diff} seconds")

    @patch('api.get_sql_connection')
    def test_get_metrics_no_results(self, mock_conn):
        """GET with valid API key but no matching data should return 404."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        response = self.client.get(
            '/api/v1/metrics',
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 404)

    @patch('api.get_sql_connection')
    def test_get_metrics_with_results(self, mock_conn):
        """GET with valid API key and data should return 200 with results."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "host": "10.0.0.1", "ip": "10.0.0.1", "cpu_usage": 45.0,
             "mem_used_mb": 512.0, "disk_free_gb": 20.0, "timestamp": "2026-05-02 12:00:00"}
        ]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_connection.__enter__ = MagicMock(return_value=mock_connection)
        mock_connection.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_connection

        response = self.client.get(
            '/api/v1/metrics',
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['count'], 1)
        self.assertIn('results', data)

    @patch('api.get_sql_connection')
    def test_add_metric_db_error(self, mock_conn):
        """POST should return 500 when database raises an exception."""
        mock_conn.side_effect = Exception("DB connection failed")

        response = self.client.post(
            '/api/v1/metrics',
            json={
                "host": "10.0.0.1",
                "ip": "10.0.0.1",
                "metrics": {
                    "cpu_usage": 45.0,
                    "mem_used_mb": 512.0,
                    "disk_free_gb": 20.0
                }
            },
            headers={"X-API-Key": "test-key"}
        )
        self.assertEqual(response.status_code, 500)


if __name__ == '__main__':
    unittest.main(verbosity=2)
