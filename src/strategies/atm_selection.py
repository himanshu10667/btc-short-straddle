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

from src.strategies.paper_execution import PaperStraddleSimulator


PAPER_QUANTITY = "0.01"
STOP_LOSS_PCT = "0.01"
TAKE_PROFIT_PCT = "0.02"
MAX_QUOTE_AGE_SECONDS = 5
MAX_QUOTE_TIMESTAMP_DIFFERENCE_NS = 5_000_000_000


def display_field(option, field):
    value = getattr(option, field, None)
    return value if value is not None else "Not available"


class ATMSelectionStrategy(Strategy):
    def on_start(self):
        print("\n========== BTC ATM STRADDLE STRATEGY ==========")
        print("Environment       : BYBIT MAINNET")
        print("Market data       : LIVE PUBLIC DATA")
        print("Execution         : PAPER SIMULATION ONLY")
        print(f"Paper quantity    : {PAPER_QUANTITY} per leg")
        print(f"Stop-loss         : {float(STOP_LOSS_PCT) * 100:.2f}%")
        print(f"Take-profit       : {float(TAKE_PROFIT_PCT) * 100:.2f}%")

        self.reference_id = InstrumentId.from_str(
            "BTCUSDT-LINEAR.BYBIT"
        )

        self.selected = False
        self.call_option_id = None
        self.put_option_id = None
        self.latest_quotes = {}
        self.paper_simulator = None
        self.paper_started = False

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

        active_options = [
            option
            for option in self.btc_options
            if option.expiration_ns > now_ns
        ]

        if not active_options:
            print("No unexpired BTC options found.")
            return

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
        print(
            f"CALL contract   : "
            f"{call_option.id if call_option else 'Not found'}"
        )
        print(
            f"PUT contract    : "
            f"{put_option.id if put_option else 'Not found'}"
        )

        if not (call_option and put_option):
            print("\nCould not find both legs at the selected strike.")
            print("Will wait for another index-price update.")
            return

        self.print_contract_specs("CALL", call_option)
        self.print_contract_specs("PUT", put_option)

        self.call_option_id = call_option.id
        self.put_option_id = put_option.id
        self.selected = True

        # Create the paper simulator only after both contracts are selected.
        self.paper_simulator = PaperStraddleSimulator(
            call_id=self.call_option_id,
            put_id=self.put_option_id,
            quantity=PAPER_QUANTITY,
            stop_loss_pct=STOP_LOSS_PCT,
            take_profit_pct=TAKE_PROFIT_PCT,
        )

        print("\nATM STRADDLE PAIR FOUND SUCCESSFULLY.")
        print("Subscribing to both option quote feeds...")

        self.subscribe_quotes(self.call_option_id)
        self.subscribe_quotes(self.put_option_id)

        print(f"CALL subscription: {self.call_option_id}")
        print(f"PUT subscription : {self.put_option_id}")
        print("Waiting for valid quote updates from both options.")
        print("Paper execution will begin when both quotes are valid.")
        print("No real orders will be submitted.")
        print("==========================================\n")

    def print_contract_specs(self, label, option):
        print(f"\n========== {label} CONTRACT SPECIFICATIONS ==========")

        fields = [
            "id",
            "underlying",
            "quote_currency",
            "settlement_currency",
            "is_inverse",
            "strike_price",
            "option_kind",
            "expiration_ns",
            "price_precision",
            "size_precision",
            "price_increment",
            "size_increment",
            "multiplier",
            "lot_size",
            "min_quantity",
            "max_quantity",
            "min_notional",
            "max_notional",
        ]

        for field in fields:
            print(f"{field:22}: {display_field(option, field)}")

        print("====================================================")

    def on_quote(self, quote):
        instrument_id = quote.instrument_id

        if instrument_id not in (
            self.call_option_id,
            self.put_option_id,
        ):
            return

        try:
            bid = quote.bid_price.as_double()
            ask = quote.ask_price.as_double()
            bid_size = quote.bid_size.as_double()
            ask_size = quote.ask_size.as_double()
        except AttributeError:
            print(f"Could not read quote data for {instrument_id}")
            return

        self.latest_quotes[instrument_id] = {
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "ts_event": quote.ts_event,
            "received_at": time.monotonic(),
        }

        leg_name = (
            "CALL" if instrument_id == self.call_option_id else "PUT"
        )

        print(
            f"{leg_name} quote | "
            f"Bid: {bid:.8f} | Ask: {ask:.8f} | "
            f"Bid size: {bid_size:.4f} | Ask size: {ask_size:.4f}"
        )

        if (
            self.call_option_id not in self.latest_quotes
            or self.put_option_id not in self.latest_quotes
        ):
            print("Waiting for the other option's first quote...")
            return

        call = self.latest_quotes[self.call_option_id]
        put = self.latest_quotes[self.put_option_id]

        call_age = time.monotonic() - call["received_at"]
        put_age = time.monotonic() - put["received_at"]

        if (
            call_age > MAX_QUOTE_AGE_SECONDS
            or put_age > MAX_QUOTE_AGE_SECONDS
        ):
            print("Combined premium unavailable: stale quote.")
            return

        if (
            abs(call["ts_event"] - put["ts_event"])
            > MAX_QUOTE_TIMESTAMP_DIFFERENCE_NS
        ):
            print(
                "Combined premium unavailable: "
                "quote timestamps differ by over 5 seconds."
            )
            return

        combined_bid = (
            call["bid"] + put["bid"]
            if call["bid"] > 0 and put["bid"] > 0
            else None
        )

        combined_ask = (
            call["ask"] + put["ask"]
            if call["ask"] > 0 and put["ask"] > 0
            else None
        )

        print("\n========== BTC STRADDLE QUOTE SUMMARY ==========")
        print(
            f"CALL | Bid: {call['bid']:.2f} | Ask: {call['ask']:.2f} "
            f"| Bid size: {call['bid_size']:.4f} "
            f"| Ask size: {call['ask_size']:.4f}"
        )
        print(
            f"PUT  | Bid: {put['bid']:.2f} | Ask: {put['ask']:.2f} "
            f"| Bid size: {put['bid_size']:.4f} "
            f"| Ask size: {put['ask_size']:.4f}"
        )

        print(f"CALL quote age: {call_age:.2f}s")
        print(f"PUT quote age : {put_age:.2f}s")

        print(
            f"Combined bid premium : {combined_bid:.2f}"
            if combined_bid is not None
            else "Combined bid premium : Unavailable"
        )
        print(
            f"Combined ask premium : {combined_ask:.2f}"
            if combined_ask is not None
            else "Combined ask premium : Unavailable"
        )

        print("These are quote estimates, not executed prices.")
        print("Execution remains paper-only.")
        print("================================================\n")

        self.update_paper_execution(instrument_id, call, put)

    def update_paper_execution(self, updated_instrument_id, call, put):
        if self.paper_simulator is None:
            return

        # Before entry, wait for both legs to have a complete,
        # positive two-sided quote with usable bid liquidity.
        if not self.paper_started:
            valid_call = (
                call["bid"] > 0
                and call["ask"] > 0
                and call["bid_size"] > 0
            )
            valid_put = (
                put["bid"] > 0
                and put["ask"] > 0
                and put["bid_size"] > 0
            )

            if not (valid_call and valid_put):
                print(
                    "[PAPER ENTRY WAIT] Both legs need valid "
                    "bid/ask prices and bid liquidity."
                )
                return

            print("\n[PAPER] Both option quotes are valid.")
            print("[PAPER] Initialising simulated short straddle entry...")

            # Seed both quotes. The second update starts the entry.
            self.paper_simulator.update_quote(
                self.call_option_id,
                call["bid"],
                call["ask"],
                call["bid_size"],
                call["ask_size"],
            )

            self.paper_simulator.update_quote(
                self.put_option_id,
                put["bid"],
                put["ask"],
                put["bid_size"],
                put["ask_size"],
            )

            self.paper_started = self.paper_simulator.entry_started
            return

        # After entry, process only the instrument that just received
        # a fresh quote. The simulator retains the other leg's last quote.
        if updated_instrument_id == self.call_option_id:
            quote_data = call
        else:
            quote_data = put

        self.paper_simulator.update_quote(
            updated_instrument_id,
            quote_data["bid"],
            quote_data["ask"],
            quote_data["bid_size"],
            quote_data["ask_size"],
        )

    def on_stop(self):
        print("\nBTC ATM straddle market-data monitoring stopped.")

        if self.paper_simulator is not None:
            self.paper_simulator.print_summary()


def main():
    data_config = BybitDataClientConfig(
        environment=BybitEnvironment.MAINNET,
        product_types=[
            BybitProductType.OPTION,
            BybitProductType.LINEAR,
        ],
    )

    node = (
        LiveNode.builder(
            "BTC-ATM-STRADDLE",
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

    print("\nStarting Bybit MAINNET BTC ATM straddle strategy...")
    print("Public market data only. No API credentials required.")
    print("No execution client configured.")
    print("Paper execution only. No real orders will be submitted.")
    print("Press Ctrl+C to stop.\n")

    try:
        node.run()
    except KeyboardInterrupt:
        print("\nStopping strategy...")
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
