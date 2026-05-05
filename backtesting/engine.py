from dataclasses import dataclass

from execution.paper_engine import PaperTrader
from risk.risk_manager import RiskConfig, RiskManager


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    starting_capital: float = 100000.0
    risk_per_trade: float = 0.01
    default_stop_points: float = 25.0
    max_quantity: int = 500


@dataclass(frozen=True)
class StrategyRun:
    strategy_name: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    net_profit: float
    ending_equity: float
    max_drawdown: float
    trade_log: list
    equity_curve: list


class BacktestEngine:
    def __init__(self, config):
        self.config = config
        self.risk_manager = RiskManager(
            RiskConfig(
                risk_per_trade=config.risk_per_trade,
                max_quantity=config.max_quantity,
                default_stop_points=config.default_stop_points,
            )
        )

    def run(self, candles, strategy):
        trader = PaperTrader(self.config.starting_capital, verbose=False)
        trade_log = []
        equity_curve = []
        peak_equity = self.config.starting_capital
        max_drawdown = 0.0

        for index in range(len(candles)):
            current_slice = candles.iloc[: index + 1]
            current_candle = current_slice.iloc[-1]
            current_time = current_slice.index[-1]

            stop_fill = self._check_intracandle_stop(trader, current_candle, current_time)
            if stop_fill:
                trade_log.append(stop_fill)

            signal = strategy.generate_signal(current_slice, trader.position)
            if signal.is_trade:
                fill = self._execute_signal(trader, signal, current_candle["close"], current_time)
                if fill:
                    trade_log.append(fill)

            equity = trader.mark_to_market(current_candle["close"])
            equity_curve.append((current_time, equity))
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)

        if trader.position is not None:
            final_candle = candles.iloc[-1]
            fill = trader.exit(float(final_candle["close"]), "backtest end")
            if fill:
                fill.time = candles.index[-1].to_pydatetime()
                trade_log.append(fill)
            final_equity = trader.mark_to_market(float(final_candle["close"]))
            equity_curve.append((candles.index[-1], final_equity))
            peak_equity = max(peak_equity, final_equity)
            max_drawdown = max(max_drawdown, peak_equity - final_equity)

        closed_trades = [fill for fill in trade_log if fill.action == "EXIT"]
        wins = sum(1 for fill in closed_trades if fill.pnl > 0)
        losses = sum(1 for fill in closed_trades if fill.pnl <= 0)
        total_trades = len(closed_trades)
        win_rate = (wins / total_trades * 100.0) if total_trades else 0.0

        return StrategyRun(
            strategy_name=strategy.name,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            net_profit=trader.realized_pnl,
            ending_equity=trader.cash,
            max_drawdown=max_drawdown,
            trade_log=trade_log,
            equity_curve=equity_curve,
        )

    def _check_intracandle_stop(self, trader, candle, current_time):
        if trader.position is None or trader.position.stop_loss is None:
            return None
        if float(candle["low"]) > trader.position.stop_loss:
            return None
        fill = trader.exit(trader.position.stop_loss, "stop loss hit")
        if fill:
            fill.time = current_time.to_pydatetime()
        return fill

    def _execute_signal(self, trader, signal, price, current_time):
        if signal.action == "BUY":
            quantity = self.risk_manager.size_for_signal(trader.cash, price, signal)
            fill = trader.buy(
                self.config.symbol,
                float(price),
                quantity,
                stop_loss=signal.stop_loss,
                reason=signal.reason,
            )
        else:
            fill = trader.exit(float(price), signal.reason)

        if fill:
            fill.time = current_time.to_pydatetime()
        return fill
