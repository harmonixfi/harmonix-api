from datetime import datetime


ALLOCATION_RATIO: float = 1 / 2


def calculate_projected_apy(last_funding_rate: float, component_apy: float) -> float:
    avg_8h_funding_rate = last_funding_rate * 24 * 365
    # Calculate the projected APY based on the average funding rate
    projected_apy = (
        avg_8h_funding_rate * ALLOCATION_RATIO
        + (component_apy / 100) * ALLOCATION_RATIO
    )
    return projected_apy * 100


def convert_to_nanoseconds(datetime: datetime) -> int:
    """
    Converts a date string in the format 'YYYY-MM-DD' to a UNIX timestamp in nanoseconds.

    Args:
        date_string (str): The date string to convert (e.g., '2024-06-05').

    Returns:
        int: The UNIX timestamp in nanoseconds.
    """
    nanoseconds = int(datetime.timestamp() * 1e9)
    return nanoseconds


def nanoseconds_to_datetime(nanoseconds):
    """
    Convert nanoseconds to a datetime object.

    :param nanoseconds: int, time in nanoseconds since epoch
    :return: datetime, converted datetime object
    """
    seconds = nanoseconds / 1e9
    return datetime.fromtimestamp(seconds)


def unixtimestamp_to_datetime(unixtimestamp):
    """
    Convert nanoseconds to a datetime object.

    :param nanoseconds: int, time in nanoseconds since epoch
    :return: datetime, converted datetime object
    """
    seconds = unixtimestamp / 1e3
    return datetime.fromtimestamp(seconds)


def datetime_to_unix_ms(dt: datetime) -> int:
    # Convert datetime to Unix timestamp in milliseconds
    return int(dt.timestamp() * 1000)
