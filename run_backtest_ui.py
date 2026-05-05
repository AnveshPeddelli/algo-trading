import tkinter as tk

from ui.backtest_app import BacktestWorkbench


def main():
    root = tk.Tk()
    BacktestWorkbench(root)
    root.mainloop()


if __name__ == "__main__":
    main()
