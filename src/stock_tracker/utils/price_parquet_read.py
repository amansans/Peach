import pandas as pd
from stock_tracker.config.settings import settings

path = settings.PRICE_DIR + "AAPL"
df = pd.read_parquet(path)
print(pd)
