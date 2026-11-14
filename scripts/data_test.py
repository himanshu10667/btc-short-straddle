from nautilus_trader.adapters.bybit import (
    BybitDataClientConfig,
    BybitDataClientFactory,
    BybitEnvironment,
    BybitProductType,
)
from nautilus_trader.common import Environment
from nautilus_trader.live import LiveNode
from nautilus_trader.model import TraderId


def main():
    # Configure Bybit Testnet public options market data.
    data_config = BybitDataClientConfig(
        environment=BybitEnvironment.TESTNET,
        product_types=[BybitProductType.OPTION],
    )

    # Build a data-only NautilusTrader node.
    node = (
        LiveNode.builder(
            "BTC-OPTIONS-DATA-TEST",
            TraderId.from_str("STRADDLE-001"),
            Environment.LIVE,
        )
        .add_data_client(
            "BYBIT",
            BybitDataClientFactory(),
            data_config,
        )
        .build()
    )

    print("Starting Bybit Testnet options data connection...")
    print("No API credentials configured. No orders will be submitted.")

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nStopping node...")
    finally:
        node.dispose()
        print("Node disposed.")


if __name__ == "__main__":
    main()
