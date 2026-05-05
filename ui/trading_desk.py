import queue
import tkinter as tk
from tkinter import messagebox, ttk

from execution.paper_engine import PaperTrader
from risk.risk_manager import RiskConfig, RiskManager
from ui.live_dashboard import LiveMarketSession
from config.settings import get_settings


class TradingDeskApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Algo Trader Trading Desk")
        self.root.geometry("1360x860")
        self.root.minsize(1180, 760)

        self.settings = get_settings()
        self.event_queue = queue.Queue()
        self.session = LiveMarketSession(self.settings, self.event_queue)
        self.trader = PaperTrader(self.settings.starting_capital, verbose=False)
        self.risk_manager = RiskManager(
            RiskConfig(
                risk_per_trade=self.settings.risk_per_trade,
                max_quantity=self.settings.max_quantity,
                default_stop_points=self.settings.default_stop_points,
            )
        )
        self.last_snapshot = self.session.snapshot()
        self.last_fill_count = 0

        self.instrument_name_var = tk.StringVar(value=self.settings.instrument_name)
        self.instrument_key_var = tk.StringVar(value=self.settings.instrument_key)
        self.connection_var = tk.StringVar(value="DISCONNECTED")
        self.feed_var = tk.StringVar(value="Not connected")
        self.price_var = tk.StringVar(value="n/a")
        self.tick_var = tk.StringVar(value="0")
        self.last_tick_var = tk.StringVar(value="Never")
        self.feed_keys_var = tk.StringVar(value="n/a")
        self.error_var = tk.StringVar(value="None")

        self.cash_var = tk.StringVar()
        self.equity_var = tk.StringVar()
        self.realized_var = tk.StringVar()
        self.unrealized_var = tk.StringVar()
        self.position_var = tk.StringVar()
        self.account_status_var = tk.StringVar(value="Paper account ready.")
        self.add_funds_var = tk.StringVar(value="10000")

        self.plan_entry_var = tk.StringVar()
        self.plan_target_var = tk.StringVar()
        self.plan_stop_var = tk.StringVar()
        self.plan_qty_var = tk.StringVar()
        self.plan_expected_profit_var = tk.StringVar(value="0.00")
        self.plan_expected_loss_var = tk.StringVar(value="0.00")
        self.plan_rr_var = tk.StringVar(value="n/a")
        self.plan_status_var = tk.StringVar(value="Plan a trade using live price or your own levels.")

        self._build_layout()
        self._bind_plan_inputs()
        self.refresh_account()
        self.root.after(300, self.poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        live_tab = ttk.Frame(notebook, padding=16)
        money_tab = ttk.Frame(notebook, padding=16)
        planner_tab = ttk.Frame(notebook, padding=16)

        notebook.add(live_tab, text="Live Feed")
        notebook.add(money_tab, text="Paper Money")
        notebook.add(planner_tab, text="Trade Planner")

        self.build_live_tab(live_tab)
        self.build_money_tab(money_tab)
        self.build_planner_tab(planner_tab)

    def build_live_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(left, text="Live Feed Controls", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(left, text="Instrument Name").grid(row=1, column=0, sticky="w", pady=(16, 4))
        ttk.Entry(left, textvariable=self.instrument_name_var, width=34).grid(row=2, column=0, sticky="ew")
        ttk.Label(left, text="Instrument Key").grid(row=3, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(left, textvariable=self.instrument_key_var, width=34).grid(row=4, column=0, sticky="ew")
        ttk.Button(left, text="Connect Live Feed", command=self.connect_live_feed).grid(
            row=5, column=0, sticky="ew", pady=(16, 0)
        )
        ttk.Button(left, text="Disconnect Feed", command=self.disconnect_live_feed).grid(
            row=6, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(left, text="Use Current Price In Planner", command=self.use_live_price_in_planner).grid(
            row=7, column=0, sticky="ew", pady=(8, 0)
        )

        status = ttk.LabelFrame(right, text="Connection Status", padding=12)
        status.grid(row=0, column=0, sticky="ew")
        status.columnconfigure(1, weight=1)
        live_rows = [
            ("Connection", self.connection_var),
            ("Feed", self.feed_var),
            ("Current Price", self.price_var),
            ("Ticks Received", self.tick_var),
            ("Last Tick", self.last_tick_var),
            ("Feed Keys", self.feed_keys_var),
            ("Last Error", self.error_var),
        ]
        for row, (label, variable) in enumerate(live_rows):
            ttk.Label(status, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            ttk.Label(status, textvariable=variable, wraplength=760, justify="left").grid(
                row=row, column=1, sticky="w", pady=4
            )

        candles = ttk.LabelFrame(right, text="Live Candles", padding=10)
        candles.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        candles.columnconfigure(0, weight=1)
        candles.rowconfigure(0, weight=1)
        self.candle_tree = ttk.Treeview(
            candles,
            columns=("time", "open", "high", "low", "close"),
            show="headings",
            height=18,
        )
        for key, heading, width in (
            ("time", "Time", 180),
            ("open", "Open", 110),
            ("high", "High", 110),
            ("low", "Low", 110),
            ("close", "Close", 110),
        ):
            self.candle_tree.heading(key, text=heading)
            self.candle_tree.column(key, width=width, anchor="center")
        self.candle_tree.grid(row=0, column=0, sticky="nsew")

    def build_money_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.LabelFrame(parent, text="Paper Account", padding=12)
        header.grid(row=0, column=0, sticky="ew")
        for col in range(3):
            header.columnconfigure(col, weight=1)

        summary_rows = [
            ("Cash", self.cash_var),
            ("Equity", self.equity_var),
            ("Realized PnL", self.realized_var),
            ("Unrealized PnL", self.unrealized_var),
            ("Position", self.position_var),
            ("Status", self.account_status_var),
        ]
        for index, (label, variable) in enumerate(summary_rows):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(header, text=label).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=6)
            ttk.Label(header, textvariable=variable, wraplength=420, justify="left").grid(
                row=row, column=col + 1, sticky="w", pady=6
            )

        controls = ttk.Frame(parent)
        controls.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        controls.columnconfigure(0, weight=0)
        controls.columnconfigure(1, weight=1)
        controls.rowconfigure(1, weight=1)

        funds = ttk.LabelFrame(controls, text="Cash Management", padding=12)
        funds.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        ttk.Label(funds, text="Add Paper Funds").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(funds, textvariable=self.add_funds_var, width=18).grid(row=1, column=0, sticky="ew")
        ttk.Button(funds, text="Add Funds", command=self.add_funds).grid(
            row=2, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(funds, text="Refresh Account", command=self.refresh_account).grid(
            row=3, column=0, sticky="ew", pady=(8, 0)
        )

        history = ttk.LabelFrame(controls, text="Trade History", padding=10)
        history.grid(row=0, column=1, rowspan=2, sticky="nsew")
        history.columnconfigure(0, weight=1)
        history.rowconfigure(0, weight=1)
        self.history_tree = ttk.Treeview(
            history,
            columns=("time", "action", "symbol", "qty", "price", "pnl", "reason"),
            show="headings",
        )
        for key, heading, width in (
            ("time", "Time", 140),
            ("action", "Action", 70),
            ("symbol", "Symbol", 150),
            ("qty", "Qty", 60),
            ("price", "Price", 85),
            ("pnl", "PnL", 85),
            ("reason", "Reason", 180),
        ):
            self.history_tree.heading(key, text=heading)
            self.history_tree.column(key, width=width, anchor="center")
        self.history_tree.grid(row=0, column=0, sticky="nsew")

    def build_planner_tab(self, parent):
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(parent, text="Trade Inputs", padding=12)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        right = ttk.LabelFrame(parent, text="Trade Preview", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        input_rows = [
            ("Entry Price", self.plan_entry_var),
            ("Target Price", self.plan_target_var),
            ("Stop Loss", self.plan_stop_var),
            ("Quantity", self.plan_qty_var),
        ]
        for row, (label, variable) in enumerate(input_rows):
            ttk.Label(left, text=label).grid(row=row * 2, column=0, sticky="w", pady=(0 if row == 0 else 12, 4))
            ttk.Entry(left, textvariable=variable, width=20).grid(row=row * 2 + 1, column=0, sticky="ew")

        ttk.Button(left, text="Use Live Price", command=self.use_live_price_in_planner).grid(
            row=8, column=0, sticky="ew", pady=(16, 0)
        )
        ttk.Button(left, text="Auto Size Quantity", command=self.auto_size_quantity).grid(
            row=9, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(left, text="Enter Paper Trade", command=self.enter_paper_trade).grid(
            row=10, column=0, sticky="ew", pady=(16, 0)
        )
        ttk.Button(left, text="Exit Current Position", command=self.exit_current_position).grid(
            row=11, column=0, sticky="ew", pady=(8, 0)
        )

        preview_rows = [
            ("Selected Instrument", self.instrument_name_var),
            ("Current Live Price", self.price_var),
            ("Expected Profit", self.plan_expected_profit_var),
            ("Expected Loss", self.plan_expected_loss_var),
            ("Reward / Risk", self.plan_rr_var),
            ("Planner Status", self.plan_status_var),
        ]
        for row, (label, variable) in enumerate(preview_rows):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 16), pady=8)
            ttk.Label(right, textvariable=variable, wraplength=620, justify="left").grid(
                row=row, column=1, sticky="w", pady=8
            )

    def _bind_plan_inputs(self):
        for variable in (self.plan_entry_var, self.plan_target_var, self.plan_stop_var, self.plan_qty_var):
            variable.trace_add("write", self.update_trade_preview)

    def connect_live_feed(self):
        self.session.start(self.instrument_name_var.get(), self.instrument_key_var.get())
        self.connection_var.set("CONNECTING")
        self.feed_var.set("Starting login flow...")

    def disconnect_live_feed(self):
        self.session.stop()
        self.refresh_account()

    def use_live_price_in_planner(self):
        if self.last_snapshot["last_price"] is None:
            self.plan_status_var.set("No live price available yet.")
            return
        current_price = f"{self.last_snapshot['last_price']:.2f}"
        self.plan_entry_var.set(current_price)
        if not self.plan_target_var.get().strip():
            self.plan_target_var.set(f"{self.last_snapshot['last_price'] + 50:.2f}")
        if not self.plan_stop_var.get().strip():
            self.plan_stop_var.set(f"{self.last_snapshot['last_price'] - self.settings.default_stop_points:.2f}")
        self.plan_status_var.set("Planner updated with current live price.")

    def auto_size_quantity(self):
        try:
            entry = float(self.plan_entry_var.get())
            stop = float(self.plan_stop_var.get())
        except ValueError:
            self.plan_status_var.set("Entry price and stop loss are required before auto sizing.")
            return
        quantity = self.risk_manager.position_size(self.trader.cash, entry, stop)
        self.plan_qty_var.set(str(quantity))
        self.plan_status_var.set("Quantity sized from your paper risk settings.")

    def enter_paper_trade(self):
        if self.trader.position is not None:
            self.plan_status_var.set("You already have an open paper position.")
            return

        try:
            entry = float(self.plan_entry_var.get())
            stop = float(self.plan_stop_var.get())
            quantity = int(self.plan_qty_var.get() or "0")
        except ValueError:
            self.plan_status_var.set("Entry, stop, and quantity must be valid numbers.")
            return

        if quantity <= 0:
            self.plan_status_var.set("Quantity must be greater than zero.")
            return

        fill = self.trader.buy(
            self.instrument_name_var.get().strip() or self.settings.instrument_name,
            entry,
            quantity,
            stop_loss=stop,
            reason="manual planner entry",
        )
        if fill is None:
            self.plan_status_var.set("Paper trade entry was rejected.")
            return

        self.plan_status_var.set("Paper trade entered.")
        self.account_status_var.set(
            f"Entered {quantity} units at {entry:.2f} with stop loss {stop:.2f}."
        )
        self.refresh_account()

    def exit_current_position(self):
        if self.trader.position is None:
            self.plan_status_var.set("No open paper position to exit.")
            return

        exit_price = self.last_snapshot["last_price"]
        if exit_price is None:
            try:
                exit_price = float(self.plan_entry_var.get())
            except ValueError:
                self.plan_status_var.set("No live price available. Enter a price in planner first.")
                return

        fill = self.trader.exit(exit_price, "manual planner exit")
        if fill is None:
            self.plan_status_var.set("Exit failed.")
            return

        self.plan_status_var.set("Paper position exited.")
        self.account_status_var.set(f"Exited paper trade at {exit_price:.2f}.")
        self.refresh_account()

    def add_funds(self):
        try:
            amount = float(self.add_funds_var.get())
            self.trader.add_funds(amount)
        except ValueError as exc:
            messagebox.showerror("Invalid amount", str(exc))
            return
        self.account_status_var.set(f"Added {amount:.2f} to paper funds.")
        self.refresh_account()

    def refresh_account(self):
        last_price = self.last_snapshot["last_price"]
        equity = self.trader.mark_to_market(last_price)
        unrealized = 0.0
        if self.trader.position is not None and last_price is not None:
            unrealized = (float(last_price) - self.trader.position.entry_price) * self.trader.position.quantity

        if self.trader.position is None:
            position_text = "FLAT"
        else:
            position_text = (
                f"LONG {self.trader.position.quantity} @ {self.trader.position.entry_price:.2f} "
                f"(SL {self.trader.position.stop_loss:.2f})"
            )

        self.cash_var.set(f"{self.trader.cash:.2f}")
        self.equity_var.set(f"{equity:.2f}")
        self.realized_var.set(f"{self.trader.realized_pnl:.2f}")
        self.unrealized_var.set(f"{unrealized:.2f}")
        self.position_var.set(position_text)

        if len(self.trader.fills) != self.last_fill_count:
            self.last_fill_count = len(self.trader.fills)
            self.history_tree.delete(*self.history_tree.get_children())
            for fill in self.trader.fills:
                self.history_tree.insert(
                    "",
                    "end",
                    values=(
                        fill.time.strftime("%Y-%m-%d %H:%M:%S"),
                        fill.action,
                        fill.symbol,
                        fill.quantity,
                        f"{fill.price:.2f}",
                        f"{fill.pnl:.2f}",
                        fill.reason,
                    ),
                )

    def update_trade_preview(self, *_args):
        try:
            entry = float(self.plan_entry_var.get())
            target = float(self.plan_target_var.get())
            stop = float(self.plan_stop_var.get())
            quantity = int(self.plan_qty_var.get() or "0")
        except ValueError:
            self.plan_expected_profit_var.set("0.00")
            self.plan_expected_loss_var.set("0.00")
            self.plan_rr_var.set("n/a")
            return

        expected_profit = max(0.0, (target - entry) * quantity)
        expected_loss = max(0.0, (entry - stop) * quantity)
        reward_risk = "n/a" if expected_loss <= 0 else f"{expected_profit / expected_loss:.2f}"
        self.plan_expected_profit_var.set(f"{expected_profit:.2f}")
        self.plan_expected_loss_var.set(f"{expected_loss:.2f}")
        self.plan_rr_var.set(reward_risk)

    def poll_queue(self):
        try:
            while True:
                _event, snapshot = self.event_queue.get_nowait()
                self.apply_snapshot(snapshot)
        except queue.Empty:
            pass
        self.root.after(300, self.poll_queue)

    def apply_snapshot(self, snapshot):
        self.last_snapshot = snapshot
        self.connection_var.set(snapshot["connection_status"])
        self.feed_var.set(snapshot["feed_status"])
        self.price_var.set("n/a" if snapshot["last_price"] is None else f"{snapshot['last_price']:.2f}")
        self.tick_var.set(str(snapshot["tick_count"]))
        self.last_tick_var.set(
            "Never"
            if snapshot["last_tick_time"] is None
            else snapshot["last_tick_time"].strftime("%Y-%m-%d %H:%M:%S")
        )
        self.feed_keys_var.set(
            "n/a" if not snapshot["last_feed_keys"] else ", ".join(snapshot["last_feed_keys"])
        )
        self.error_var.set(snapshot["last_error"] or "None")

        self.candle_tree.delete(*self.candle_tree.get_children())
        for candle_time, row in snapshot["candles"]:
            self.candle_tree.insert(
                "",
                "end",
                values=(
                    candle_time.strftime("%Y-%m-%d %H:%M"),
                    f"{row['open']:.2f}",
                    f"{row['high']:.2f}",
                    f"{row['low']:.2f}",
                    f"{row['close']:.2f}",
                ),
            )

        if self.trader.position is not None and snapshot["last_price"] is not None:
            stop_fill = self.trader.check_stop(snapshot["last_price"])
            if stop_fill is not None:
                self.account_status_var.set(
                    f"Stop loss hit at {snapshot['last_price']:.2f}. Position closed automatically."
                )

        self.refresh_account()

    def on_close(self):
        try:
            self.session.stop()
        finally:
            self.root.destroy()
