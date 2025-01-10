from calendar import monthrange
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

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


class UnivariateSklearnAPIBased(ForecastModel):
    LABEL_COL = "label"
    N_FORECAST_COL = "n_forecast"
    INITIAL_INDEX_COL = "initial_index"
    PREDICTION_COL = "prediction"

    def __init__(
        self,
        model_class_type: BaseEstimator,
        hpts: Optional[dict] = None,
        windows: list[int] = [5, 20, 60, 180],
        stats: list[str] = ["mean", "std", "min", "max"],
        n_shifts: int = 20,
        n_steps_predict: int = 20,
        **kwargs,
    ):

        self.model_class_type = model_class_type
        self.windows = windows
        self.stats = stats
        self.n_shifts = n_shifts
        self.n_steps_predict = n_steps_predict
        self.hpts = hpts or dict()
        self.models: dict[str, BaseEstimator] = dict()

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
            df_all = self.preprocess(df[symbol])
            df_valid = None

            if valid_range is not None:
                df_train = df_all[df_all[self.INITIAL_INDEX_COL] < valid_range[0]]
                df_valid = df_all[
                    (df_all[self.INITIAL_INDEX_COL] >= valid_range[0])
                    & (df_all[self.INITIAL_INDEX_COL] < valid_range[1])
                ]
            else:
                df_train = df_all

            # Initialize and fit the model
            model = self.model_class_type(**self.hpts)
            if df_valid is not None:
                model.fit(
                    df_train.drop([self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1),
                    df_train[self.LABEL_COL],
                    eval_set=[
                        (
                            df_valid.drop(
                                [self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1
                            ),
                            df_valid[self.LABEL_COL],
                        )
                    ],
                )
            else:
                model.fit(
                    df_train.drop([self.LABEL_COL, self.INITIAL_INDEX_COL], axis=1),
                    df_train[self.LABEL_COL],
                )
            self.models[symbol] = model

    def _get_dict_all_features_dfs(
        self,
        df: pd.DataFrame,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
    ):
        dict_all_features_dfs: dict[str, pd.DataFrame] = dict()
        for symbol in df.columns:
            df_features = self.preprocess(df[symbol])
            df_features = df_features[
                df_features[self.INITIAL_INDEX_COL].between(index_start, index_end)
            ].drop(columns=[self.LABEL_COL])
            dict_all_features_dfs[symbol] = df_features

        return dict_all_features_dfs

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

        dict_all_features_dfs = self._get_dict_all_features_dfs(
            df_predict, index_start, index_end
        )

        for i, symbol in enumerate(df_predict.columns):
            predictions_model = self.models[symbol].predict(
                dict_all_features_dfs[symbol].drop([self.INITIAL_INDEX_COL], axis=1)
            )
            df_preds = dict_all_features_dfs[symbol][
                [self.INITIAL_INDEX_COL, self.N_FORECAST_COL]
            ].copy()
            df_preds[self.PREDICTION_COL] = predictions_model

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


class MultivariateSklearnAPIBased(UnivariateSklearnAPIBased):
    def preprocess(self, df: pd.DataFrame):
        df_all_features = None
        df_all_labels: dict[str, pd.DataFrame] = dict()
        for symbol in df.columns:
            # Preprocess and split the data
            df_symbol = super().preprocess(df[symbol])

            per_symbol_feature_columns = [
                col
                for col in df_symbol.columns
                if col
                not in [self.LABEL_COL, self.INITIAL_INDEX_COL, self.N_FORECAST_COL]
            ]
            column_renames = {
                feature: f"{feature}_{symbol}" for feature in per_symbol_feature_columns
            }

            df_symbol = df_symbol.rename(columns=column_renames)

            if df_all_features is None:
                df_all_features = df_symbol.drop(columns=[self.LABEL_COL])
            else:
                df_all_features = df_all_features.merge(
                    df_symbol.drop(columns=[self.LABEL_COL]),
                    on=[
                        self.INITIAL_INDEX_COL,
                        self.N_FORECAST_COL,
                    ],
                    how="inner",
                )

            df_all_labels[symbol] = df_symbol[
                [self.LABEL_COL, self.INITIAL_INDEX_COL, self.N_FORECAST_COL]
            ]

        return df_all_features, df_all_labels

    def fit(
        self, df: pd.DataFrame, valid_range: Optional[tuple[int, int]] = None, **kwargs
    ):
        # Make shared features dataset
        df_all_features, df_all_labels = self.preprocess(df)
        all_labels_train: dict[str, pd.DataFrame] = dict()
        all_labels_valid: dict[str, pd.DataFrame] = dict()
        df_train_all = df_all_features
        df_valid_all = None

        if valid_range is not None:
            for symbol in df.columns:
                all_labels_train[symbol] = df_all_labels[symbol][
                    df_all_labels[symbol][self.INITIAL_INDEX_COL] < valid_range[0]
                ]
                all_labels_valid[symbol] = df_all_labels[symbol][
                    (df_all_labels[symbol][self.INITIAL_INDEX_COL] >= valid_range[0])
                    & (df_all_labels[symbol][self.INITIAL_INDEX_COL] < valid_range[1])
                ]

            df_train_all = df_all_features[
                df_all_features[self.INITIAL_INDEX_COL] < valid_range[0]
            ]
            df_valid_all = df_all_features[
                (df_all_features[self.INITIAL_INDEX_COL] >= valid_range[0])
                & (df_all_features[self.INITIAL_INDEX_COL] < valid_range[1])
            ]
        else:
            for symbol in df.columns:
                all_labels_train[symbol] = df_all_labels[symbol]
            df_train_all = df_all_features

        for symbol in df.columns:
            logger.info(f"Training {symbol}...")
            model = self.model_class_type(**self.hpts)
            if df_valid_all is not None:
                model.fit(
                    df_train_all.drop([self.INITIAL_INDEX_COL], axis=1),
                    all_labels_train[symbol][self.LABEL_COL],
                    eval_set=[
                        (
                            df_valid_all.drop([self.INITIAL_INDEX_COL], axis=1),
                            all_labels_valid[symbol][self.LABEL_COL],
                        )
                    ]
                    if df_valid_all is not None
                    else None,
                )
            else:
                model.fit(
                    df_train_all.drop([self.INITIAL_INDEX_COL], axis=1),
                    all_labels_train[symbol][self.LABEL_COL],
                )

            self.models[symbol] = model

    def _get_dict_all_features_dfs(
        self,
        df: pd.DataFrame,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
    ):
        df_all_features, _ = self.preprocess(df)
        df_all_features = df_all_features[
            df_all_features[self.INITIAL_INDEX_COL].between(index_start, index_end)
        ]
        dict_all_features_dfs: dict[str, pd.DataFrame] = dict()

        for symbol in df.columns:
            dict_all_features_dfs[symbol] = df_all_features

        return dict_all_features_dfs
