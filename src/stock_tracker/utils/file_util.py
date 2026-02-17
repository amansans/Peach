import pandas as pd
from pathlib import Path


def create_ticker_file(filepath: Path) -> None:
    """
    Create ticker file when it does not exist
    """
    df = pd.DataFrame(columns=["Symbol"])
    df.to_excel(filepath, index=False)
