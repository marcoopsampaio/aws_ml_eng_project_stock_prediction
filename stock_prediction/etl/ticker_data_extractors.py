from pathlib import Path

import pandas as pd
import quantstats as qs

from stock_prediction.commons import (
    DEFAULT_DATA_EXTRACTION_OUTPUT_PATH,
    DEFAULT_SYMBOLS_CSV_PATH,
)
from stock_prediction.helpers.logging.log_config import get_logger

logger = get_logger()


def extract_ticker_data(
    symbols_csv_path: Path = DEFAULT_SYMBOLS_CSV_PATH,
    cache_path: Path = DEFAULT_DATA_EXTRACTION_OUTPUT_PATH,
    overwrite_cache: bool = False,
):

    symbols = list(pd.read_csv(symbols_csv_path)["fund_symbol"])

    logger.info(f"Extracting data for {len(symbols)} symbols.")

    if cache_path.exists() and not overwrite_cache:
        logger.info(f"Loading data from cache: {cache_path}")
        return pd.read_csv(cache_path)

    df_all_symbols = qs.utils.download_returns(symbols)

    logger.info("All symbols data extracted.")

    df_all_symbols.to_csv(cache_path)

    return df_all_symbols


def load_cleaned_dataset():
    df_all_symbols = pd.read_csv(DEFAULT_DATA_EXTRACTION_OUTPUT_PATH)
    df_all_symbols["Date"] = df_all_symbols["Date"].apply(lambda x: pd.Timestamp(x))
    df_all_symbols = df_all_symbols.set_index("Date")
    first_index = df_all_symbols.isna().sum()

    df_all_symbols_clipped = df_all_symbols[
        df_all_symbols.index >= df_all_symbols.index[first_index].max()
    ]

    cols_final = [
        col for col in df_all_symbols.columns if col not in ["RGI", "RYH", "RYT"]
    ]

    return df_all_symbols_clipped[cols_final]


def train_test_split(test_fraction: float = 0.4):
    df = load_cleaned_dataset()
    n_samples_train = int(df.shape[0] * (1 - test_fraction))
    n_samples_test = int(df.shape[0] * test_fraction)
    df_train = df.sort_index(ascending=True).head(n_samples_train)
    df_test = df.sort_index(ascending=True).tail(n_samples_test)

    return df_train, df_test


if __name__ == "__main__":
    extract_ticker_data()
