from datetime import datetime, timedelta, timezone
from hyperliquid.api import API
from hyperliquid.utils.types import (
    Any,
    Callable,
    Meta,
    SpotMeta,
    SpotMetaAndAssetCtxs,
    Optional,
    Subscription,
    cast,
    Cloid,
)
from hyperliquid.websocket_manager import WebSocketManager


class Info(API):
    def __init__(
        self,
        base_url: Optional[str] = None,
        skip_ws: Optional[bool] = False,
        meta: Optional[Meta] = None,
        spot_meta: Optional[SpotMeta] = None,
    ):
        super().__init__(base_url)
        if not skip_ws:
            self.ws_manager = WebSocketManager(self.base_url)
            self.ws_manager.start()
        if meta is None:
            meta = self.meta()

        if spot_meta is None:
            spot_meta = self.spot_meta()

        self.coin_to_asset = {
            asset_info["name"]: asset
            for (asset, asset_info) in enumerate(meta["universe"])
        }
        self.name_to_coin = {
            asset_info["name"]: asset_info["name"] for asset_info in meta["universe"]
        }

        # spot assets start at 10000
        for spot_info in spot_meta["universe"]:
            self.coin_to_asset[spot_info["name"]] = spot_info["index"] + 10000
            self.name_to_coin[spot_info["name"]] = spot_info["name"]
            base, quote = spot_info["tokens"]
            name = f'{spot_meta["tokens"][base]["name"]}/{spot_meta["tokens"][quote]["name"]}'
            if name not in self.name_to_coin:
                self.name_to_coin[name] = spot_info["name"]

    def user_points(self, address: str) -> float:
        future_time = datetime.now() - timedelta(minutes=30)
        timestamp = int(future_time.timestamp())
        return self.post(
            "/info",
            {
                "type": "userPoints",
                "user": address,
                "signature": {
                    "r": "0xe8a8cdd9604592bcf7c84228a5ee766b87aa2b5138384df0a8d9044a12f87be7",
                    "s": "0x7b142a3bbbbc4cffbe4cef272a73fd653af9a349d7d393ea193cfb73a1297f11",
                    "v": 28,
                },
                "timestamp": timestamp,
            },
        )

    def user_state(self, address: str) -> Any:

        return self.post("/info", {"type": "clearinghouseState", "user": address})

    def spot_user_state(self, address: str) -> Any:
        return self.post("/info", {"type": "spotClearinghouseState", "user": address})

    def open_orders(self, address: str) -> Any:

        return self.post("/info", {"type": "openOrders", "user": address})

    def frontend_open_orders(self, address: str) -> Any:

        return self.post("/info", {"type": "frontendOpenOrders", "user": address})

    def all_mids(self) -> Any:

        return self.post("/info", {"type": "allMids"})

    def user_fills(self, address: str) -> Any:

        return self.post("/info", {"type": "userFills", "user": address})

    def meta(self) -> Meta:

        return cast(Meta, self.post("/info", {"type": "meta"}))

    def meta_and_asset_ctxs(self) -> Any:

        return self.post("/info", {"type": "metaAndAssetCtxs"})

    def spot_meta(self) -> SpotMeta:
        """Retrieve exchange spot metadata

        POST /info

        Returns:
            {
                universe: [
                    {
                        tokens: [int, int],
                        name: str,
                        index: int,
                        isCanonical: bool
                    },
                    ...
                ],
                tokens: [
                    {
                        name: str,
                        szDecimals: int,
                        weiDecimals: int,
                        index: int,
                        tokenId: str,
                        isCanonical: bool
                    },
                    ...
                ]
            }
        """
        return cast(SpotMeta, self.post("/info", {"type": "spotMeta"}))

    def spot_meta_and_asset_ctxs(self) -> SpotMetaAndAssetCtxs:
        """Retrieve exchange spot asset contexts
        POST /info
        Returns:
            [
                {
                    universe: [
                        {
                            tokens: [int, int],
                            name: str,
                            index: int,
                            isCanonical: bool
                        },
                        ...
                    ],
                    tokens: [
                        {
                            name: str,
                            szDecimals: int,
                            weiDecimals: int,
                            index: int,
                            tokenId: str,
                            isCanonical: bool
                        },
                        ...
                    ]
                },
                [
                    {
                        dayNtlVlm: float string,
                        markPx: float string,
                        midPx: Optional(float string),
                        prevDayPx: float string,
                        circulatingSupply: float string,
                        coin: str
                    }
                    ...
                ]
            ]
        """
        return cast(
            SpotMetaAndAssetCtxs, self.post("/info", {"type": "spotMetaAndAssetCtxs"})
        )

    def funding_history(
        self, name: str, startTime: int, endTime: Optional[int] = None
    ) -> Any:
        """Retrieve funding history for a given coin

        POST /info

        Args:
            name (str): Coin to retrieve funding history for.
            startTime (int): Unix timestamp in milliseconds.
            endTime (int): Unix timestamp in milliseconds.

        Returns:
            [
                {
                    coin: str,
                    fundingRate: float string,
                    premium: float string,
                    time: int
                },
                ...
            ]
        """
        coin = self.name_to_coin[name]
        if endTime is not None:
            return self.post(
                "/info",
                {
                    "type": "fundingHistory",
                    "coin": coin,
                    "startTime": startTime,
                    "endTime": endTime,
                },
            )
        return self.post(
            "/info", {"type": "fundingHistory", "coin": coin, "startTime": startTime}
        )

    def user_funding_history(
        self, user: str, startTime: int, endTime: Optional[int] = None
    ) -> Any:
        """Retrieve a user's funding history
        POST /info
        Args:
            user (str): Address of the user in 42-character hexadecimal format.
            startTime (int): Start time in milliseconds, inclusive.
            endTime (int, optional): End time in milliseconds, inclusive. Defaults to current time.
        Returns:
            List[Dict]: A list of funding history records, where each record contains:
                - user (str): User address.
                - type (str): Type of the record, e.g., "userFunding".
                - startTime (int): Unix timestamp of the start time in milliseconds.
                - endTime (int): Unix timestamp of the end time in milliseconds.
        """
        if endTime is not None:
            return self.post(
                "/info",
                {
                    "type": "userFunding",
                    "user": user,
                    "startTime": startTime,
                    "endTime": endTime,
                },
            )
        return self.post(
            "/info", {"type": "userFunding", "user": user, "startTime": startTime}
        )

    def l2_snapshot(self, name: str) -> Any:
        """Retrieve L2 snapshot for a given coin

        POST /info

        Args:
            name (str): Coin to retrieve L2 snapshot for.

        Returns:
            {
                coin: str,
                levels: [
                    [
                        {
                            n: int,
                            px: float string,
                            sz: float string
                        },
                        ...
                    ],
                    ...
                ],
                time: int
            }
        """
        return self.post("/info", {"type": "l2Book", "coin": self.name_to_coin[name]})

    def candles_snapshot(
        self, name: str, interval: str, startTime: int, endTime: int
    ) -> Any:
        """Retrieve candles snapshot for a given coin

        POST /info

        Args:
            name (str): Coin to retrieve candles snapshot for.
            interval (str): Candlestick interval.
            startTime (int): Unix timestamp in milliseconds.
            endTime (int): Unix timestamp in milliseconds.

        Returns:
            [
                {
                    T: int,
                    c: float string,
                    h: float string,
                    i: str,
                    l: float string,
                    n: int,
                    o: float string,
                    s: string,
                    t: int,
                    v: float string
                },
                ...
            ]
        """
        req = {
            "coin": self.name_to_coin[name],
            "interval": interval,
            "startTime": startTime,
            "endTime": endTime,
        }
        return self.post("/info", {"type": "candleSnapshot", "req": req})

    def user_fees(self, address: str) -> Any:
        """Retrieve the volume of trading activity associated with a user.
        POST /info
        Args:
            address (str): Onchain address in 42-character hexadecimal format;
                            e.g. 0x0000000000000000000000000000000000000000.
        Returns:
            {
                activeReferralDiscount: float string,
                dailyUserVlm: [
                    {
                        date: str,
                        exchange: str,
                        userAdd: float string,
                        userCross: float string
                    },
                ],
                feeSchedule: {
                    add: float string,
                    cross: float string,
                    referralDiscount: float string,
                    tiers: {
                        mm: [
                            {
                                add: float string,
                                makerFractionCutoff: float string
                            },
                        ],
                        vip: [
                            {
                                add: float string,
                                cross: float string,
                                ntlCutoff: float string
                            },
                        ]
                    }
                },
                userAddRate: float string,
                userCrossRate: float string
            }
        """
        return self.post("/info", {"type": "userFees", "user": address})

    def query_order_by_oid(self, user: str, oid: int) -> Any:
        return self.post("/info", {"type": "orderStatus", "user": user, "oid": oid})

    def query_order_by_cloid(self, user: str, cloid: Cloid) -> Any:
        return self.post(
            "/info", {"type": "orderStatus", "user": user, "oid": cloid.to_raw()}
        )

    def query_referral_state(self, user: str) -> Any:
        return self.post("/info", {"type": "referral", "user": user})

    def query_sub_accounts(self, user: str) -> Any:
        return self.post("/info", {"type": "subAccounts", "user": user})

    def subscribe(
        self, subscription: Subscription, callback: Callable[[Any], None]
    ) -> int:
        if (
            subscription["type"] == "l2Book"
            or subscription["type"] == "trades"
            or subscription["type"] == "candle"
        ):
            subscription["coin"] = self.name_to_coin[subscription["coin"]]
        if self.ws_manager is None:
            raise RuntimeError("Cannot call subscribe since skip_ws was used")
        else:
            return self.ws_manager.subscribe(subscription, callback)

    def unsubscribe(self, subscription: Subscription, subscription_id: int) -> bool:
        if (
            subscription["type"] == "l2Book"
            or subscription["type"] == "trades"
            or subscription["type"] == "candle"
        ):
            subscription["coin"] = self.name_to_coin[subscription["coin"]]
        if self.ws_manager is None:
            raise RuntimeError("Cannot call unsubscribe since skip_ws was used")
        else:
            return self.ws_manager.unsubscribe(subscription, subscription_id)

    def name_to_asset(self, name: str) -> int:
        return self.coin_to_asset[self.name_to_coin[name]]
