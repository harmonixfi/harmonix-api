from abc import abstractmethod
import uuid

from sqlmodel import Session, select

from models.apy_component import APYComponent
from models.vault_apy_breakdown import VaultAPYBreakdown, VaultAPYComponent


class APYComponentService:
    def __init__(
        self, vault_id: uuid.UUID, current_apy: float, period: int, session: Session
    ):
        self.vault_id = vault_id
        self.current_apy = current_apy
        self.session = session
        self.period = period

    @abstractmethod
    def get_component_values(self) -> dict:
        """Return the APY component values. Must be implemented by subclasses."""
        pass

    def save(self):
        component_values = self.get_component_values()
        self.save_vault_apy_components(
            self.vault_id, self.current_apy, component_values, self.period
        )

    def save_vault_apy_components(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        component_values: dict,
        period: int,
    ):
        vault_apy = self.upsert_vault_apy(vault_id, current_apy, period)
        for component_name, component_apy in component_values.items():
            self.update_or_create_component(
                vault_apy.id, component_name, component_apy, period
            )

        self.session.commit()

    def upsert_vault_apy(
        self,
        vault_id: uuid.UUID,
        total_apy: float,
        period: int,
    ) -> VaultAPYBreakdown:
        vault_apy = self.session.exec(
            select(VaultAPYBreakdown)
            .where(VaultAPYBreakdown.vault_id == vault_id)
            .where(VaultAPYBreakdown.period == period)
        ).first()

        if not vault_apy:
            vault_apy = VaultAPYBreakdown(vault_id=vault_id)

        vault_apy.period = period
        vault_apy.total_apy = total_apy
        self.session.add(vault_apy)
        self.session.commit()

        return vault_apy

    def update_or_create_component(
        self, vault_apy_breakdown_id, component_name, component_apy, period: int
    ):
        component = self.session.exec(
            select(VaultAPYComponent).where(
                VaultAPYComponent.vault_apy_breakdown_id == vault_apy_breakdown_id,
                VaultAPYComponent.component_name == component_name,
                VaultAPYComponent.period == period,
            )
        ).first()

        if component:
            component.component_apy = component_apy
        else:
            component = VaultAPYComponent(
                vault_apy_breakdown_id=vault_apy_breakdown_id,
                component_name=component_name,
                component_apy=component_apy,
                period=period,
            )

        self.session.add(component)


class KelpDaoArbitrumApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        rs_eth_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.rs_eth_value = rs_eth_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.RS_ETH: self.rs_eth_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class KelpDaoApyComponentService(APYComponentService):

    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        rs_eth_value: float,
        ae_usd_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.rs_eth_value = rs_eth_value
        self.ae_usd_value = ae_usd_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.RS_ETH: self.rs_eth_value,
            APYComponent.AE_USD: self.ae_usd_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class RenzoApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        ez_eth_value: float,
        ae_usd_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.ez_eth_value = ez_eth_value
        self.ae_usd_value = ae_usd_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.EZ_ETH: self.ez_eth_value,
            APYComponent.AE_USD: self.ae_usd_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class DeltaNeutralApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        wst_eth_value: float,
        ae_usd_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.wst_eth_value = wst_eth_value
        self.ae_usd_value = ae_usd_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.WST_ETH: self.wst_eth_value,
            APYComponent.AE_USD: self.ae_usd_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class BSXApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        wst_eth_value: float,
        bsx_point_value: float,
        funding_fee_value: float,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, session)
        self.wst_eth_value = wst_eth_value
        self.bsx_point_value = bsx_point_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.WST_ETH: self.wst_eth_value,
            APYComponent.BSX_POINT: self.bsx_point_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class OptionWheelApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        wst_eth_value: float,
        usde_usdc_value: float,
        option_yield_value: float,
        eth_gains: float,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, session)
        self.wst_eth_value = wst_eth_value
        self.usde_usdc_value = usde_usdc_value
        self.option_yield_value = option_yield_value
        self.eth_gains = eth_gains

    def get_component_values(self) -> dict:
        return {
            APYComponent.WST_ETH: self.wst_eth_value,
            APYComponent.USDCe_USDC: self.usde_usdc_value,
            APYComponent.OPTIONS_YIELD: self.option_yield_value,
            APYComponent.ETH_GAINS: self.eth_gains,
        }


class PendleApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        fixed_value: float,
        hyperliquid_point_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.fixed_value = fixed_value
        self.hyperliquid_point_value = hyperliquid_point_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.FIXED_YIELD: self.fixed_value,
            APYComponent.HL_POINT: self.hyperliquid_point_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class Pendle26Jun2025ApyComponentService(APYComponentService):

    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        fixed_value: float,
        hyperliquid_reward_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.fixed_value = fixed_value
        self.hyperliquid_reward_value = hyperliquid_reward_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.FIXED_YIELD: self.fixed_value,
            APYComponent.HYPE_REWARDS: self.hyperliquid_reward_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class GoldLinkApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        arb_reward_value: float,
        funding_fee_value: float,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, session)
        self.arb_reward_value = arb_reward_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.ARB_REWARDS: self.arb_reward_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class RethinkApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        wst_eth_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.wst_eth_value = wst_eth_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.WST_ETH: self.wst_eth_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }


class HypeApyComponentService(APYComponentService):
    def __init__(
        self,
        vault_id: uuid.UUID,
        current_apy: float,
        hype_reward_value: float,
        funding_fee_value: float,
        period: int,
        session: Session,
    ):
        super().__init__(vault_id, current_apy, period, session)
        self.hype_reward_value = hype_reward_value
        self.funding_fee_value = funding_fee_value

    def get_component_values(self) -> dict:
        return {
            APYComponent.HYPE_REWARDS: self.hype_reward_value,
            APYComponent.FUNDING_FEES: self.funding_fee_value,
        }
