from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, create_engine, select

from core import constants
from core.config import settings
from models.campaigns import Campaign
from models.pps_history import PricePerShareHistory
from models.referralcodes import ReferralCode
from models.reward_session_config import RewardSessionConfig
from models.reward_sessions import RewardSessions
from models.reward_thresholds import RewardThresholds
from models.user import User
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, Vault, VaultGroup

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported (models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/tiangolo/full-stack-fastapi-postgresql/issues/28


def init_pps_history(session: Session, vault: Vault):
    cnt = session.exec(
        select(func.count())
        .select_from(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault.id)
    ).one()

    if cnt == 0:
        pps_history_data = [
            PricePerShareHistory(
                datetime=datetime(2024, 1, 31), price_per_share=1, vault_id=vault.id
            )
        ]

        for pps in pps_history_data:
            session.add(pps)

        session.commit()


def init_vault_performance(session: Session, vault: Vault):
    cnt = session.exec(
        select(func.count())
        .select_from(VaultPerformance)
        .where(VaultPerformance.vault_id == vault.id)
    ).one()

    if cnt == 0:
        performance_hist = [
            VaultPerformance(
                datetime=datetime.now(timezone.utc),
                vault_id=vault.id,
                total_locked_value=0,
                apy_1m=0,
                apy_1w=0,
                benchmark=0,
                pct_benchmark=0,
                risk_factor=0,
                all_time_high_per_share=0,
                total_shares=0,
                sortino_ratio=0,
                downside_risk=0,
                earned_fee=0,
                unique_depositors=0,
                fee_structure='{"deposit_fee":0.0,"exit_fee":0.0,"performance_fee":10.0,"management_fee":1.0}',
            )
        ]

        for item in performance_hist:
            session.add(item)

        session.commit()


def seed_stablecoin_pps_history(session: Session, vault: Vault):
    cnt = session.exec(select(func.count()).select_from(PricePerShareHistory)).one()
    if cnt == 0:
        pps_history_data = [
            PricePerShareHistory(
                datetime=datetime(2024, 1, 31), price_per_share=1, vault_id=vault.id
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 9), price_per_share=1.0000, vault_id=vault.id
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 16),
                price_per_share=1.043481,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 23),
                price_per_share=1.066503,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 3, 1),
                price_per_share=1.151802,
                vault_id=vault.id,
            ),
        ]

        for pps in pps_history_data:
            session.add(pps)

        session.commit()


def seed_opitons_wheel_vault_performance(stablecoin_vault: Vault, session):
    cnt = session.exec(select(func.count()).select_from(VaultPerformance)).one()
    if cnt == 0:
        if stablecoin_vault:
            vault_performances = [
                VaultPerformance(
                    datetime=datetime(2024, 2, 9),
                    total_locked_value=650.469078,
                    apy_1m=0,
                    apy_1w=0,
                    benchmark=2454.89,
                    pct_benchmark=1.451064143,
                    vault_id=stablecoin_vault.id,
                ),
                VaultPerformance(
                    datetime=datetime(2024, 2, 16),
                    total_locked_value=1148.814994,
                    apy_1m=67.89769076,
                    apy_1w=821.4619023,
                    benchmark=2822.835139,
                    pct_benchmark=16.65668528,
                    vault_id=stablecoin_vault.id,
                ),
                VaultPerformance(
                    datetime=datetime(2024, 2, 23),
                    total_locked_value=1175.957697,
                    apy_1m=118.9935637,
                    apy_1w=212.2583925,
                    benchmark=3028.727421,
                    pct_benchmark=23.37528042,
                    vault_id=stablecoin_vault.id,
                ),
                VaultPerformance(
                    datetime=datetime(2024, 3, 1),
                    total_locked_value=1253.815827,
                    apy_1m=458.8042689,
                    apy_1w=5440.514972,
                    benchmark=3366.58661,
                    pct_benchmark=37.13798215,
                    vault_id=stablecoin_vault.id,
                ),
            ]

            for vp in vault_performances:
                session.add(vp)

        session.commit()


