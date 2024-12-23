import copy
from typing import Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from stock_prediction.helpers.logging.log_config import get_logger
from stock_prediction.modeling.forecast_model import ForecastModel

logger = get_logger()


class UnivariateARIMAs(ForecastModel):
    def __init__(
        self,
        p: int = 20,
        d: int = 1,
        q: int = 20,
    ):

        """
        Initialize the UnivariateARMA model.

        Parameters
        ----------
        p : int, optional
            The number of autoregressive terms. Default is 20.
        d : int, optional
            The number of differencing terms. Default is 1.
        q : int, optional
            The number of moving average terms. Default is 20.

        Attributes
        ----------
        p : int
            The number of autoregressive terms.
        q : int
            The number of moving average terms.
        models : dict
            A dictionary of ARIMA models, keyed by symbol.
        """
        self.p = p
        self.d = d
        self.q = q
        self.models: dict[str, ARIMA] = dict()

    def fit(self, df: pd.DataFrame, **kwargs):
        """
        Fit the UnivariateARIMAs to the given training data.

        Parameters
        ----------
        df_train : pd.DataFrame
            The dataframe containing the training data.

        Returns
        -------
        None
        """

        df_train = df.reset_index(drop=True)

        start_params = None

        for symbol in df_train.columns:
            arima_model = ARIMA(df_train[symbol], order=(self.p, self.d, self.q))
            if len(self.models) == df_train.shape[1]:
                start_params = self.models[symbol].params

            if start_params is None:
                arima_model = arima_model.fit()
                start_params = arima_model.params
            else:
                arima_model = arima_model.fit(start_params=start_params)

            self.models[symbol] = arima_model

    def predict(
        self,
        df_predict: pd.DataFrame,
        n_steps_predict: int,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
        **kwargs,
    ):

        """
        Predict future values using the UnivariateARIMAs.

        Parameters
        ----------
        df_predict : pd.DataFrame
            The dataframe containing the data to predict from.
        n_steps_predict : int
            The number of steps ahead to predict.
        index_start : int, optional
            The starting index for prediction. If None, defaults to the last available index minus n_steps_predict.
        index_end : int, optional
            The ending index for prediction. If None, defaults to the last available index minus n_steps_predict + 1.

        Returns
        -------
        np.ndarray
            A numpy array of predicted values of shape (df_predict.shape[0], df_predict.shape[1], n_steps_predict).
        """
        if index_start is None:
            index_start = df_predict.shape[0] - n_steps_predict
        if index_end is None:
            index_end = df_predict.shape[0] - n_steps_predict + 1

        n_rows_predict = index_end - index_start
        predictions = np.zeros((n_rows_predict, df_predict.shape[1], n_steps_predict))

        if self.models is None:
            raise ValueError("Model must be fit before calling predict.")

        # copy self.models
        models = copy.deepcopy(self.models)

        for index in range(index_start, index_end):
            # Add one new real instance of each symbol
            for symbol in models.keys():
                models.update(
                    {
                        symbol: models[symbol].append(
                            df_predict[symbol][index : index + 1].to_numpy()
                        )
                    }
                )

            predictions[index - index_start, :, :] = self.forecast_next_n_steps(
                index_first=index + 1,
                n_steps_predict=n_steps_predict,
                models=models,
            )

        return predictions

    def forecast_next_n_steps(
        self, index_first: int, n_steps_predict: int, models: dict
    ):

        n_symbols = len(models.keys())
        predictions = np.zeros((n_symbols, n_steps_predict))
        for i, symbol in enumerate(models.keys()):
            predictions[i, :] = (
                1
                + models[symbol].predict(
                    start=index_first,
                    end=index_first + n_steps_predict - 1,  # the end index is inclusive
                )
            ).cumprod()
        return predictions
