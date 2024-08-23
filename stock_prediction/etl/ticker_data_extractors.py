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


if __name__ == "__main__":
    extract_ticker_data()
