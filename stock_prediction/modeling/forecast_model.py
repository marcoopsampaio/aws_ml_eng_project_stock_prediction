from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class ForecastModel(ABC):
    """
    Forecast model base class.
    """

    @abstractmethod
    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def fit(self, df: pd.DataFrame, **kwargs):
        pass

    @abstractmethod
    def predict(
        self,
        df_predict: pd.DataFrame,
        n_steps_predict: int,
        index_start: Optional[int] = None,
        index_end: Optional[int] = None,
        **kwargs,
    ):
        pass
