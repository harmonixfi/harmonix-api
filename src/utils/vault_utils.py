ALLOCATION_RATIO: float = 1 / 2


def calculate_projected_apy(last_funding_rate: float, component_apy: float) -> float:
    avg_8h_funding_rate = last_funding_rate * 24 * 365
    # Calculate the projected APY based on the average funding rate
    projected_apy = (
        avg_8h_funding_rate * ALLOCATION_RATIO
        + (component_apy / 100) * ALLOCATION_RATIO
    )
    return projected_apy * 100
