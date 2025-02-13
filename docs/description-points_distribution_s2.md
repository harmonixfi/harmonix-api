# 📌 Dynamic Points Reward System - Documentation

## **Overview**
The Dynamic Points Reward System manages **reward programs** based on user deposits in **vaults**. Users earn points based on their **balance, holding time, and loyalty bonuses**.

---

## **1️⃣ USERS - User Information Table**
📌 **Purpose:** Stores basic user information.

| **Column**        | **Description** |
|------------------|----------------|
| `user_id`       | **Unique User ID** |
| `wallet_address` | **User's cryptocurrency wallet address** |
| `created_at`     | **Account creation timestamp** |
| `updated_at`     | **Last update timestamp** |

💡 **Example:**
- User with `user_id = 12345` and wallet `0xABC...XYZ`
- When they join a vault, the system retrieves information from this table.

---

## **2️⃣ VAULTS - Vault Information Table**
📌 **Purpose:** Stores information about vaults where users deposit funds.

| **Column**          | **Description** |
|-------------------|----------------|
| `id`             | **Unique vault ID** |
| `name`           | **Vault name** |
| `tvl`            | **Total Value Locked in the vault** |
| `apr`            | **Annual Percentage Rate (APR)** |
| `vault_currency` | **Currency used in the vault (ETH, USDT, etc.)** |
| `contract_address` | **Smart contract address of the vault** |

💡 **Example:**
- Vault **ETH-Staking** has `APR = 5%`, `tvl = 1,000,000 USDT`.
- When a user deposits, they earn points based on **balance & holding time**.

---

## **3️⃣ USER_PORTFOLIO - User Deposits Tracking**
📌 **Purpose:** Tracks the amount deposited by each user in a vault.

| **Column**          | **Description** |
|---------------------|----------------|
| `id`               | **Unique record ID for each deposit** |
| `vault_id`         | **Vault where the user deposited** |
| `user_address`     | **User's wallet address** |
| `total_balance`    | **Current balance in the vault** |
| `init_deposit`     | **Initial deposit amount** |
| `trade_start_date` | **Deposit start date** |
| `trade_end_date`   | **Withdrawal date (if applicable)** |

💡 **Example:**
- User deposits **1,000 USDT** into the ETH-Staking vault on **01/01/2024**.
- If they haven’t withdrawn, `trade_end_date` remains **empty**.

---

## **4️⃣ REWARD_SESSIONS - Reward Programs Tracking**
📌 **Purpose:** Manages different reward sessions.

| **Column**           | **Description** |
|---------------------|----------------|
| `session_id`       | **Unique session ID** |
| `session_name`     | **Reward session name (e.g., Season 1)** |
| `start_date`       | **Session start date** |
| `end_date`         | **Session end date (if applicable)** |
| `max_points`       | **Maximum points that can be distributed** |
| `points_distributed` | **Total points distributed so far** |

💡 **Example:**
- **Season 1** runs from **01/01/2024 - 31/03/2024**.
- **Maximum points available: 1,000,000**.

---

## **5️⃣ USER_POINTS - User Earned Points**
📌 **Purpose:** Stores the points each user has earned.

| **Column**          | **Description** |
|------------------|----------------|
| `id`            | **Unique points record ID** |
| `user_id`       | **User who earned the points** |
| `vault_id`      | **Vault where points were earned** |
| `session_id`    | **Associated reward session** |
| `points`        | **Total points earned** |
| `created_at`    | **Timestamp when points were granted** |

💡 **Example:**
- User deposits **1000 USDT**, holds for **10 days**, and earns **100 points**.

---

## **6️⃣ USER_POINTS_HISTORY - Points History Tracking**
📌 **Purpose:** Records all changes in user points over time.

| **Column**          | **Description** |
|------------------|----------------|
| `id`            | **Unique history record ID** |
| `user_points_id`| **Reference to `USER_POINTS`** |
| `point`        | **Points added in this update** |
| `created_at`    | **Timestamp of the update** |

💡 **Example:**
- `01/01`: User had **100 points**.
- `02/01`: User earned **10 more points** → History shows **110 points**.

---

## **7️⃣ TIME_FACTOR - Time-Based Multiplier Tracking**
📌 **Purpose:** The longer a user holds funds, the more bonus points they earn.

| **Column**         | **Description** |
|-----------------|----------------|
| `id`           | **Unique time factor ID** |
| `user_id`      | **User associated with this record** |
| `vault_id`     | **Vault ID** |
| `days_held`    | **Total number of days funds were held** |
| `factor`       | **Bonus multiplier based on days held** |
| `last_updated` | **Last time the factor was updated** |

💡 **Example:**
- User holds funds **10 days** → `factor = 1.1` (10% bonus).
- User holds funds **100 days** → `factor = 2.0` (2x points).

---

## **8️⃣ LOYALTY_BONUS - Additional Bonus for Long-Term Users**
📌 **Purpose:** Grants additional points based on total earned points.

| **Column**         | **Description** |
|-----------------|----------------|
| `id`           | **Unique loyalty bonus ID** |
| `user_id`      | **User receiving the bonus** |
| `session_id`   | **Related reward session** |
| `bonus_points` | **Extra points awarded** |
| `created_at`   | **Bonus allocation timestamp** |

💡 **Formula:**

y = 0.015 × ln(Total Points + 1)

💡 **Example:**
- User has **1000 points** → Bonus = **0.10 points/hour**.
- User has **10,000 points** → Bonus = **0.14 points/hour**.

---

## **📌 Summary**
✅ **Users deposit funds into vaults** (`USER_PORTFOLIO`).  
✅ **Every hour, the system calculates points** (`USER_POINTS`).  
✅ **Loyalty Bonus is included automatically**.  
✅ **Holding funds longer increases rewards** (`TIME_FACTOR`).  
✅ **System logs all changes for transparency** (`USER_POINTS_HISTORY`).

📌 **This documentation provides a complete overview of how the Dynamic Points Reward System operates.** 🚀