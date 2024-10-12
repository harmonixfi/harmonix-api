from hyperliquid.info import Info


if __name__ == "__main__":
    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    user_state = info.user_points("0x243937d8c75fD743741dE1621c6c10abe579f4d2")
    print("Monthly APY:", user_state)
