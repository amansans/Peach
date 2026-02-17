from datetime import datetime


def today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return datetime.now().strftime("%Y-%m-%d")