def seed_users(session: Session):
    cnt = session.exec(select(func.count()).select_from(User)).one()
    if cnt == 0:
        users = [
            User(
                wallet_address="0x7354F8aDFDfc6ca4D9F81Fc20d04eb8A7b11b01b",
            ),
            User(
                wallet_address="0x6DBd53C16e8024DcFb06CcAace1344fDfF12b0D9",
            ),
            User(
                wallet_address="0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa",
            ),
        ]
        for user in users:
            existing_user = session.exec(
                select(User).where(User.wallet_address == user.wallet_address)
            ).first()
            if not existing_user:
                session.add(user)
    session.commit()


def seed_referral_codes(session: Session):
    cnt = session.exec(select(func.count()).select_from(ReferralCode)).one()
    if cnt == 0:
        users = session.exec(select(User)).all()
        user_ids = [user.user_id for user in users]
        referral_codes = [
            ReferralCode(
                user_id=user_ids[0],
                code="referral1",
                usage_limit=50,
            ),
            ReferralCode(
                user_id=user_ids[1],
                code="referral2",
                usage_limit=50,
            ),
            ReferralCode(
                user_id=user_ids[2],
                code="referral3",
                usage_limit=50,
            ),
        ]
        for referral_code in referral_codes:
            session.add(referral_code)
    session.commit()


def seed_reward_sessions(session: Session):
    cnt = session.exec(select(func.count()).select_from(RewardSessions)).one()
    if cnt == 0:
        reward_sessions = [
            RewardSessions(
                session_name="Session 1",
                start_date=datetime(2024, 1, 1),
                partner_name=constants.HARMONIX,
            )
        ]
        for reward_session in reward_sessions:
            session.add(reward_session)
    session.commit()


def seed_reward_session_config(session: Session):
    cnt = session.exec(select(func.count()).select_from(RewardSessionConfig)).one()
    if cnt == 0:
        reward_session = session.exec(
            select(RewardSessions).where(RewardSessions.session_name == "Session 1")
        ).first()
        reward_session_configs = [
            RewardSessionConfig(
                session_id=reward_session.session_id,
                start_delay_days=69,
                max_points=5000000,
                created_at=datetime.now(),
            ),
        ]
        for reward_session_config in reward_session_configs:
            session.add(reward_session_config)
    session.commit()


def seed_campaigns(session: Session):
    cnt = session.exec(select(func.count()).select_from(Campaign)).one()
    if cnt == 0:
        campaigns = [
            Campaign(
                name=constants.Campaign.KOL_AND_PARTNER.value,
                status=constants.Status.ACTIVE.value,
            ),
            Campaign(
                name=constants.Campaign.REFERRAL_101.value,
                status=constants.Status.ACTIVE.value,
            ),
        ]
        for campaign in campaigns:
            session.add(campaign)
    session.commit()


def seed_reward_thresholds(session: Session):
    cnt = session.exec(select(func.count()).select_from(RewardThresholds)).one()
    if cnt == 0:
        reward_thresholds = [
            RewardThresholds(
                tier=0,
                threshold=0,
                commission_rate=0.05,
            ),
            RewardThresholds(
                tier=1,
                threshold=0,
                commission_rate=0.06,
            ),
            RewardThresholds(
                tier=2,
                threshold=500000,
                commission_rate=0.07,
            ),
            RewardThresholds(
                tier=3,
                threshold=1000000,
                commission_rate=0.08,
            ),
            RewardThresholds(
                tier=4,
                threshold=1500000,
                commission_rate=0.09,
            ),
        ]
        for reward_threshold in reward_thresholds:
            session.add(reward_threshold)
    session.commit()


def init_new_vault(session: Session, vault: Vault):
    existing_vault = session.exec(select(Vault).where(Vault.slug == vault.slug)).first()
    if existing_vault:
        init_pps_history(session, vault)
        init_vault_performance(session, vault)


