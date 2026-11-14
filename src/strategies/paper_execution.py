from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


D = Decimal


class OrderStatus(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class PaperOrder:
    order_id: str
    leg: str
    side: str
    requested_qty: Decimal
    filled_qty: Decimal = D("0")
    average_price: Decimal = D("0")
    status: OrderStatus = OrderStatus.ACKNOWLEDGED

    @property
    def remaining_qty(self):
        return max(D("0"), self.requested_qty - self.filled_qty)


@dataclass
class LegPosition:
    leg: str
    instrument_id: str
    quantity: Decimal = D("0")
    entry_price: Decimal = D("0")


class PaperStraddleSimulator:
    """
    Simplified paper execution model.

    - SELL entries execute against bid prices and bid sizes.
    - BUY exits execute against ask prices and ask sizes.
    - Exit orders persist while partially filled.
    - A leg can have only one active exit order at a time.
    - Realized P&L is tracked as (entry - exit) * closed quantity.

    This is not an exchange matching engine. It does not model queue
    position, latency, fees, slippage, or exchange-specific execution.
    """

    def __init__(
        self,
        call_id,
        put_id,
        quantity=D("0.01"),
        stop_loss_pct=D("0.01"),
        take_profit_pct=D("0.02"),
    ):
        self.call_id = str(call_id)
        self.put_id = str(put_id)
        self.quantity = D(str(quantity))
        self.stop_loss_pct = D(str(stop_loss_pct))
        self.take_profit_pct = D(str(take_profit_pct))

        if self.quantity <= 0:
            raise ValueError("Quantity must be positive.")

        if self.stop_loss_pct < 0 or self.take_profit_pct < 0:
            raise ValueError("Risk percentages cannot be negative.")

        self.quotes = {}
        self.orders = []
        self.exit_orders = {}

        self.positions = {
            "CALL": LegPosition("CALL", self.call_id),
            "PUT": LegPosition("PUT", self.put_id),
        }

        self.entry_started = False
        self.entry_premium = None
        self.exit_started = False
        self.exit_reason = None
        self.closed = False
        self.realized_pnl = D("0")
        self.next_order_number = 1

    def log(self, message):
        print(message)

    def new_order(self, leg, side, quantity):
        order = PaperOrder(
            order_id=f"PAPER-{self.next_order_number:03d}",
            leg=leg,
            side=side,
            requested_qty=quantity,
        )
        self.next_order_number += 1
        self.orders.append(order)

        self.log(
            f"[ORDER ACK] {order.order_id} | {leg} | {side} "
            f"| requested={quantity}"
        )
        return order

    def update_quote(self, instrument_id, bid, ask, bid_size, ask_size):
        instrument_id = str(instrument_id)

        self.quotes[instrument_id] = {
            "bid": D(str(bid)),
            "ask": D(str(ask)),
            "bid_size": D(str(bid_size)),
            "ask_size": D(str(ask_size)),
        }

        self.log(
            f"[QUOTE] {instrument_id} | "
            f"bid={bid} x {bid_size} | ask={ask} x {ask_size}"
        )

        if self.exit_started and not self.closed:
            # Only the instrument that received a fresh quote is eligible
            # for another simulated fill. Do not reuse stale liquidity.
            self.process_exit_for(instrument_id)
            self.check_closed()
            return

        if not self.entry_started:
            self.try_open_straddle()
        elif self.entry_started and not self.exit_started:
            self.check_risk()

    def try_open_straddle(self):
        if self.call_id not in self.quotes or self.put_id not in self.quotes:
            return

        self.entry_started = True

        self.log("\n========== PAPER STRADDLE ENTRY ==========")

        call_order = self.new_order("CALL", "SELL", self.quantity)
        put_order = self.new_order("PUT", "SELL", self.quantity)

        self.fill_entry_order(call_order, self.quotes[self.call_id])
        self.fill_entry_order(put_order, self.quotes[self.put_id])

        call_position = self.positions["CALL"]
        put_position = self.positions["PUT"]

        self.log("\nEntry position summary:")
        self.print_position(call_position)
        self.print_position(put_position)

        if call_position.quantity != put_position.quantity:
            self.log(
                "\n[WARNING] UNBALANCED STRADDLE: "
                "Call and Put filled quantities differ."
            )
            self.log(
                "The simulator will close the filled exposure "
                "to avoid leaving an unmatched leg."
            )
            self.start_exit("UNBALANCED_ENTRY")
            return

        if call_position.quantity == 0:
            self.log("[ENTRY FAILED] Neither leg received a fill.")
            return

        self.entry_premium = (
            call_position.entry_price + put_position.entry_price
        )

        self.log(
            f"\n[ENTRY COMPLETE] Balanced quantity per leg: "
            f"{call_position.quantity}"
        )
        self.log(f"Combined entry premium: {self.entry_premium}")
        self.log("==========================================\n")

    def fill_entry_order(self, order, quote):
        available = quote["bid_size"]
        fill_qty = min(order.remaining_qty, available)

        if fill_qty <= 0 or quote["bid"] <= 0:
            order.status = OrderStatus.REJECTED
            self.log(
                f"[ORDER REJECTED] {order.order_id}: "
                "no executable bid size."
            )
            return

        order.filled_qty += fill_qty
        order.average_price = quote["bid"]

        if order.remaining_qty == 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        position = self.positions[order.leg]
        position.quantity += fill_qty
        position.entry_price = order.average_price

        self.log(
            f"[{order.status.value}] {order.order_id} | "
            f"filled={fill_qty} @ {order.average_price} | "
            f"remaining={order.remaining_qty}"
        )

    def check_risk(self):
        if self.entry_premium is None or self.exit_started or self.closed:
            return

        call = self.positions["CALL"]
        put = self.positions["PUT"]

        if call.quantity <= 0 or call.quantity != put.quantity:
            return

        call_quote = self.quotes.get(self.call_id)
        put_quote = self.quotes.get(self.put_id)

        if not call_quote or not put_quote:
            return

        if call_quote["ask"] <= 0 or put_quote["ask"] <= 0:
            return

        buyback_premium = call_quote["ask"] + put_quote["ask"]

        stop_price = self.entry_premium * (
            D("1") + self.stop_loss_pct
        )
        target_price = self.entry_premium * (
            D("1") - self.take_profit_pct
        )

        self.log(
            f"[RISK CHECK] entry={self.entry_premium} | "
            f"buyback={buyback_premium} | "
            f"SL={stop_price:.4f} | TP={target_price:.4f}"
        )

        if buyback_premium >= stop_price:
            self.start_exit("STOP_LOSS")
        elif buyback_premium <= target_price:
            self.start_exit("TAKE_PROFIT")

    def start_exit(self, reason):
        if self.exit_started or self.closed:
            self.log(f"[EXIT IGNORED] Exit already started or position closed.")
            return

        self.exit_started = True
        self.exit_reason = reason

        self.log(f"\n[EXIT TRIGGERED] {reason}")

        # Create at most one exit order per open leg.
        for leg in ("CALL", "PUT"):
            position = self.positions[leg]

            if position.quantity <= 0:
                continue

            if leg not in self.exit_orders:
                self.exit_orders[leg] = self.new_order(
                    leg, "BUY", position.quantity
                )

        # Process the latest cached quote for each leg once.
        self.process_exit_for(self.call_id)
        self.process_exit_for(self.put_id)
        self.check_closed()

    def process_exit_for(self, instrument_id):
        leg = None

        if instrument_id == self.call_id:
            leg = "CALL"
        elif instrument_id == self.put_id:
            leg = "PUT"

        if leg is None:
            return

        position = self.positions[leg]
        order = self.exit_orders.get(leg)

        if position.quantity <= 0 or order is None:
            return

        if order.status == OrderStatus.FILLED:
            return

        quote = self.quotes.get(instrument_id)

        if not quote or quote["ask"] <= 0:
            self.log(f"[EXIT WAIT] {leg}: no valid ask quote.")
            return

        available = quote["ask_size"]
        fill_qty = min(order.remaining_qty, position.quantity, available)

        if fill_qty <= 0:
            self.log(
                f"[EXIT WAIT] {leg}: no ask-side liquidity. "
                f"Remaining={position.quantity}"
            )
            return

        fill_price = quote["ask"]

        # Update cumulative order fill and its average execution price.
        previous_filled = order.filled_qty
        new_filled = previous_filled + fill_qty

        order.average_price = (
            (order.average_price * previous_filled)
            + (fill_price * fill_qty)
        ) / new_filled

        order.filled_qty = new_filled
        position.quantity -= fill_qty

        self.realized_pnl += (
            position.entry_price - fill_price
        ) * fill_qty

        if order.remaining_qty == 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        self.log(
            f"[{order.status.value}] {order.order_id} | "
            f"closed={fill_qty} @ {fill_price} | "
            f"order_remaining={order.remaining_qty} | "
            f"position_remaining={position.quantity}"
        )

    def check_closed(self):
        if self.closed:
            return

        if all(
            position.quantity == 0
            for position in self.positions.values()
        ):
            self.closed = True
            self.log(
                f"\n[PAPER POSITION CLOSED] Reason: {self.exit_reason}"
            )
            self.log("Both option positions are flat.")
            self.log(f"Realized P&L (premium units): {self.realized_pnl}")
        else:
            remaining = {
                leg: position.quantity
                for leg, position in self.positions.items()
                if position.quantity > 0
            }
            self.log(f"[EXIT INCOMPLETE] Remaining positions: {remaining}")

    def print_position(self, position):
        self.log(
            f"{position.leg}: quantity={position.quantity} | "
            f"average entry={position.entry_price}"
        )

    def print_summary(self):
        print("\n========== PAPER EXECUTION SUMMARY ==========")

        for leg, position in self.positions.items():
            self.print_position(position)

        print(f"Exit reason : {self.exit_reason}")
        print(f"Closed      : {self.closed}")
        print(f"Realized P&L: {self.realized_pnl}")
        print(f"Total orders: {len(self.orders)}")

        print("\nOrder states:")
        for order in self.orders:
            print(
                f"{order.order_id} | {order.leg} | {order.side} | "
                f"{order.status.value} | "
                f"filled={order.filled_qty} | "
                f"remaining={order.remaining_qty}"
            )

        print("=============================================\n")
