from strategy.nifty_strategy import NiftyEmaCrossoverStrategy


_default_strategy = NiftyEmaCrossoverStrategy()


def generate_signal(df, position=None):
    return _default_strategy.generate_signal(df, position)
