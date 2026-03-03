from stock_tracker.utils.file_util import create_ticker_file
from stock_tracker.config.settings import settings
from pathlib import Path
import logging
import pandas as pd


class FileTickerStorage:
    def __init__(self, ticker_file: Path | None = None):
        # Default to your existing config path
        self.ticker_file = ticker_file or settings.TICKER_FILE
        print(settings.TICKER_FILE)

    def load_existing_tickers(self) -> pd.DataFrame:
        """Load existing ticker list from Excel (if it exists)."""
        if not self.ticker_file.exists():
            logging.info("Ticker file does not exist yet.")
            create_ticker_file(self.ticker_file)
            logging.info("Ticker excel file created.")
            return pd.DataFrame(columns=["Symbol"])

        return pd.read_excel(self.ticker_file)

    def save_tickers(self, df: pd.DataFrame) -> None:
        """Persist ticker DataFrame to Excel."""
        df.to_excel(self.ticker_file, index=False)
        logging.info("Ticker list saved to %s", self.ticker_file.name)
