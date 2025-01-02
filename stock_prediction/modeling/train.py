"""
This script is used to train the model periodically.
"""
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from stock_prediction.etl.ticker_data_extractors import (
    extract_ticker_data,
    load_cleaned_dataset,
)
from stock_prediction.helpers.logging.log_config import get_logger

# from stock_prediction.modeling.lightgbm import UnivariateLightGBMs
from stock_prediction.modeling.baselines import RollingGeometricAverage

logger = get_logger()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepares data, trains model and uploads predictions to S3"
    )
    parser.add_argument(
        "--model_type",
        type=str,
        default="univariate_lgbm",
        help="Type of model to train",
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

    # Get last date in the dataset
    last_date = df_all_symbols.index[-1]

    latest_prices = yf.download(
        list(df_all_symbols.columns),
        start=last_date.strftime("%Y-%m-%d"),
        end=datetime.now().strftime("%Y-%m-%d"),
    )

    # Extract the 'Adj Close' prices as of the last day in the extracted returns dataset
    last_day_close = latest_prices["Adj Close"][
        latest_prices.index == last_date.strftime("%Y-%m-%d")
    ].iloc[0]

    df_all_symbols_prices = (
        df_all_symbols_cumulative[last_day_close.index]
        * last_day_close
        / df_all_symbols_cumulative[last_day_close.index].iloc[-1]
    )

    # Calculate absolute predictions
    df_all_symbols_prices["is_predicted"] = False

    logger.info(
        f"Dataset loaded with {df_all_symbols_prices.shape[0]} samples and {df_all_symbols_prices.shape[1]} features."
    )
    # Train the model
    model = RollingGeometricAverage()
    model.fit(df_all_symbols)

    n_steps_predict = args.n_steps_predict
    n_symbols = len(last_day_close.index)

    # Forecast predictions based on the last observation in the dataset
    predictions = model.predict(
        df_all_symbols[last_day_close.index],
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

    df_all_symbols_prices.to_feather("predictions.feather")

    logger.info("Predictions saved to predictions.feather")
