# StockEye

StockEye analyzes US and Singapore (SGX) listed stocks two ways:

- **Macro (2-year horizon)**: scores news sentiment with FinBERT and measures how the stock moved relative to its market around each news event (an event study).
- **Technical (1-week horizon)**: detects candlestick patterns, measures how reliable each pattern has been for that specific stock, and summarizes the standard indicators (VWAP, RSI, SMA/EMA, MACD, Bollinger Bands).

> StockEye is an informational analysis tool. Nothing it shows is investment advice.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI service, analysis engines, data providers, MongoDB repositories |
| `frontend/` | React + MUI single-page app |
| `docs/` | Architecture notes and the technology report |

Setup instructions for each part live in its own README.
