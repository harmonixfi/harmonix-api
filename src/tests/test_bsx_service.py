import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock
from services.bsx_service import get_list_claim_bsx_point, BSXPoint, bsx_base_url
import requests


class TestBSXService(unittest.TestCase):

    def setUp(self):
        self.mock_api_response = {
            "epochs": [
                {
                    "start_at": "1648771200000000000",
                    "end_at": "1648857600000000000",
                    "point": "100.5",
                    "degen_point": "10.5",
                    "status": "completed",
                    "claim_deadline": "1649462400000000000",
                    "claimed_at": "1649030400000000000",
                    "claimable": True,
                },
                {
                    "start_at": "1648857600000000000",
                    "end_at": "1648944000000000000",
                    "point": "150.75",
                    "degen_point": "15.75",
                    "status": "ongoing",
                    "claim_deadline": "1649548800000000000",
                    "claimed_at": "0",
                    "claimable": False,
                },
            ]
        }

    @patch("services.bsx_service.requests.get")
    def test_get_list_claim_bsx_point_success(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_api_response
        mock_get.return_value = mock_response

        result = get_list_claim_bsx_point()

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], BSXPoint)
        self.assertEqual(
            result[0].start_at, datetime(2022, 4, 1, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            result[0].end_at, datetime(2022, 4, 2, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(result[0].point, 100.5)
        self.assertEqual(result[0].degen_point, 10.5)
        self.assertEqual(result[0].status, "completed")
        self.assertEqual(
            result[0].claim_deadline, datetime(2022, 4, 9, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            result[0].claimed_at, datetime(2022, 4, 4, 0, 0, tzinfo=timezone.utc)
        )
        self.assertTrue(result[0].claimable)

        self.assertIsNone(result[1].claimed_at)

    @patch("services.bsx_service.requests.get")
    def test_get_list_claim_bsx_point_api_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as context:
            get_list_claim_bsx_point()
        self.assertIn("Request failed with status 500", str(context.exception))

    @patch("services.bsx_service.requests.get")
    def test_get_list_claim_bsx_point_network_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("Network error")
        with self.assertRaises(Exception) as context:
            get_list_claim_bsx_point()
        self.assertIn(
            "Error occurred while fetching BSX points: Network error",
            str(context.exception),
        )
