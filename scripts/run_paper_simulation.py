import sys
from pathlib import Path
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategies.paper_execution import PaperStraddleSimulator


D = Decimal

CALL = "BTC-15NOV26-67000-C-USDT-OPTION.BYBIT"
PUT = "BTC-15NOV26-67000-P-USDT-OPTION.BYBIT"


def run_stop_loss_scenario():
    print("\n\n############################################")
    print("SCENARIO 1: STOP-LOSS")
    print("############################################")

    sim = PaperStraddleSimulator(CALL, PUT, quantity="0.01")

    sim.update_quote(CALL, 450, 455, 0.10, 0.10)
    sim.update_quote(PUT, 505, 510, 0.10, 0.10)
    sim.update_quote(CALL, 455, 460, 0.10, 0.10)

    assert sim.closed
    assert sim.exit_reason == "STOP_LOSS"
    assert sim.positions["CALL"].quantity == D("0")
    assert sim.positions["PUT"].quantity == D("0")

    sim.print_summary()
    print("[TEST PASSED] Stop-loss scenario")


def run_take_profit_scenario():
    print("\n\n############################################")
    print("SCENARIO 2: TAKE-PROFIT")
    print("############################################")

    sim = PaperStraddleSimulator(CALL, PUT, quantity="0.01")

    sim.update_quote(CALL, 450, 455, 0.10, 0.10)
    sim.update_quote(PUT, 505, 510, 0.10, 0.10)
    sim.update_quote(CALL, 435, 440, 0.10, 0.10)
    sim.update_quote(PUT, 485, 490, 0.10, 0.10)

    assert sim.closed
    assert sim.exit_reason == "TAKE_PROFIT"
    assert sim.positions["CALL"].quantity == D("0")
    assert sim.positions["PUT"].quantity == D("0")

    sim.print_summary()
    print("[TEST PASSED] Take-profit scenario")


def run_partial_entry_scenario():
    print("\n\n############################################")
    print("SCENARIO 3: PARTIAL / UNBALANCED ENTRY")
    print("############################################")

    sim = PaperStraddleSimulator(CALL, PUT, quantity="0.01")

    sim.update_quote(CALL, 450, 455, 0.10, 0.10)
    sim.update_quote(PUT, 505, 510, 0.004, 0.10)

    assert sim.exit_reason == "UNBALANCED_ENTRY"
    assert sim.closed
    assert sim.positions["CALL"].quantity == D("0")
    assert sim.positions["PUT"].quantity == D("0")

    sim.print_summary()
    print("[TEST PASSED] Partial entry scenario")


def run_partial_exit_and_duplicate_prevention_scenario():
    print("\n\n############################################")
    print("SCENARIO 4: PARTIAL EXIT + DUPLICATE PREVENTION")
    print("############################################")

    sim = PaperStraddleSimulator(CALL, PUT, quantity="0.01")

    # Open a balanced short straddle.
    sim.update_quote(CALL, 450, 455, 0.10, 0.10)
    sim.update_quote(PUT, 505, 510, 0.10, 0.10)

    # Trigger stop-loss. Call has only 0.004 ask liquidity.
    sim.update_quote(CALL, 455, 460, 0.10, 0.004)

    assert sim.exit_started
    assert not sim.closed
    assert sim.positions["CALL"].quantity == D("0.006")
    assert sim.positions["PUT"].quantity == D("0")

    call_exit_orders = [
        order for order in sim.orders
        if order.leg == "CALL" and order.side == "BUY"
    ]

    assert len(call_exit_orders) == 1

    call_exit_order = call_exit_orders[0]
    assert call_exit_order.filled_qty == D("0.004")
    assert call_exit_order.remaining_qty == D("0.006")

    print("\n--- First partial exit recorded ---")
    print(f"Call position remaining: {sim.positions['CALL'].quantity}")
    print(f"Existing exit order: {call_exit_order.order_id}")

    # A fresh quote provides 0.003 additional ask liquidity.
    sim.update_quote(CALL, 450, 455, 0.10, 0.003)

    assert sim.positions["CALL"].quantity == D("0.003")
    assert call_exit_order.filled_qty == D("0.007")
    assert call_exit_order.remaining_qty == D("0.003")

    # Another fresh quote supplies the final 0.003.
    sim.update_quote(CALL, 448, 453, 0.10, 0.003)

    assert sim.closed
    assert sim.positions["CALL"].quantity == D("0")
    assert sim.positions["PUT"].quantity == D("0")
    assert call_exit_order.status.value == "FILLED"

    # Quotes after closure must not create more orders.
    order_count_after_close = len(sim.orders)
    sim.update_quote(CALL, 447, 452, 0.10, 0.10)

    assert len(sim.orders) == order_count_after_close

    call_exit_orders = [
        order for order in sim.orders
        if order.leg == "CALL" and order.side == "BUY"
    ]

    assert len(call_exit_orders) == 1

    sim.print_summary()
    print("[TEST PASSED] Partial exit and duplicate prevention")


if __name__ == "__main__":
    run_stop_loss_scenario()
    run_take_profit_scenario()
    run_partial_entry_scenario()
    run_partial_exit_and_duplicate_prevention_scenario()

    print("\n\n============================================")
    print("ALL PAPER SIMULATION TESTS PASSED")
    print("============================================")
