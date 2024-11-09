import asyncio
import logging
import boto3
import json
import time

from core.config import settings
from log import setup_logging_to_console
from notifications import telegram_bot
from notifications.message_builder import send_telegram_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
sqs_client = boto3.client(
    "sqs",
    aws_access_key_id=settings.SNS_SYSTEM_API_KEY,
    aws_secret_access_key=settings.SNS_SYSTEM_API_SECRET,
    region_name="ap-southeast-1"
)
queue_url = settings.SNS_SYSTEM_MONITORING_URL


async def process_message(message_body):
    try:
        logger.info("Received SNS message: %s", message_body)
        alert_details = "CPU usage on Server A has exceeded 90%."
        await telegram_bot.send_alert(
            send_telegram_alert(alert_details),
            channel="error",
        )
    except Exception as e:
        logger.error("Error processing message system_monitoring_sqs_listener: %s", e)


async def listener_to_sqs():
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )
            logger.info("Received response from SQS: %s", response)

            if "Messages" in response:
                for message in response["Messages"]:
                    message_body = json.loads(message["Body"])

                    await process_message(message_body)
                    sqs_client.delete_message(
                        QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                    )
            else:
                logger.info("No new messages. Waiting...")
            time.sleep(5)
        except Exception as e:
            logger.error("Error in system_monitoring_sqs_listener: %s", e)


if __name__ == "__main__":
    setup_logging_to_console()
    logger.info("Starting the SQS listener for system monitoring...")
    asyncio.run(listener_to_sqs())
