import pandas as pd
from sqlalchemy.orm import Session
from stock_tracker.db.session import SessionLocal
from stock_tracker.db.models import TickerModel


class PostgresTickerStorage:
    def _get_session(self) -> Session:
        return SessionLocal()

    def load_existing_tickers(self) -> pd.DataFrame:
        with self._get_session() as session:
            rows = session.query(TickerModel).all()
            if not rows:
                return pd.DataFrame(columns=["symbol"])
            return pd.DataFrame([{"symbol": row.symbol} for row in rows])

    def save_tickers(self, df: pd.DataFrame) -> None:
        with self._get_session() as session:
            existing = {row.symbol for row in session.query(TickerModel.symbol).all()}
            new_symbols = [
                TickerModel(symbol=symbol)
                for symbol in df["symbol"]
                if symbol not in existing
            ]
            if new_symbols:
                session.add_all(new_symbols)
                session.commit()
