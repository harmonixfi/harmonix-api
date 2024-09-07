import logging
from datetime import datetime
from sqlmodel import Session

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from services.bsx_service import claim_point, get_list_claim_point

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def bsx_point_claim_weelky():
    try:
        logger.info("Starting BSX point claiming process")
        bsx_points = get_list_claim_point()
        logger.info(f"Retrieved {len(bsx_points)} BSX points to claim")

        successful_claims = 0
        failed_claims = 0

        for index, bsx_point in enumerate(bsx_points, start=1):
            logger.info(
                f"Claiming point {index}/{len(bsx_points)}: start_at={bsx_point.start_at}, end_at={bsx_point.end_at}"
            )
            try:
                claim_result = claim_point(bsx_point.start_at, bsx_point.end_at)
                if claim_result:
                    logger.info(f"Successfully claimed point {index}")
                    successful_claims += 1
                else:
                    logger.warning(f"Failed to claim point {index}")
                    failed_claims += 1
            except Exception as claim_error:
                logger.error(f"Error claiming point {index}: {str(claim_error)}")
                failed_claims += 1

        logger.info(
            f"BSX point claiming process completed. Successful claims: {successful_claims}, Failed claims: {failed_claims}"
        )
    except Exception as e:
        logger.error(f"Error occurred during BSX point claiming process: {str(e)}")


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("bsx_point_claim_weelky", logger=logger)
    claim_bsx_point_daily()