def seed_vaults(session: Session):
    kelpdao_group = session.exec(
        select(VaultGroup).where(VaultGroup.name == "Koi & Chill with Kelp DAO")
    ).first()

    # Create initial data
    vaults = [
        Vault(
            name="Options Wheel Vault",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address=settings.ROCKONYX_STABLECOIN_ADDRESS,
            slug="options-wheel-vault",
        ),
        Vault(
            name="Delta Neutral Vault",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address=settings.ROCKONYX_DELTA_NEUTRAL_VAULT_ADDRESS,
            slug="delta-neutral-vault",
        ),
        Vault(
            name="Restaking Delta Neutral Vault",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address=settings.ROCKONYX_RENZO_ZIRCUIT_RESTAKING_DELTA_NEUTRAL_VAULT_ADDRESS,
            slug="renzo-zircuit-restaking-delta-neutral-vault",
            routes='["renzo", "zircuit"]',
            category="points",
            network_chain=NetworkChain.ethereum,
        ),
        Vault(
            name="Restaking Delta Neutral Vault",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address=settings.ROCKONYX_KELPDAO_ARB_RESTAKING_DELTA_NEUTRAL_VAULT_ADDRESS,
            slug="kelpdao-restaking-delta-neutral-vault",
            routes='["kelpdao"]',
            category="points",
            network_chain=NetworkChain.arbitrum_one,
        ),
        Vault(
            name="Koi & Chill with Kelp DAO",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address="",
            slug="ethereum-kelpdao-restaking-delta-neutral-vault",
            routes='["kelpdao", "zircuit"]',
            category="points",
            network_chain=NetworkChain.ethereum,
            group_id=kelpdao_group.id if kelpdao_group else None,
            monthly_apy=0,
            weekly_apy=0,
            ytd_apy=0,
            apr=0,
            tvl=0,
            is_active=False,
            max_drawdown=0,
            strategy_name=constants.DELTA_NEUTRAL_STRATEGY,
        ),
        Vault(
            name="The Golden Guardian with Solv",
            vault_capacity=4 * 1e3,
            vault_currency="WBTC",
            contract_address="",
            slug="arbitrum-wbtc-vault",
            routes=None,
            category="real_yield",
            network_chain=NetworkChain.arbitrum_one,
            monthly_apy=0,
            weekly_apy=0,
            ytd_apy=0,
            apr=0,
            tvl=0,
            max_drawdown=0,
            owner_wallet_address="0x75bE1a23160B1b930D4231257A83e1ac317153c8",
            is_active=False,
            strategy_name=constants.STAKING_STRATEGY,
        ),
    ]

    for vault in vaults:
        existing_vault = session.exec(
            select(Vault).where(Vault.slug == vault.slug)
        ).first()
        if not existing_vault:
            session.add(vault)

    session.commit()


def seed_group(session: Session):
    groups = [
        VaultGroup(
            name="Koi & Chill with Kelp DAO",
        )
    ]

    for group in groups:
        existing_group = session.exec(
            select(VaultGroup).where(VaultGroup.name == group.name)
        ).first()
        if not existing_group:
            session.add(group)

    session.commit()


def seed_options_wheel_vault(session: Session):
    # Seed data for VaultPerformance for Stablecoin Vault
    stablecoin_vault = session.exec(
        select(Vault).where(Vault.slug == "options-wheel-vault")
    ).first()

    seed_opitons_wheel_vault_performance(stablecoin_vault, session)
    seed_stablecoin_pps_history(session, stablecoin_vault)
    seed_users(session)
    seed_referral_codes(session)
    seed_reward_sessions(session)
    seed_reward_session_config(session)
    seed_campaigns(session)
    seed_reward_thresholds(session)


def init_db(session: Session) -> None:
    seed_group(session)
    seed_vaults(session)

    seed_options_wheel_vault(session)

    renzo_vault = session.exec(
        select(Vault).where(Vault.slug == "renzo-zircuit-restaking-delta-neutral-vault")
    ).first()
    init_new_vault(session, renzo_vault)

    kelpdao_vault = session.exec(
        select(Vault).where(Vault.slug == "kelpdao-restaking-delta-neutral-vault")
    ).first()
    init_new_vault(session, kelpdao_vault)

    kelpdao_vault1 = session.exec(
        select(Vault).where(
            Vault.slug == "ethereum-kelpdao-restaking-delta-neutral-vault"
        )
    ).first()
    init_new_vault(session, kelpdao_vault1)

    solv_vault1 = session.exec(
        select(Vault).where(
            Vault.slug == "arbitrum-wbtc-vault"
        )
    ).first()
    init_new_vault(session, solv_vault1)
