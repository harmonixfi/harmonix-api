from datetime import datetime, timezone, timedelta
from collections import defaultdict
import traceback
import pandas as pd
from typing import Dict, List, Tuple

# Import necessary libraries
import pandas as pd
from sqlalchemy import create_engine, select, text
from sqlmodel import Session
from web3 import Web3
from core import constants
from core.db import engine
from datetime import datetime, timedelta

from models.user_rewards import UserRewardAudit, UserRewards

DEPOSIT_METHOD_ID = "0x71b8dc69"
WITHDRAW_METHOD_ID = "0x087fad4c"
WITHDRAW2_METHOD_ID = "0xb51d1d4f"

DEPOSIT_TOPIC = "0xf943cf10ef4d1e3239f4716ddecdf546e8ba8ab0e41deafd9a71a99936827e45"
WITHDRAW_TOPIC = "0x29835b361052a697c9f643de976223a59a332b7b4acaefa06267016e3e5d8efa"
HYPE_VAULT_ID = "c3010b21-25e0-4786-870c-774d2b91f4c5"

# Create a session
session = Session(engine)


from core.config import settings


def get_rewards_config_from_db(session: Session, current_date: datetime) -> Dict:
    """
    Fetch rewards distribution configuration from database starting from current week

    Args:
        session: SQLAlchemy session
        current_date: datetime object to determine current week

    Returns config in the format:
    {
        "weeks": [
            {
                "start_date": "2024-12-25",
                "end_date": "2024-12-31",
                "daily_reward": 3.0  # Calculated from total_reward * distribution_percentage / 7
            },
            ...
        ]
    }
    """
    # Ensure current_date is timezone-aware
    if current_date.tzinfo is None:
        current_date = current_date.replace(tzinfo=timezone.utc)

    # Query the reward_distribution_config table
    query = """
        WITH current_week AS (
            SELECT week 
            FROM config.reward_distribution_config rdc
            WHERE rdc.vault_id = :vault_id
                AND rdc.start_date <= :current_date
            ORDER BY rdc.start_date DESC
            LIMIT 1
        )
        SELECT 
            rdc.start_date,
            LEAD(rdc.start_date) OVER (ORDER BY rdc.start_date) as end_date,
            rdc.total_reward,
            rdc.distribution_percentage,
            rdc.week
        FROM config.reward_distribution_config rdc
        WHERE rdc.vault_id = :vault_id
            AND rdc.week >= (SELECT week FROM current_week)
        ORDER BY rdc.start_date ASC
    """

    result = session.execute(
        text(query), {"vault_id": HYPE_VAULT_ID, "current_date": current_date}
    )
    weeks = []

    for row in result:
        start_date = row.start_date.replace(tzinfo=timezone.utc)

        # Calculate end_date and ensure it's timezone-aware
        if row.end_date:
            end_date = row.end_date.replace(tzinfo=timezone.utc)
        else:
            end_date = start_date + timedelta(days=7)

        # Calculate daily reward from total weekly reward
        weekly_reward = row.total_reward * row.distribution_percentage
        daily_reward = weekly_reward / 7

        weeks.append(
            {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "daily_reward": float(daily_reward),
                "week": row.week,
            }
        )

    if not weeks:
        print(f"No reward configuration found for current date: {current_date}")
    else:
        print(
            f"Found {len(weeks)} weeks of configuration starting from week {weeks[0]['week']}"
        )

    return {"weeks": weeks}


def get_logs_from_tx_hash(tx_hash: str, topic: str = None) -> list:
    # Connect to the Ethereum node
    web3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))

    # Check if the connection is successful
    if not web3.is_connected():
        raise ConnectionError("Failed to connect to the Ethereum node.")

    # Get the transaction receipt
    tx_receipt = web3.eth.get_transaction_receipt(tx_hash)

    if not tx_receipt:
        raise ValueError(f"No transaction found for hash: {tx_hash}")

    # Extract logs from the transaction receipt
    logs = tx_receipt["logs"]

    # Filter logs by topic if provided
    if topic is not None:
        logs = [log for log in logs if log["topics"][0].hex() == topic]

    return logs


