from datetime import datetime
import json
import pytest
from unittest.mock import call, patch, MagicMock


import logging
from services.bsx_service import get_list_claim_point, claim_point

from bg_tasks import bsx_point_claim_weelky


def create_mocked_get_response():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "epochs": [
            {
                "start_at": "2023-01-01T00:00:00Z",
                "end_at": "2023-01-02T00:00:00Z",
                "point": "100",
                "degen_point": "10",
                "status": "OPEN",
                "claim_deadline": "1672531200",  # Example timestamp
                "claimed_at": "0",
                "claimable": True,
            },
            {
                "start_at": "2023-01-03T00:00:00Z",
                "end_at": "2023-01-04T00:00:00Z",
                "point": "200",
                "degen_point": "20",
                "status": "OPEN",
                "claim_deadline": "1673126400",  # Example timestamp
                "claimed_at": "1672531200",
                "claimable": True,
            },
        ]
    }
    return mock_response


def create_mocked_post_response():
    mock_response_post = MagicMock()
    mock_response_post.status_code = 200
    return mock_response_post


@patch("requests.post")
@patch("requests.get")
@patch("services.bsx_service.get_list_claim_point")
@patch("services.bsx_service.claim_point")
@patch("bg_tasks.bsx_point_claim_weelky.logger")
def test_bsx_point_claim_weelky_success(
    mock_get_logger,
    mock_claim_point,
    mock_get_list_claim_point,
    mock_requests_get,
    mock_requests_post,
):
    mock_requests_get.return_value = create_mocked_get_response()
    mock_requests_post.return_value = create_mocked_post_response()

    # Mock `get_list_claim_point` to use the mocked HTTP response
    mock_bsx_points = [
        MagicMock(start_at=datetime(2023, 1, 1), end_at=datetime(2023, 1, 2)),
        MagicMock(start_at=datetime(2023, 1, 3), end_at=datetime(2023, 1, 4)),
    ]
    mock_get_list_claim_point.return_value = mock_bsx_points
    mock_claim_point.return_value = True

    # Call the function
    bsx_point_claim_weelky.bsx_point_claim_weelky()  # Adjust based on your module structure

    # Check if logger was called with appropriate messages
    expected_calls = [
        call.info("Starting BSX point claiming process"),
        call.info(f"Retrieved {len(mock_bsx_points)} BSX points to claim"),
        call.info(
            f"Claiming point 1/2: start_at={mock_bsx_points[0].start_at.isoformat()}Z, end_at={mock_bsx_points[0].end_at.isoformat()}Z"
        ),
        call.info("Successfully claimed point 1"),
        call.info(
            f"Claiming point 2/2: start_at={mock_bsx_points[1].start_at.isoformat()}Z, end_at={mock_bsx_points[1].end_at.isoformat()}Z"
        ),
        call.info("Successfully claimed point 2"),
        call.info(
            "BSX point claiming process completed. Successful claims: 2, Failed claims: 0"
        ),
    ]
    mock_get_logger.info.assert_has_calls(expected_calls, any_order=False)


@patch("requests.get")
@patch("services.bsx_service.get_list_claim_point")
@patch("services.bsx_service.claim_point")
@patch("bg_tasks.bsx_point_claim_weelky.logger")
def test_bsx_point_claim_weelky_failure(
    mock_get_logger, mock_claim_point, mock_get_list_claim_point, mock_requests_get
):
    # Mock the return values of get_list_claim_point and claim_point
    mock_requests_get.return_value = create_mocked_get_response()
    mock_claim_point.side_effect = Exception("Claim failed")

    # Call the function under test
    bsx_point_claim_weelky.bsx_point_claim_weelky()

    # Check if logger was called with appropriate error messages
    mock_get_logger.info.assert_any_call("Starting BSX point claiming process")
    mock_get_logger.info.assert_any_call(f"Retrieved 2 BSX points to claim")

    # Check the final summary logging
    mock_get_logger.info.assert_any_call(
        "BSX point claiming process completed. Successful claims: 0, Failed claims: 2"
    )


@patch("requests.get")
@patch("services.bsx_service.claim_point")
@patch("bg_tasks.bsx_point_claim_weelky.logger")
def test_bsx_point_claim_weelky_empty_list(
    mock_get_logger, mock_get_list_claim_point, mock_requests_get
):
    # Mock get_list_claim_point to return an empty list
    mock_response = create_mocked_get_response()
    mock_response.json.return_value = {"epochs": []}
    mock_requests_get.return_value = mock_response

    # Call the function under test
    bsx_point_claim_weelky.bsx_point_claim_weelky()

    # Check if logger was called with the empty list message
    mock_get_logger.info.assert_any_call("Starting BSX point claiming process")
    mock_get_logger.info.assert_any_call(f"Retrieved 0 BSX points to claim")

    # Check the final summary logging
    mock_get_logger.info.assert_any_call(
        "BSX point claiming process completed. Successful claims: 0, Failed claims: 0"
    )
