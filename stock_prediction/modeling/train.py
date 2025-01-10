"""
This script is used to train the model periodically.
"""
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from stock_prediction.deployment.utils import PREDICTIONS_FILE_NAME
from stock_prediction.etl.ticker_data_extractors import (
    extract_ticker_data,
    load_cleaned_dataset,
)
from stock_prediction.helpers.logging.log_config import get_logger
from stock_prediction.modeling.lightgbm_model import UnivariateLightGBMs

logger = get_logger()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepares data, trains model and uploads predictions to S3"
    )

    parser.add_argument(
        "--n_steps_predict", type=int, default=20, help="Number of days to predict"
    )

    args = parser.parse_args()

    # Extract raw data
    df_all_symbols = extract_ticker_data(
        cache_path=Path("extracted_data.csv"), overwrite_cache=True
    )

    # Clean the data
    df_all_symbols = load_cleaned_dataset(df_all_symbols)

    # Calculate cumulative returns to be able to get absolute prices
    df_all_symbols_cumulative = (1 + df_all_symbols).cumprod()

    # Get last date in the dataset for which closing prices are available
    latest_prices = None
    i_latest_prices = len(df_all_symbols)
    for i in range(len(df_all_symbols) - 1, 0, -1):
        i_latest_prices = i
        last_date = df_all_symbols.index[i_latest_prices]
        latest_prices = yf.download(
            list(df_all_symbols.columns),
            start=last_date.strftime("%Y-%m-%d"),
            end=datetime.now().strftime("%Y-%m-%d"),
        )
        if len(latest_prices["Adj Close"]) != 0:
            break

    # Extract the 'Adj Close' prices as of the last day in the extracted returns dataset
    last_day_close = latest_prices["Adj Close"][latest_prices.index == last_date.strftime("%Y-%m-%d")].iloc[0]  # type: ignore

    # Clip the end of the dataframes if needed, and select only the columns we need
    df_all_symbols = df_all_symbols.iloc[: i_latest_prices + 1][last_day_close.index]
    df_all_symbols_cumulative = df_all_symbols_cumulative.iloc[: i_latest_prices + 1][
        last_day_close.index
    ]

    # Calculate absolute prices
    df_all_symbols_prices = (
        df_all_symbols_cumulative * last_day_close / df_all_symbols_cumulative.iloc[-1]
    )

    # Calculate absolute predictions
    df_all_symbols_prices["is_predicted"] = False

    logger.info(
        f"Dataset loaded with {df_all_symbols_prices.shape[0]} samples and {df_all_symbols_prices.shape[1]} features."
    )
    print(df_all_symbols)

    # Train the model
    model = UnivariateLightGBMs(
        windows=[5, 20, 60, 180, 400],
        lgbm_hpts={"max_depth": 3, "learning_rate": 0.01},
    )
    model.fit(df_all_symbols)

    n_steps_predict = args.n_steps_predict
    n_symbols = len(last_day_close.index)

    # Forecast predictions based on the last observation in the dataset
    predictions = model.predict(
        df_all_symbols,
        n_steps_predict=n_steps_predict,
        index_start=df_all_symbols.shape[0] - 1,
        index_end=df_all_symbols.shape[0],
    )

    logger.info(
        f"Predictions made for {n_steps_predict} days with {n_symbols} symbols."
    )

    df_predictions = pd.DataFrame(
        (
            predictions[-1]
            * df_all_symbols_prices.drop(columns=["is_predicted"])
            .iloc[-1]
            .to_numpy()
            .reshape(n_symbols, 1)
        ).T,
        columns=list(last_day_close.index),
        # generate an index of business days starting from the last day of df_train
        index=pd.date_range(
            start=df_all_symbols_prices.index[-1] + pd.Timedelta(days=1),
            periods=n_steps_predict,
            freq="B",
        ),
    )
    # name the index as Date
    df_predictions.index.name = "Date"
    df_predictions["is_predicted"] = True

    df_all_symbols_prices = pd.concat([df_all_symbols_prices, df_predictions])

    df_all_symbols_prices.to_feather(PREDICTIONS_FILE_NAME)

    logger.info(f"Predictions saved to {PREDICTIONS_FILE_NAME}")
