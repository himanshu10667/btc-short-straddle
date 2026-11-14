from nautilus_trader.adapters.bybit import (
    BybitDataClientConfig,
    BybitDataClientFactory,
    BybitEnvironment,
    BybitProductType,
)
from nautilus_trader.common import Environment
from nautilus_trader.live import LiveNode
from nautilus_trader.model import CryptoOption, TraderId, Venue
from nautilus_trader.trading import Strategy


class InstrumentDiscoveryStrategy(Strategy):
    def on_start(self):
        print("\n========== BTC OPTIONS INSTRUMENT DISCOVERY ==========")

        venue = Venue("BYBIT")

        try:
            instruments = self.cache.instruments(venue=venue)
        except Exception as exc:
            print(f"Could not read instrument cache: {exc}")
            return

        options = [
            instrument
            for instrument in instruments
            if isinstance(instrument, CryptoOption)
        ]

        btc_options = [
            option
            for option in options
            if "BTC" in str(option.underlying).upper()
            or "BTC" in str(option.symbol).upper()
        ]

        print(f"Total instruments in cache: {len(instruments)}")
        print(f"Options found: {len(options)}")
        print(f"BTC options found: {len(btc_options)}")

        if not btc_options:
            print("\nNo BTC options found in the cache yet.")
            print("We will investigate instrument loading next.")
            return

        btc_options.sort(
            key=lambda option: (
                option.expiration_ns,
                float(str(option.strike_price)),
                str(option.option_kind),
            )
        )

        print("\nAvailable BTC options:\n")

        for option in btc_options:
            print(
                f"Symbol: {option.id} | "
                f"Strike: {option.strike_price} | "
                f"Expiry: {option.expiration_utc} | "
                f"Type: {option.option_kind}"
            )

        print("\n========== DISCOVERY COMPLETE ==========\n")


def main():
    data_config = BybitDataClientConfig(
        environment=BybitEnvironment.TESTNET,
        product_types=[BybitProductType.OPTION],
    )

    node = (
        LiveNode.builder(
            "BTC-OPTIONS-DISCOVERY",
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

    # Strategies are registered on the built node, not the builder.
    node.add_strategy(InstrumentDiscoveryStrategy())

    print("Starting Bybit Testnet BTC options discovery...")
    print("Using public market data; no API credentials are configured.")
    print("No orders will be submitted.")
    print("Press Ctrl+C to stop.\n")

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nStopping node...")
    finally:
        node.dispose()
        print("Node disposed.")


if __name__ == "__main__":
    main()
