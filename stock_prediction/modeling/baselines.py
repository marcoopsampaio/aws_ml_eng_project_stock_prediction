from typing import Optional

import numpy as np
import pandas as pd

from stock_prediction.helpers.logging.log_config import get_logger
from stock_prediction.modeling.forecast_model import ForecastModel

logger = get_logger()


class RollingGeometricAverage(ForecastModel):
    def __init__(self, window: int = 20, **kwargs):
        self.window = window
        pass

    def fit(self, df_train: pd.DataFrame, **kwargs):
        logger.info(
            "This model simply uses a rolling average rule so it is not fitted."
        )

    def predict(
        self,
        df_predict: pd.DataFrame,
        n_steps_predict: int = 1,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
        **kwargs,
    ):
        """
        Predict future values using a rolling geometric average method.

        Parameters
        ----------
        df_predict : pd.DataFrame
            The dataframe containing the data to predict from.
        n_steps_predict : int, optional
            The number of steps ahead to predict. Default is 1.
        index_start : int, optional
            The starting index for prediction. If None, defaults to the last available index minus n_steps_predict.
        index_end : int, optional
            The ending index for prediction. If None, defaults to the last available index minus n_steps_predict.
        **kwargs
            Additional keyword arguments.

        Returns
        -------
        np.ndarray
            A numpy array of predicted values.
        """
        if index_start is None:
            index_start = df_predict.shape[0] - n_steps_predict

        if index_end is None:
            index_end = df_predict.shape[0] - n_steps_predict

        df_rolling_geometric_average = (
            df_predict[index_start - self.window : index_end]
            .reset_index(drop=True)
            .rolling(window=self.window)
            .apply(lambda y: (1 + y).cumprod().iloc[-1] ** (1 / self.window))
        )

        np_range = np.arange(n_steps_predict)

        predictions = (
            df_rolling_geometric_average[self.window - 1 :]
            .map(lambda x: x ** (np_range + 1))
            .to_numpy()
        )

        return np.array(predictions.tolist())
