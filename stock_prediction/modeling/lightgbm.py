from calendar import monthrange
from typing import Optional

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from stock_prediction.helpers.logging.log_config import get_logger
from stock_prediction.modeling.forecast_model import ForecastModel

logger = get_logger()


def get_time_features(row: pd.DataFrame) -> pd.Series:
    row_ = row["Date"]
    day = row_.day
    week_day = row_.weekday()
    month = row_.month
    _, ndays_month = monthrange(row_.year, month)

    frac_month = day / ndays_month
    frac_week = (week_day + 1) / 5
    frac_year = (month - 1 + frac_month) / 12
    return pd.Series(
        {"frac_week": frac_week, "frac_month": frac_month, "frac_year": frac_year}
    )


def make_shifted_series_df(
    series: pd.Series, min_shift: int, max_shift: int, shift_name: str = "shifted"
):
    return pd.DataFrame(
        {
            f"{shift_name}_{abs(i)}": series.shift(i)
            for i in range(min_shift, max_shift)
        },
        index=series.index,
    )


def make_rolling_window_features_df(
    series: pd.DataFrame, windows: list[int], stats: list[str]
):
    series_dict = {}
    for window in windows:
        for stat in stats:
            series_dict[f"{stat}_{window}"] = series.rolling(window=window).agg(stat)

    return pd.DataFrame(series_dict)


class UnivariateLightGBMs(ForecastModel):
    LABEL_COL = "label"
    N_FORECAST_COL = "n_forecast"
    INITIAL_INDEX_COL = "initial_index"
    PREDICTION_COL = "prediction"

    def __init__(
        self,
        lgbm_hpts: Optional[dict] = None,
        windows: list[int] = [5, 20, 60, 180],
        stats: list[str] = ["mean", "std", "min", "max"],
        n_shifts: int = 20,
        n_steps_predict: int = 20,
        **kwargs,
    ):

        self.windows = windows
        self.stats = stats
        self.n_shifts = n_shifts
        self.n_steps_predict = n_steps_predict
        self.lgbm_hpts = lgbm_hpts or dict()
        self.models: dict[str, LGBMRegressor] = dict()

    def preprocess(self, series: pd.Series) -> pd.DataFrame:
        series_reset = series.reset_index(drop=True)

        df_time_features = series.reset_index().apply(get_time_features, axis=1)

        df_shifted_series = make_shifted_series_df(
            series=series_reset, min_shift=0, max_shift=self.n_shifts
        )

        df_labels = make_shifted_series_df(
            series=series_reset,
            min_shift=-self.n_steps_predict,
            max_shift=0,
            shift_name=self.LABEL_COL,
        )

        df_rolling_features = make_rolling_window_features_df(
            series=series_reset, windows=self.windows, stats=self.stats
        )

        df_all_features = pd.concat(
            [df_time_features, df_shifted_series, df_rolling_features], axis=1
        ).iloc[max(self.windows + [self.n_shifts]) : -self.n_steps_predict]

        df_labels = df_labels.iloc[
            max(self.windows + [self.n_shifts]) : -self.n_steps_predict
        ]

        df_processed_list = []
        for col in df_labels.columns:
            df_tmp = df_all_features.copy()
            df_tmp[self.N_FORECAST_COL] = int(col.split("_")[-1])
            df_tmp[self.LABEL_COL] = df_labels[col]
            df_processed_list.append(df_tmp)

        df_processed_expanded = (
            pd.concat(df_processed_list, axis=0)
            .reset_index()
            .rename(columns={"index": self.INITIAL_INDEX_COL})
        )

        return df_processed_expanded

    def fit(
        self, df: pd.DataFrame, valid_range: Optional[tuple[int, int]] = None, **kwargs
    ):
        for symbol in df.columns:
            print(f"Training {symbol}...")
            # Preprocess and split the data
            df_train = self.preprocess(df[symbol])
            df_valid = None
            if valid_range is not None:
                df_train = df_train.iloc[: valid_range[0]]
                df_valid = df_train.iloc[valid_range[0] : valid_range[1]]

            # Initialize and fit the model
            lgbm_model = LGBMRegressor(**self.lgbm_hpts)
            lgbm_model.fit(
                df_train.drop([self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1),
                df_train[self.LABEL_COL],
                eval_set=[
                    (
                        df_valid.drop([self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1),
                        df_valid[self.LABEL_COL],
                    )
                ]
                if df_valid is not None
                else None,
            )
            self.models[symbol] = lgbm_model

    def predict(
        self,
        df_predict: pd.DataFrame,
        n_steps_predict: int,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
        **kwargs,
    ):
        if n_steps_predict > self.n_steps_predict:
            raise ValueError(
                "n_steps_predict cannot be greater than the "
                f"model's n_steps_predict ({self.n_steps_predict})"
            )

        if index_start is None:
            index_start = df_predict.shape[0] - n_steps_predict
        if index_end is None:
            index_end = df_predict.shape[0] - n_steps_predict + 1

        predictions = np.zeros(
            (index_end - index_start, df_predict.shape[1], n_steps_predict)
        )

        for i, symbol in enumerate(df_predict.columns):
            df_predict_preprocessed = self.preprocess(df_predict[symbol])
            df_predict_preprocessed = df_predict_preprocessed[
                df_predict_preprocessed[self.INITIAL_INDEX_COL].between(
                    index_start, index_end
                )
            ]
            predictions_lgbm = self.models[symbol].predict(
                df_predict_preprocessed.drop(
                    [self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1
                )
            )
            df_preds = df_predict_preprocessed[
                [self.INITIAL_INDEX_COL, self.N_FORECAST_COL]
            ].copy()
            df_preds[self.PREDICTION_COL] = predictions_lgbm

            predictions[:, i, :] = (
                df_preds.groupby(self.INITIAL_INDEX_COL)[
                    [self.INITIAL_INDEX_COL, self.N_FORECAST_COL, self.PREDICTION_COL]
                ]
                .apply(
                    lambda x: (
                        1
                        + pd.Series(
                            x.sort_values(by=self.N_FORECAST_COL)[
                                self.PREDICTION_COL
                            ].values
                        )
                    ).cumprod()
                )
                .sort_index()
                .to_numpy()[:, :n_steps_predict]
            )

        return predictions
