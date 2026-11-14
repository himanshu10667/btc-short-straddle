import time
from datetime import datetime, timezone

from nautilus_trader.adapters.bybit import (
    BybitDataClientConfig,
    BybitDataClientFactory,
    BybitEnvironment,
    BybitProductType,
)
from nautilus_trader.common import Environment
from nautilus_trader.live import LiveNode
from nautilus_trader.model import (
    CryptoOption,
    IndexPriceUpdate,
    InstrumentId,
    TraderId,
    Venue,
)
from nautilus_trader.trading import Strategy


class ATMSelectionStrategy(Strategy):
    def on_start(self):
        print("\n========== BTC ATM STRADDLE SELECTION ==========")

        self.reference_id = InstrumentId.from_str(
            "BTCUSDT-LINEAR.BYBIT"
        )
        self.selected = False

        # Load available BTC option instruments.
        instruments = self.cache.instruments(venue=Venue("BYBIT"))

        self.btc_options = [
            option
            for option in instruments
            if isinstance(option, CryptoOption)
            and (
                "BTC" in str(option.underlying).upper()
                or "BTC" in str(option.symbol).upper()
            )
        ]

        print(f"BTC option instruments available: {len(self.btc_options)}")
        print(f"Subscribing to BTC index price: {self.reference_id}")
        print("Waiting for BTC index-price update...")

        # Subscribe to the underlying index-price feed.
        self.subscribe_index_prices(self.reference_id)

    def on_index_price(self, index_price: IndexPriceUpdate):
        if self.selected:
            return

        if index_price.instrument_id != self.reference_id:
            return

        try:
            btc_price = index_price.value.as_double()
        except AttributeError:
            btc_price = float(index_price.value)

        if btc_price <= 0:
            print(f"Ignoring invalid BTC index price: {btc_price}")
            return

        print(f"\nBTC index price received: ${btc_price:,.2f}")

        self.select_atm_options(btc_price)

    def select_atm_options(self, btc_price):
        now_ns = time.time_ns()

        # Exclude expired contracts.
        active_options = [
            option
            for option in self.btc_options
            if option.expiration_ns > now_ns
        ]

        if not active_options:
            print("No unexpired BTC options found.")
            return

        # Use the nearest available expiry.
        nearest_expiry = min(
            option.expiration_ns for option in active_options
        )

        expiry_options = [
            option
            for option in active_options
            if option.expiration_ns == nearest_expiry
        ]

        strikes = sorted({
            float(option.strike_price)
            for option in expiry_options
        })

        if not strikes:
            print("No strikes available for the nearest expiry.")
            return

        # Select the strike closest to the BTC index price.
        atm_strike = min(
            strikes,
            key=lambda strike: abs(strike - btc_price),
        )

        matching_options = [
            option
            for option in expiry_options
            if float(option.strike_price) == atm_strike
        ]

        call_option = next(
            (
                option for option in matching_options
                if "CALL" in str(option.option_kind).upper()
            ),
            None,
        )

        put_option = next(
            (
                option for option in matching_options
                if "PUT" in str(option.option_kind).upper()
            ),
            None,
        )

        expiry_date = datetime.fromtimestamp(
            nearest_expiry / 1_000_000_000,
            tz=timezone.utc,
        )

        print("\n========== ATM SELECTION RESULT ==========")
        print(f"BTC index price : ${btc_price:,.2f}")
        print(f"Selected strike : ${atm_strike:,.2f}")
        print(f"Expiry          : {expiry_date.isoformat()}")

        if call_option:
            print(f"CALL contract   : {call_option.id}")
        else:
            print("CALL contract   : Not found")

        if put_option:
            print(f"PUT contract    : {put_option.id}")
        else:
            print("PUT contract    : Not found")

        if call_option and put_option:
            print("\nATM STRADDLE PAIR FOUND SUCCESSFULLY.")
            self.selected = True
        else:
            print("\nCould not find both legs at the selected strike.")

        print("No orders have been submitted.")
        print("==========================================\n")

    def on_stop(self):
        print("ATM selection strategy stopped.")


def main():
    data_config = BybitDataClientConfig(
        environment=BybitEnvironment.TESTNET,
        product_types=[
            BybitProductType.OPTION,
            BybitProductType.LINEAR,
        ],
    )

    node = (
        LiveNode.builder(
            "BTC-ATM-INDEX-SELECTION",
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

    node.add_strategy(ATMSelectionStrategy())

    print("Starting Bybit Testnet ATM selection...")
    print("Public market data only. No API credentials required.")
    print("No orders will be submitted.")
    print("Press Ctrl+C to stop.")

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nStopping strategy...")
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
