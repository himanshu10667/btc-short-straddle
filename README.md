# BTC Options Short Straddle

An algorithmic BTC options trading strategy developed using Python,
NautilusTrader, and Bybit market data.

The project implements an ATM (At-The-Money) short straddle by selecting
a Call and Put option with the same strike price and expiry, simulating
the sale of both options, and monitoring the combined premium for
stop-loss and take-profit conditions.

## Objective

Build a BTC ATM Short Straddle using NautilusTrader and Bybit.

The strategy:
1. Retrieves the BTC reference price.
2. Discovers available BTC option contracts.
3. Selects the nearest unexpired expiry.
4. Identifies the strike closest to the BTC reference price.
5. Selects the matching Call and Put contracts.
6. Monitors quotes for both option legs.
7. Simulates selling both options.
8. Monitors the combined premium and manages exits.

## Strategy Logic

### ATM Selection

- Uses the BTCUSDT linear instrument's index price as the reference price.
- Filters out expired option contracts.
- Selects the nearest available expiry.
- Chooses the strike closest to the BTC reference price.
- Selects the matching Call and Put options with the same strike and expiry.

### Entry

- Simulates selling both option legs.
- Uses the available bid prices and bid quantities for simulated sell fills.
- Tracks order acknowledgements, partial fills, and completed fills.
- Checks that both legs have balanced quantities before treating the
  straddle as an established position.

### Risk Management

The strategy monitors the combined premium required to buy back both legs.

- **Stop-Loss: 1%** — triggers when the combined buyback premium rises
  by 1% or more from the entry premium.
- **Take-Profit: 2%** — triggers when the combined buyback premium falls
  by 2% or more from the entry premium.
- Uses ask prices for buyback valuation.
- Simulates buying back both option legs when an exit condition is met.
- Handles partial exits and prevents duplicate exit orders.

## Implementation Status

### Completed

- [x] NautilusTrader environment setup
- [x] Bybit public market data connectivity
- [x] BTC options instrument discovery
- [x] BTC reference index price subscription
- [x] ATM strike and expiry selection
- [x] Matching Call and Put contract selection
- [x] Live quote subscriptions for both option legs
- [x] Combined bid and ask premium calculation
- [x] Paper execution of both entry orders
- [x] 1% stop-loss and 2% take-profit monitoring
- [x] Paper exit order execution
- [x] Partial-fill and unbalanced-entry handling
- [x] Duplicate exit prevention
- [x] Paper execution scenario testing
- [x] Graceful strategy shutdown and cleanup

### Not Yet Implemented

- [ ] Authenticated Bybit account connectivity
- [ ] Actual exchange order placement
- [ ] Live order acknowledgement and position tracking
- [ ] End-to-end execution on Bybit Testnet

## Technology Stack

- **Language:** Python 3.14
- **Trading Framework:** NautilusTrader 2.0.0rc9
- **Exchange:** Bybit
- **Market Data:** Bybit public API and WebSocket streams
- **Environment Management:** uv and Python virtual environments
- **Version Control:** Git and GitHub

## Project Structure

```text
btc-short-straddle/
├── docs/
├── scripts/
│   ├── data_test.py
│   ├── instrument_discovery.py
│   ├── quote_feed_test.py
│   └── run_paper_simulation.py
├── src/
│   ├── __init__.py
│   └── strategies/
│       ├── __init__.py
│       ├── atm_selection.py
│       └── paper_execution.py
├── tests/
├── .env
├── .gitignore
└── README.md
```

## Running the Project

Clone the repository:

```bash
git clone https://github.com/himanshu10667/btc-short-straddle.git
cd btc-short-straddle
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the paper execution scenarios:

```bash
python scripts/run_paper_simulation.py
```

Run the integrated ATM strategy:

```bash
python -m src.strategies.atm_selection
```

The integrated strategy connects to Bybit public market data, discovers
BTC options, selects the ATM Call and Put, and runs the paper execution
logic using incoming market quotes.

## Important Notes

- The current implementation uses Bybit Mainnet **public market data**.
- No authenticated trading connection or real exchange orders are used.
- Order execution and position management are handled by a custom
  paper execution simulator.
- Paper execution results do not represent actual exchange fills.
- The simulator does not account for trading fees, slippage, or
  exchange-specific settlement and P&L calculations.
- The 1% stop-loss and 2% take-profit thresholds are based on the
  combined option premium, not the underlying BTC price.

## Disclaimer

This project is developed for educational and internship-assignment
purposes. It is not intended for production trading or financial advice.
