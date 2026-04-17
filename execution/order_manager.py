class PaperOrderManager:
    def __init__(self, trader, risk_manager, symbol):
        self.trader = trader
        self.risk_manager = risk_manager
        self.symbol = symbol

    def handle_signal(self, signal, price):
        if not signal.is_trade:
            return None

        if signal.action == "BUY":
            quantity = self.risk_manager.size_for_signal(self.trader.cash, price, signal)
            return self.trader.execute(signal, price, quantity=quantity, symbol=self.symbol)

        return self.trader.execute(signal, price, symbol=self.symbol)
