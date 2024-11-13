from datetime import datetime, timezone

from sqlalchemy import bindparam, func, text
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
from models.vaults import NetworkChain, Vault, VaultGroup, VaultMetadata

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), pool_pre_ping=True)


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
                datetime=datetime(2024, 1, 31, tzinfo=timezone.utc),
                price_per_share=1,
                vault_id=vault.id,
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
                datetime=datetime(2024, 1, 31, timezone=timezone.utc),
                price_per_share=1,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 9, timezone=timezone.utc),
                price_per_share=1.0000,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 16, timezone=timezone.utc),
                price_per_share=1.043481,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 2, 23, timezone=timezone.utc),
                price_per_share=1.066503,
                vault_id=vault.id,
            ),
            PricePerShareHistory(
                datetime=datetime(2024, 3, 1, timezone=timezone.utc),
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


def init_new_vault_metadata(session: Session):
    existing_vault = session.exec(
        select(Vault).where(Vault.slug == constants.GOLD_LINK_SLUG)
    ).first()
    if existing_vault:

        existing_vault_metadata = session.exec(
            select(VaultMetadata).where(VaultMetadata.vault_id == existing_vault.id)
        ).first()

        if existing_vault_metadata:
            return

        vault_metadata = VaultMetadata(
            vault_id=existing_vault.id,
            leverage=0,
            borrow_apr=0,
            goldlink_trading_account="0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa",
            health_factor=0,
            last_updated=datetime.now(tz=timezone.utc),
            open_position_size=0,
        )
        session.add(vault_metadata)
        session.commit()


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
        Vault(
            name="Koi Paradise with Pendle",
            vault_capacity=4 * 1e3,
            vault_currency="USDC",
            contract_address="0xC5d824572E20BB73DE991dC31b9802Fcb0A64D1b",
            slug="arbitrum-pendle-rseth-26sep2024",
            routes=None,
            category="real_yield",
            underlying_asset="rsETH",
            network_chain=NetworkChain.arbitrum_one,
            monthly_apy=5.789,
            weekly_apy=0,
            ytd_apy=0,
            apr=0,
            tvl=100,
            tags="pendle",
            max_drawdown=0,
            maturity_date="2024-09-26",
            owner_wallet_address="0xea065ed6E86f6b6a9468ae26366616AB2f5d4F21",
            is_active=False,
            strategy_name=constants.PENDLE_HEDGING_STRATEGY,
            pt_address="0x30c98c0139b62290e26ac2a2158ac341dcaf1333",
        ),
        Vault(
            name="Koi Paradise with Pendle",
            vault_capacity=4 * 1e3,
            vault_currency="USDC",
            contract_address="0xC71BA0E3C1FB9CBcB15fbC677e78C99aC1bc590B",
            slug="arbitrum-pendle-rseth-26dec2024",
            routes=None,
            category="real_yield",
            underlying_asset="rsETH",
            network_chain=NetworkChain.arbitrum_one,
            monthly_apy=0,
            weekly_apy=0,
            ytd_apy=0,
            apr=0,
            tvl=0,
            tags="pendle,new",
            max_drawdown=0,
            maturity_date="2024-12-26",
            owner_wallet_address="0xea065ed6E86f6b6a9468ae26366616AB2f5d4F21",
            is_active=False,
            strategy_name=constants.PENDLE_HEDGING_STRATEGY,
            pt_address="0x355ec27c9d4530de01a103fa27f884a2f3da65ef",
            pendle_market_address="0xcb471665bf23b2ac6196d84d947490fd5571215f",
        ),
        Vault(
            name="Koi & Chill with Kelp Gain",
            vault_capacity=4 * 1e6,
            vault_currency="USDC",
            contract_address="0xCf8Be38F161DB8241bbBDbaB4231f9DF62DBc820",
            slug=constants.KELPDAO_GAIN_VAULT_SLUG,
            routes='["kelpdao", "kelpdaogain"]',
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
            name="Gold Link",
            vault_capacity=4 * 1e3,
            vault_currency="USDC",
            slug=constants.GOLD_LINK_SLUG,
            contract_address="0x0d856b121cA1Cf862837Cb2BB03D181E25E9e892",
            routes=None,
            category="rewards",
            underlying_asset="LINK",
            network_chain=NetworkChain.arbitrum_one,
            monthly_apy=0,
            weekly_apy=0,
            ytd_apy=0,
            apr=0,
            tvl=0,
            tags="",
            max_drawdown=0,
            maturity_date="",
            owner_wallet_address="0xba90101dDFc56D1bdbb0CfBDD4E716BD03E14424",
            is_active=False,
            strategy_name=constants.DELTA_NEUTRAL_STRATEGY,
            pt_address="",
            pendle_market_address="",
            update_frequency="",
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


def seed_vault_category(session: Session):

    def try_add_vault_category(session: Session, value_type: str):
        stmt = text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 
                    FROM pg_enum 
                    WHERE enumlabel = '{value_type}'
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'vaultcategory')
                ) THEN
                    ALTER TYPE vaultcategory ADD VALUE '{value_type}';
                END IF;
            END $$;
            """
        )
        session.exec(stmt)

    try_add_vault_category(session, "rewards")


def init_db(session: Session) -> None:
    seed_vault_category(session)

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
        select(Vault).where(Vault.slug == "arbitrum-wbtc-vault")
    ).first()
    init_new_vault(session, solv_vault1)

    pendle_rs_26sep = session.exec(
        select(Vault).where(Vault.slug == "arbitrum-pendle-rseth-26sep2024")
    ).first()
    init_new_vault(session, pendle_rs_26sep)

    pendle_rs_26dec = session.exec(
        select(Vault).where(Vault.slug == "arbitrum-pendle-rseth-26dec2024")
    ).first()
    init_new_vault(session, pendle_rs_26dec)

    kelpgain_vault = session.exec(
        select(Vault).where(Vault.slug == constants.KELPDAO_GAIN_VAULT_SLUG)
    ).first()
    init_new_vault(session, kelpgain_vault)

    goldlink_vault = session.exec(
        select(Vault).where(Vault.slug == "arbitrum-leverage-delta-neutral-link")
    ).first()
    init_new_vault(session, goldlink_vault)
    init_new_vault_metadata(session)
