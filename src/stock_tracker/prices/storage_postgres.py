import pandas as pd
from sqlalchemy.orm import Session
from stock_tracker.db.session import SessionLocal
from stock_tracker.db.models import PriceModel


class PostgresPriceStorage:
    def _get_session(self) -> Session:
        return SessionLocal()

    def load_price_parquet_file(self, ticker: str) -> pd.DataFrame:
        """Load all prices for a given ticker from Postgres."""
        with self._get_session() as session:
            rows = session.query(PriceModel).filter(PriceModel.ticker == ticker).all()
            if not rows:
                return pd.DataFrame(
                    columns=["ticker", "date", "open", "high", "low", "close", "volume"]
                )
            return pd.DataFrame(
                [
                    {
                        "ticker": row.ticker,
                        "date": row.date,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                    }
                    for row in rows
                ]
            )

    def store_updated_prices(self, df: pd.DataFrame, ticker: str) -> None:
        """Upsert prices for a ticker. Replaces all existing rows for that ticker."""
        with self._get_session() as session:
            session.query(PriceModel).filter(PriceModel.ticker == ticker).delete()
            rows = [
                PriceModel(
                    ticker=ticker,
                    date=row["date"],
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    volume=row.get("volume"),
                )
                for _, row in df.iterrows()
            ]
            session.add_all(rows)
            session.commit()
