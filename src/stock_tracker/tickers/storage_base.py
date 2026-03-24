from typing import Protocol
import pandas as pd


class TickerStorage(Protocol):
    def load_existing_tickers(self) -> pd.DataFrame: ...

    def save_tickers(self, df: pd.DataFrame) -> None: ...
