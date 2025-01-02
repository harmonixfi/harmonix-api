from sqlalchemy.sql import text


def get_pending_initiated_withdrawals_query():
    query = text(
        """
    WITH latest_initiated_withdrawals AS (
        SELECT 
            id,
            from_address,
            to_address,
            tx_hash,
            timestamp,
            input,
            block_number,
            method_id,
            ROW_NUMBER() OVER (PARTITION BY from_address ORDER BY timestamp DESC) AS rn
        FROM public.onchain_transaction_history
        WHERE method_id IN (:withdraw_method_id_1)
        AND to_address = ANY(:vault_addresses)
        AND timestamp >= :start_ts
        AND timestamp <= :end_ts
    ),
    has_later_completion AS (
        SELECT DISTINCT 
            i.from_address,
            i.tx_hash
        FROM latest_initiated_withdrawals i
        WHERE i.rn = 1
        AND EXISTS (
            SELECT 1
            FROM public.onchain_transaction_history c
            WHERE c.from_address = i.from_address
            AND to_address = ANY(:vault_addresses)
            AND c.method_id = :complete_method_id
            AND c.timestamp > i.timestamp
        )
    )
    SELECT *
    FROM latest_initiated_withdrawals i
    WHERE i.rn = 1
    AND NOT EXISTS (
        SELECT 1 
        FROM has_later_completion h 
        WHERE h.from_address = i.from_address
    );
    """
    )
    return query
