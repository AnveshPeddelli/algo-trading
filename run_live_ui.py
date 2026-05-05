import tkinter as tk

from ui.trading_desk import TradingDeskApp


def main():
    root = tk.Tk()
    TradingDeskApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
