# 📈 Stock Tracker

A Python-based stock data pipeline that:

- Fetches ticker symbols from major stock indices (S&P 500, Dow Jones, Nasdaq 100)
- Downloads historical price data using Yahoo Finance
- Stores price data locally in Parquet format
- Updates only new data on subsequent runs (incremental updates)
- Is fully unit-tested using `pytest`
- Is structured using industry-standard `src/` layout
- Is CI/CD-ready for GitHub Actions

---

## 🧠 Why This Project Exists

This project is built to practice **real-world software engineering** concepts:

- Clean project structure (`src` layout)
- Dependency injection for testability
- Unit testing with mocks & fixtures
- File system isolation using `tmp_path` & `monkeypatch`
- External API mocking (Yahoo Finance)
- CI/CD-ready test suite
- Separation of concerns (fetching, storage, business logic)

This mirrors how production data pipelines are built in finance, data engineering, and backend teams.

---

## 🗂 Project Structure

stock_tracker/
│
├── src/
│ └── stock_tracker/
│ ├── config.py
│ ├── tickers/
│ │ ├── fetch.py
│ │ ├── service.py
│ │ └── storage.py
│ │
│ ├── prices/
│ │ ├── fetch.py
│ │ ├── service.py
│ │ └── storage.py
│ │
│ └── utils/
│ └── file_util.py
│
├── tests/
│ └── stock_tracker/
│ ├── tickers/
│ └── prices/
│
├── pyproject.toml / requirements.txt
├── pytest.ini
├── .gitignore
└── README.md

## 🛠 Tech Stack

- Python 3.10+
- pandas
- yfinance
- requests
- pytest
- Parquet (pyarrow / fastparquet)
- Git & GitHub
- GitHub Actions (CI/CD)

## 📍 Future Enhancements

- [ ] Add GitHub Actions CI pipeline
- [ ] Add retry + backoff for API failures
- [ ] Add CLI interface (argparse / typer)
- [ ] Add Docker support
- [ ] Add caching layer for API calls
- [ ] Add scheduling (cron / Airflow)
- [ ] Add logging configuration file
- [ ] Add data validation checks