def _extract_pendle_event(entry):
    # Parse the account parameter from the topics field
    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'  # For deposit event

    # token_in = None
    # if len(entry["topics"]) >= 3:
    #     token_in = f'0x{entry["topics"][2].hex()[26:]}'

    # Parse the amount and shares parameters from the data field
    data = entry["data"].hex()

    if entry["topics"][0].hex() == settings.PENDLE_COMPLETE_WITHDRAW_EVENT_TOPIC:
        pt_amount = int(data[2:66], 16) / 1e18
        sc_amount = int(data[66 : 66 + 64], 16) / 1e6
        shares = int(data[66 + 64 : 66 + 2 * 64], 16) / 1e6
        total_amount = int(data[66 + 2 * 64 : 66 + 3 * 64], 16) / 1e6
        eth_amount = 0
    else:
        pt_amount = int(data[2:66], 16) / 1e18
        eth_amount = int(data[66 : 66 + 64], 16) / 1e18
        sc_amount = int(data[66 + 64 : 66 + 2 * 64], 16) / 1e6
        total_amount = int(data[66 + 64 * 2 : 66 + 3 * 64], 16) / 1e6
        shares = int(data[66 + 3 * 64 : 66 + 4 * 64], 16) / 1e6

    return pt_amount, eth_amount, sc_amount, total_amount, shares, from_address


def get_amount_from_tx(row) -> float:
    """
    Dựa vào 1 row trong df,
    - Gọi get_logs_from_tx_hash để lấy logs
    - Lọc topic deposit/withdraw,
    - Parse ra số tiền deposit/withdraw thực tế (vd sc_amount, total_amount)
    Trả về float (nếu deposit thì dương, nếu withdraw thì user rút 100% => ta return 'toàn bộ deposit' hoặc 0?),
    hoặc trả về None nếu không parse được.
    """
    tx_hash = row["tx_hash"]

    if row["method_id"] == DEPOSIT_METHOD_ID:
        # Ta muốn filter log deposit
        logs = get_logs_from_tx_hash(tx_hash, topic=DEPOSIT_TOPIC)
        if not logs:
            return 0.0

        # Mỗi tx deposit có thể có 1 log?
        # Ta parse log đầu tiên (hoặc lặp qua logs)
        event_data = _extract_pendle_event(logs[0])
        # event_data = (pt_amount, eth_amount, sc_amount, total_amount, shares, from_address)
        # Tuỳ theo “bạn muốn xài sc_amount hay total_amount là deposit”
        # Giả sử "total_amount" = deposit stable
        total_amount = event_data[3]
        return total_amount

    elif row["method_id"] == WITHDRAW_METHOD_ID:
        # Tương tự, filter log withdraw
        logs = get_logs_from_tx_hash(tx_hash, topic=WITHDRAW_TOPIC)
        if not logs:
            return 0.0

        event_data = _extract_pendle_event(logs[0])
        # Giả sử “total_amount” = số stable rút ra
        total_amount = event_data[3]
        return total_amount

    return 0.0  # default


def process_reward_record(session: Session, row, current_date: datetime):
    """Process and insert/update rewards for a single record."""
    try:
        # Get existing reward record for the user if any
        user_reward = session.exec(
            select(UserRewards)
            .where(UserRewards.vault_id == HYPE_VAULT_ID)
            .where(UserRewards.wallet_address == row["user_address"])
        ).first()
        if user_reward:
            user_reward = user_reward[0]

        # Store old reward value for audit
        old_value = user_reward.total_reward if user_reward else 0
        print(f"Processing reward for {row['user_address']}...")
        print(f"Current reward value: {old_value}")

        try:
            # Update existing reward record
            if user_reward:
                user_reward.total_reward += row["reward"]
                user_reward.updated_at = current_date
                print(f"Updated reward: {old_value} -> {user_reward.total_reward}")
            # Create new reward record
            else:
                user_reward = UserRewards(
                    vault_id=HYPE_VAULT_ID,
                    wallet_address=row["user_address"],
                    total_reward=row["reward"],
                    created_at=current_date,
                    updated_at=current_date,
                    partner_name=constants.HARMONIX,
                )
                session.add(user_reward)
                print(f"Created new reward record: {row['reward']}")

            session.commit()

            # Create audit record
            user_reward_audit = UserRewardAudit(
                user_points_id=user_reward.id,
                old_value=old_value,
                new_value=user_reward.total_reward,
                created_at=current_date,
            )
            session.add(user_reward_audit)

            # Commit changes
            session.commit()
            print(f"Successfully processed reward for {row['user_address'][:8]}")

        except Exception as db_error:
            print(f"Database operation failed: {str(db_error)}")
            session.rollback()
            raise

    except Exception as e:
        print(f"Failed to process rewards for user {row['user_address']}: {str(e)}")
        if session:
            session.rollback()
        raise


