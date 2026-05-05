import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from backtesting.data_loader import generate_demo_data, load_price_data
from backtesting.engine import BacktestConfig, BacktestEngine
from backtesting.strategies import build_strategy_catalog, rank_runs
from config.settings import get_settings


class BacktestWorkbench:
    def __init__(self, root):
        self.root = root
        self.root.title("Algo Trader AI Backtesting Workbench")
        self.root.geometry("1260x820")
        self.root.minsize(1100, 720)

        settings = get_settings()
        self.settings = settings
        self.data = None
        self.last_runs = []

        self.csv_path_var = tk.StringVar()
        self.symbol_var = tk.StringVar(value=settings.instrument_name)
        self.capital_var = tk.StringVar(value=f"{settings.starting_capital:.0f}")
        self.risk_var = tk.StringVar(value=f"{settings.risk_per_trade:.4f}")
        self.stop_var = tk.StringVar(value=f"{settings.default_stop_points:.1f}")
        self.max_qty_var = tk.StringVar(value=str(settings.max_quantity))
        self.strategy_var = tk.StringVar(value="Auto Compare (Best)")
        self.status_var = tk.StringVar(value="Load a CSV or use demo data to begin.")
        self.data_summary_var = tk.StringVar(value="No dataset loaded.")

        self.strategy_catalog = build_strategy_catalog(settings.default_stop_points)

        self._build_layout()

    def _build_layout(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        controls = ttk.Frame(self.root, padding=16)
        controls.grid(row=0, column=0, sticky="ns")
        controls.columnconfigure(0, weight=1)

        results = ttk.Frame(self.root, padding=(0, 16, 16, 16))
        results.grid(row=0, column=1, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(1, weight=1)
        results.rowconfigure(2, weight=1)

        ttk.Label(controls, text="Backtest Setup", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        ttk.Label(controls, text="Historical CSV").grid(row=1, column=0, sticky="w", pady=(16, 4))
        ttk.Entry(controls, textvariable=self.csv_path_var, width=36).grid(row=2, column=0, sticky="ew")
        ttk.Button(controls, text="Browse CSV", command=self.browse_csv).grid(
            row=3, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(controls, text="Use Demo Data", command=self.use_demo_data).grid(
            row=4, column=0, sticky="ew", pady=(8, 0)
        )

        form_specs = [
            ("Instrument Name", self.symbol_var),
            ("Paper Capital", self.capital_var),
            ("Risk Per Trade", self.risk_var),
            ("Default Stop Points", self.stop_var),
            ("Max Quantity", self.max_qty_var),
        ]
        row = 5
        for label_text, variable in form_specs:
            ttk.Label(controls, text=label_text).grid(row=row, column=0, sticky="w", pady=(14, 4))
            ttk.Entry(controls, textvariable=variable).grid(row=row + 1, column=0, sticky="ew")
            row += 2

        ttk.Label(controls, text="Strategy").grid(row=row, column=0, sticky="w", pady=(14, 4))
        strategy_values = ["Auto Compare (Best)", *self.strategy_catalog.keys()]
        ttk.Combobox(
            controls,
            textvariable=self.strategy_var,
            values=strategy_values,
            state="readonly",
        ).grid(row=row + 1, column=0, sticky="ew")

        ttk.Button(controls, text="Run Backtest", command=self.run_backtest).grid(
            row=row + 2, column=0, sticky="ew", pady=(18, 0)
        )

        ttk.Separator(controls).grid(row=row + 3, column=0, sticky="ew", pady=16)
        ttk.Label(controls, textvariable=self.data_summary_var, wraplength=280, justify="left").grid(
            row=row + 4, column=0, sticky="w"
        )

        ttk.Label(results, text="Backtest Results", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 0), pady=(0, 12)
        )

        summary_frame = ttk.LabelFrame(results, text="Summary", padding=12)
        summary_frame.grid(row=1, column=0, sticky="nsew")
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.summary_text = tk.Text(summary_frame, height=10, wrap="word", font=("Consolas", 10))
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        self.summary_text.configure(state="disabled")

        lower = ttk.Frame(results)
        lower.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)

        ranking_frame = ttk.LabelFrame(lower, text="Strategy Ranking", padding=10)
        ranking_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ranking_frame.columnconfigure(0, weight=1)
        ranking_frame.rowconfigure(0, weight=1)

        self.ranking_tree = ttk.Treeview(
            ranking_frame,
            columns=("strategy", "profit", "equity", "trades", "win_rate", "drawdown"),
            show="headings",
            height=12,
        )
        ranking_columns = {
            "strategy": ("Strategy", 150),
            "profit": ("Net Profit", 100),
            "equity": ("Ending Equity", 110),
            "trades": ("Trades", 70),
            "win_rate": ("Win Rate %", 90),
            "drawdown": ("Max Drawdown", 110),
        }
        for key, (heading, width) in ranking_columns.items():
            self.ranking_tree.heading(key, text=heading)
            self.ranking_tree.column(key, width=width, anchor="center")
        self.ranking_tree.grid(row=0, column=0, sticky="nsew")
        self.ranking_tree.bind("<<TreeviewSelect>>", self.on_select_run)

        trades_frame = ttk.LabelFrame(lower, text="Trade Log", padding=10)
        trades_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        trades_frame.columnconfigure(0, weight=1)
        trades_frame.rowconfigure(0, weight=1)

        self.trade_tree = ttk.Treeview(
            trades_frame,
            columns=("time", "action", "qty", "price", "pnl", "reason"),
            show="headings",
            height=12,
        )
        trade_columns = {
            "time": ("Time", 135),
            "action": ("Action", 70),
            "qty": ("Qty", 60),
            "price": ("Price", 80),
            "pnl": ("PnL", 80),
            "reason": ("Reason", 180),
        }
        for key, (heading, width) in trade_columns.items():
            self.trade_tree.heading(key, text=heading)
            self.trade_tree.column(key, width=width, anchor="center")
        self.trade_tree.grid(row=0, column=0, sticky="nsew")

        ttk.Label(self.root, textvariable=self.status_var, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10)
        )

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select historical price CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        self.csv_path_var.set(path)
        self.load_dataset(Path(path))

    def use_demo_data(self):
        self.data = generate_demo_data()
        self.csv_path_var.set("")
        self.data_summary_var.set(
            f"Demo dataset loaded: {len(self.data)} candles from "
            f"{self.data.index[0]:%Y-%m-%d %H:%M} to {self.data.index[-1]:%Y-%m-%d %H:%M}."
        )
        self.status_var.set("Demo dataset ready. Run a backtest to compare strategies.")

    def load_dataset(self, path):
        try:
            self.data = load_price_data(path)
        except Exception as exc:
            messagebox.showerror("Unable to load CSV", str(exc))
            self.status_var.set("CSV load failed. Check the file format and try again.")
            return

        self.data_summary_var.set(
            f"Loaded {len(self.data)} candles from {path.name}\n"
            f"Range: {self.data.index[0]:%Y-%m-%d %H:%M} to {self.data.index[-1]:%Y-%m-%d %H:%M}"
        )
        self.status_var.set(f"Loaded dataset from {path.name}.")

    def run_backtest(self):
        if self.data is None:
            self.use_demo_data()

        try:
            config = BacktestConfig(
                symbol=self.symbol_var.get().strip() or self.settings.instrument_name,
                starting_capital=float(self.capital_var.get()),
                risk_per_trade=float(self.risk_var.get()),
                default_stop_points=float(self.stop_var.get()),
                max_quantity=int(self.max_qty_var.get()),
            )
        except ValueError:
            messagebox.showerror("Invalid input", "Capital, risk, stop points, and max quantity must be numeric.")
            return

        self.strategy_catalog = build_strategy_catalog(config.default_stop_points)
        selected = self.strategy_var.get()
        if selected == "Auto Compare (Best)":
            strategy_builders = self.strategy_catalog.items()
        else:
            strategy_builders = [(selected, self.strategy_catalog[selected])]

        engine = BacktestEngine(config)
        runs = []
        for _, builder in strategy_builders:
            runs.append(engine.run(self.data, builder()))

        self.last_runs = rank_runs(runs)
        self.populate_ranking()
        self.show_run(self.last_runs[0])
        self.status_var.set(
            f"Backtest complete. Best strategy on this dataset: {self.last_runs[0].strategy_name} "
            f"with net profit {self.last_runs[0].net_profit:.2f}."
        )

    def populate_ranking(self):
        self.ranking_tree.delete(*self.ranking_tree.get_children())
        for index, run in enumerate(self.last_runs):
            self.ranking_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    run.strategy_name,
                    f"{run.net_profit:.2f}",
                    f"{run.ending_equity:.2f}",
                    run.total_trades,
                    f"{run.win_rate:.1f}",
                    f"{run.max_drawdown:.2f}",
                ),
            )
        if self.last_runs:
            self.ranking_tree.selection_set("0")

    def on_select_run(self, _event):
        selection = self.ranking_tree.selection()
        if not selection:
            return
        run = self.last_runs[int(selection[0])]
        self.show_run(run)

    def show_run(self, run):
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert(
            "end",
            (
                f"Selected Strategy : {run.strategy_name}\n"
                f"Net Profit        : {run.net_profit:.2f}\n"
                f"Ending Equity     : {run.ending_equity:.2f}\n"
                f"Closed Trades     : {run.total_trades}\n"
                f"Win Rate          : {run.win_rate:.1f}%\n"
                f"Wins / Losses     : {run.wins} / {run.losses}\n"
                f"Max Drawdown      : {run.max_drawdown:.2f}\n"
                f"Dataset Candles   : {len(self.data)}\n"
                f"Dataset Range     : {self.data.index[0]:%Y-%m-%d %H:%M} to "
                f"{self.data.index[-1]:%Y-%m-%d %H:%M}\n"
            ),
        )
        if self.strategy_var.get() == "Auto Compare (Best)":
            self.summary_text.insert(
                "end",
                "\nThis result is the best performer among the built-in strategies on the loaded dataset.\n",
            )
        self.summary_text.configure(state="disabled")

        self.trade_tree.delete(*self.trade_tree.get_children())
        for fill in run.trade_log:
            self.trade_tree.insert(
                "",
                "end",
                values=(
                    fill.time.strftime("%Y-%m-%d %H:%M"),
                    fill.action,
                    fill.quantity,
                    f"{fill.price:.2f}",
                    f"{fill.pnl:.2f}",
                    fill.reason,
                ),
            )
