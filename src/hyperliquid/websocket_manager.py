import asyncio
import json
import logging
import threading
import time
from collections import defaultdict

import websockets

from hyperliquid.utils.types import (
    Any,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Subscription,
    Tuple,
    WsMsg,
)

ActiveSubscription = NamedTuple(
    "ActiveSubscription",
    [("callback", Callable[[Any], None]), ("subscription_id", int)],
)


def subscription_to_identifier(subscription: Subscription) -> str:
    if subscription["type"] == "allMids":
        return "allMids"
    elif subscription["type"] == "l2Book":
        return f'l2Book:{subscription["coin"].lower()}'
    elif subscription["type"] == "trades":
        return f'trades:{subscription["coin"].lower()}'
    elif subscription["type"] == "userEvents":
        return "userEvents"
    elif subscription["type"] == "userFills":
        return f'userFills:{subscription["user"].lower()}'
    elif subscription["type"] == "candle":
        return f'candle:{subscription["coin"].lower()},{subscription["interval"]}'
    elif subscription["type"] == "orderUpdates":
        return "orderUpdates"
    elif subscription["type"] == "userFundings":
        return f'userFundings:{subscription["user"].lower()}'
    elif subscription["type"] == "userNonFundingLedgerUpdates":
        return f'userNonFundingLedgerUpdates:{subscription["user"].lower()}'


def ws_msg_to_identifier(ws_msg: WsMsg) -> Optional[str]:
    if ws_msg["channel"] == "pong":
        return "pong"
    elif ws_msg["channel"] == "allMids":
        return "allMids"
    elif ws_msg["channel"] == "l2Book":
        return f'l2Book:{ws_msg["data"]["coin"].lower()}'
    elif ws_msg["channel"] == "trades":
        trades = ws_msg["data"]
        if len(trades) == 0:
            return None
        else:
            return f'trades:{trades[0]["coin"].lower()}'
    elif ws_msg["channel"] == "user":
        return "userEvents"
    elif ws_msg["channel"] == "userFills":
        return f'userFills:{ws_msg["data"]["user"].lower()}'
    elif ws_msg["channel"] == "candle":
        return f'candle:{ws_msg["data"]["s"].lower()},{ws_msg["data"]["i"]}'
    elif ws_msg["channel"] == "orderUpdates":
        return "orderUpdates"
    elif ws_msg["channel"] == "userFundings":
        return f'userFundings:{ws_msg["data"]["user"].lower()}'
    elif ws_msg["channel"] == "userNonFundingLedgerUpdates":
        return f'userNonFundingLedgerUpdates:{ws_msg["data"]["user"].lower()}'


class WebSocketManager:
    def __init__(self, base_url: str):
        self.subscription_id_counter = 0
        self.ws_ready = False
        self.queued_subscriptions: List[Tuple[Subscription, ActiveSubscription]] = []
        self.active_subscriptions: Dict[str, List[ActiveSubscription]] = defaultdict(
            list
        )
        self.ws_url = f"ws{base_url[4:]}/ws"
        self.ping_task = None

    async def connect(self):
        """Kết nối tới WebSocket server và bắt đầu lắng nghe."""
        async with websockets.connect(self.ws_url) as websocket:
            self.ws_ready = True
            self.websocket = websocket
            self.ping_task = asyncio.create_task(self.send_ping())
            await self.on_open()
            await self.listen()

    async def send_ping(self):
        while True:
            await asyncio.sleep(50)
            logging.debug("WebSocket sending ping")
            await self.websocket.send(json.dumps({"method": "ping"}))

    async def listen(self):
        async for message in self.websocket:
            await self.on_message(message)

    async def on_message(self, message: str):
        logging.debug(f"on_message received: {message}")
        if message == "WebSocket connection established.":
            logging.debug(message)
            return

        ws_msg: WsMsg = json.loads(message)
        identifier = ws_msg_to_identifier(ws_msg)

        if identifier == "pong":
            logging.debug("WebSocket received pong")
            return

        if not identifier:
            logging.debug("WebSocket not handling empty message")
            return

        active_subscriptions = self.active_subscriptions.get(identifier, [])
        if not active_subscriptions:
            logging.warning(
                f"Unexpected WebSocket message from subscription: {identifier} - {message}"
            )
        else:
            for active_subscription in active_subscriptions:
                active_subscription.callback(ws_msg)

    async def on_open(self):
        logging.debug("WebSocket connection opened")

        # Đăng ký tất cả các subscription đang chờ
        for subscription, active_subscription in self.queued_subscriptions:
            await self.subscribe(
                subscription,
                active_subscription.callback,
                active_subscription.subscription_id,
            )

    async def subscribe(
        self,
        subscription: Subscription,
        callback: Callable[[Any], None],
        subscription_id: Optional[int] = None,
    ) -> int:
        if subscription_id is None:
            self.subscription_id_counter += 1
            subscription_id = self.subscription_id_counter

        if not self.ws_ready:
            logging.debug("WebSocket not ready, enqueueing subscription")
            self.queued_subscriptions.append(
                (subscription, ActiveSubscription(callback, subscription_id))
            )
        else:
            logging.debug(f"Subscribing to {subscription}")
            identifier = subscription_to_identifier(subscription)
            self.active_subscriptions[identifier].append(
                ActiveSubscription(callback, subscription_id)
            )

            if (
                identifier in ["userEvents", "orderUpdates"]
                and len(self.active_subscriptions[identifier]) > 1
            ):
                raise NotImplementedError(
                    f"Cannot subscribe to {identifier} multiple times"
                )

            await self.websocket.send(
                json.dumps({"method": "subscribe", "subscription": subscription})
            )

        return subscription_id

    async def unsubscribe(
        self, subscription: Subscription, subscription_id: int
    ) -> bool:
        if not self.ws_ready:
            raise NotImplementedError(
                "Cannot unsubscribe before WebSocket connection is ready"
            )

        identifier = subscription_to_identifier(subscription)
        active_subscriptions = self.active_subscriptions.get(identifier, [])
        new_active_subscriptions = [
            x for x in active_subscriptions if x.subscription_id != subscription_id
        ]

        if not new_active_subscriptions:
            await self.websocket.send(
                json.dumps({"method": "unsubscribe", "subscription": subscription})
            )

        self.active_subscriptions[identifier] = new_active_subscriptions
        return len(active_subscriptions) != len(new_active_subscriptions)