def insert_rewards_to_db(reward_df):
    """Insert all rewards from DataFrame into database."""
    current_date = datetime.now(tz=timezone.utc)
    session = Session(engine)

    print(f"Starting to process {len(reward_df)} reward records...")

    for index, row in reward_df.iterrows():
        try:
            process_reward_record(session, row, current_date)
        except Exception as e:
            print(f"Error processing row {index}: {str(e)}")
            traceback.print_exc()
            continue

    print("Completed processing all rewards")


class RewardsDistributionJob:
    def __init__(self):
        """
        Initialize the rewards distribution job with configuration

        config format:
        {
            "weeks": [
                {
                    "start_date": "2024-12-25",
                    "end_date": "2024-12-31",
                    "daily_reward": 3.0  # 21 tokens per week
                },
                {
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-07",
                    "daily_reward": 2.5  # 17.5 tokens per week
                }
            ]
        }
        """
        self.config = get_rewards_config_from_db(session, datetime.now(tz=timezone.utc))
        self.user_balances = defaultdict(float)
        self.reward_records = []

    def _get_week_config(self, date: datetime) -> Dict:
        """Get the configuration for a specific date"""
        for week in self.config["weeks"]:
            start = datetime.strptime(week["start_date"], "%Y-%m-%d")
            end = datetime.strptime(week["end_date"], "%Y-%m-%d")
            if start <= date <= end:
                return week
        return None

    def _calculate_initial_state(
        self, transactions_df: pd.DataFrame, target_date: datetime
    ) -> None:
        """Calculate user balances up to a specific date"""
        # Ensure target_date is timezone-aware
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=timezone.utc)

        # Convert target_date to pandas Timestamp with UTC timezone
        target_timestamp = pd.Timestamp(target_date)

        # Ensure DataFrame datetime column has UTC timezone
        if transactions_df["datetime"].dt.tz is None:
            transactions_df["datetime"] = transactions_df["datetime"].dt.tz_localize(
                "UTC"
            )

        # Filter transactions up to target date
        historical_tx = transactions_df[transactions_df["datetime"] <= target_timestamp]

        # Reset balances
        self.user_balances.clear()

        # Process historical transactions
        for _, tx in historical_tx.iterrows():
            wallet = tx["from_address"]
            if tx["method_id"] == DEPOSIT_METHOD_ID:
                deposit_amt = get_amount_from_tx(tx)
                self.user_balances[wallet] += deposit_amt
            elif tx["method_id"] in {WITHDRAW_METHOD_ID, WITHDRAW2_METHOD_ID}:
                self.user_balances[wallet] = 0.0

    def distribute_rewards(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """Main method to distribute rewards across multiple weeks"""
        current_date = datetime.now(tz=timezone.utc)

        # Ensure DataFrame datetime column has UTC timezone
        if transactions_df["datetime"].dt.tz is None:
            transactions_df["datetime"] = transactions_df["datetime"].dt.tz_localize(
                "UTC"
            )

        # Process each week
        for week in self.config["weeks"]:
            # Parse dates and ensure they're timezone-aware
            week_start = datetime.strptime(week["start_date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            week_end = datetime.strptime(week["end_date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

            # Skip future weeks
            if current_date < week_start:
                print(
                    f"Skipping future week {week['start_date']} to {week['end_date']}"
                )
                continue

            print(f"\nProcessing week: {week['start_date']} to {week['end_date']}")

            # Calculate initial state for this week
            self._calculate_initial_state(transactions_df, week_start)
            print(
                f"Initial state calculated. Total users with balance: {len(self.user_balances)}"
            )

            # Process daily rewards for this week
            self._process_week_rewards(
                transactions_df, week_start, week_end, week["daily_reward"]
            )

        return pd.DataFrame(self.reward_records)

    def _process_week_rewards(
        self,
        transactions_df: pd.DataFrame,
        week_start: datetime,
        week_end: datetime,
        daily_reward: float,
    ) -> None:
        """Process rewards for a specific week"""
        # Ensure datetime objects are timezone-aware
        if week_start.tzinfo is None:
            week_start = week_start.replace(tzinfo=timezone.utc)
        if week_end.tzinfo is None:
            week_end = week_end.replace(tzinfo=timezone.utc)

        # Convert to pandas Timestamps
        week_start_ts = pd.Timestamp(week_start)
        week_end_ts = pd.Timestamp(week_end)

        # Ensure DataFrame datetime column has UTC timezone
        if transactions_df["datetime"].dt.tz is None:
            transactions_df["datetime"] = transactions_df["datetime"].dt.tz_localize(
                "UTC"
            )

        # Filter transactions for this week
        week_mask = (transactions_df["datetime"] >= week_start_ts) & (
            transactions_df["datetime"] <= week_end_ts
        )
        week_transactions = transactions_df[week_mask]

        # Group by day
        grouped = week_transactions.groupby(pd.Grouper(key="datetime", freq="D"))
        current_date = pd.Timestamp(datetime.now(tz=timezone.utc))

        for day, day_df in grouped:
            if day > current_date:
                print(f"Skipping future date: {day.date()}")
                break

            print(f"\nProcessing day: {day.date()} - Transactions: {len(day_df)}")

            # Process day's transactions
            self._process_day_transactions(day_df)

            # Calculate and record daily rewards
            self._distribute_daily_rewards(day.to_pydatetime(), daily_reward)

    def _process_day_transactions(self, day_df: pd.DataFrame) -> None:
        """Process all transactions for a single day"""
        for _, tx in day_df.iterrows():
            wallet = tx["from_address"]
            if not wallet:
                continue

            if tx["method_id"] == DEPOSIT_METHOD_ID:
                deposit_amt = get_amount_from_tx(tx)
                self.user_balances[wallet] += deposit_amt
                print(
                    f"Deposit: {wallet[:8]}... Amount: {deposit_amt:.6f} New Balance: {self.user_balances[wallet]:.6f}"
                )

            elif tx["method_id"] in {WITHDRAW_METHOD_ID, WITHDRAW2_METHOD_ID}:
                old_balance = self.user_balances[wallet]
                self.user_balances[wallet] = 0.0
                print(f"Withdraw: {wallet[:8]}... Amount: {old_balance:.6f} -> 0")

    def _distribute_daily_rewards(self, day: datetime, daily_reward: float) -> None:
        """Calculate and record rewards for all users for a single day"""
        total_balance = sum(self.user_balances.values())
        print(f"End of day {day.date()} - Total Balance: {total_balance:.6f}")

        if total_balance > 0:
            for user_addr, bal in self.user_balances.items():
                if bal <= 0:
                    continue

                user_share = bal / total_balance
                user_daily_reward = user_share * daily_reward

                self.reward_records.append(
                    {
                        "date": day,
                        "user_address": user_addr,
                        "balance": bal,
                        "reward": user_daily_reward,
                    }
                )

                print(
                    f"Reward: {user_addr}... Balance: {bal:.6f} Share: {user_share:.4%} Reward: {user_daily_reward:.6f}"
                )


# Your SQL query
query = """
    SELECT * FROM public.onchain_transaction_history
    WHERE method_id in ('0x71b8dc69', '0x087fad4c', '0xb51d1d4f') 
    AND to_address = lower('0xc0e2b9ECABcA12D5024B2C11788B1cFaf972E5aa')
    ORDER BY timestamp ASC
"""

# Execute the query and fetch results
with session.begin():
    # Execute query and load into DataFrame
    df = pd.read_sql_query(query, engine)

# Convert timestamp to datetime
df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

df_sorted = df.sort_values(
    by="datetime"
)  # sắp xếp chronologically (cột 'datetime' là kiểu datetime)
df_sorted = df_sorted.reset_index(drop=True)

# Initialize and run the job
job = RewardsDistributionJob()
reward_df = job.distribute_rewards(df_sorted)

# Process rewards (using your existing DB logic)
insert_rewards_to_db(reward_df)
