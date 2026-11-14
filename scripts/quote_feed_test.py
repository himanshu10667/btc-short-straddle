from nautilus_trader.adapters.bybit import (
    BybitDataClientConfig,
    BybitDataClientFactory,
    BybitEnvironment,
    BybitProductType,
)
from nautilus_trader.common import Environment
from nautilus_trader.live import LiveNode
from nautilus_trader.model import InstrumentId, TraderId
from nautilus_trader.trading import Strategy


class StraddleQuoteTest(Strategy):

    def on_start(self):
        self.call_id = InstrumentId.from_str(
            "BTC-15NOV26-67250-C-USDT-OPTION.BYBIT"
        )
        self.put_id = InstrumentId.from_str(
            "BTC-15NOV26-67250-P-USDT-OPTION.BYBIT"
        )

        self.quotes = {
            "CALL": None,
            "PUT": None,
        }

        for name, instrument_id in [
            ("CALL", self.call_id),
            ("PUT", self.put_id),
        ]:
            instrument = self.cache.instrument(instrument_id)

            print(f"{name} instrument found: {instrument is not None}")

            if instrument is not None:
                self.subscribe_quotes(instrument_id)

    def on_quote(self, quote):
        if quote.instrument_id == self.call_id:
            name = "CALL"
        elif quote.instrument_id == self.put_id:
            name = "PUT"
        else:
            return

        bid = float(quote.bid_price)
        ask = float(quote.ask_price)

        self.quotes[name] = {
            "bid": bid,
            "ask": ask,
        }

        print(
            f"{name} | Bid: {bid} | Ask: {ask} "
            f"| Bid size: {quote.bid_size} "
            f"| Ask size: {quote.ask_size}"
        )

        call = self.quotes["CALL"]
        put = self.quotes["PUT"]

        if call is not None and put is not None:
            if call["bid"] > 0 and put["bid"] > 0:
                combined_bid = call["bid"] + put["bid"]
                print(f"Combined bid premium: {combined_bid}")

            if call["ask"] > 0 and put["ask"] > 0:
                combined_ask = call["ask"] + put["ask"]
                print(f"Combined ask premium: {combined_ask}")

            print("-" * 50)


def main():
    data_config = BybitDataClientConfig(
        environment=BybitEnvironment.MAINNET,
        product_types=[BybitProductType.OPTION],
    )

    node = (
        LiveNode.builder(
            "BTC-STRADDLE-QUOTE-TEST",
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

    node.add_strategy(StraddleQuoteTest())
    node.run()


if __name__ == "__main__":
    main()
