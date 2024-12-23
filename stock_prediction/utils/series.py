import numpy as np
import pandas as pd


def get_normalized_nsteps_ahead_predictions_array(
    df: pd.DataFrame, n_steps_ahead: int, index_start: int, index_end: int
) -> np.ndarray:

    """
    Gets a 3D array of normalized predictions n steps ahead for all symbols in the dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe to get the predictions from.
    n_steps_ahead : int
        The number of steps ahead to predict.
    index_start : int
        The index to start the predictions at.
    index_end : int
        The index to end the predictions at.

    Returns
    -------
    np.ndarray
        A 3D array of normalized predictions with shape (index_end - index_start + 1, df.shape[1], n_steps_ahead).

    """
    predictions = np.zeros((index_end - index_start, df.shape[1], n_steps_ahead))

    for i in range(index_start, index_end):
        predictions[i - index_start, :, :] = n_steps_ahead_normalized_slice_df(
            df, n_steps_ahead, i
        ).T.to_numpy()

    return predictions


def n_steps_ahead_normalized_slice_df(
    df: pd.DataFrame, n_steps_ahead: int, i_start: int
) -> pd.DataFrame:
    """
    Returns a normalized slice of the dataframe with n steps ahead.

    Parameters
    ----------
    df : pd.DataFrame
        The dataframe to slice.
    n_steps_ahead : int
        The number of steps ahead to slice.
    i_start : int
        The index to start the slice at.

    Returns
    -------
    pd.DataFrame
        The normalized slice of the dataframe.
    """

    return (
        df.iloc[i_start + 1 : i_start + n_steps_ahead + 1] / df.iloc[i_start]
    ).reset_index(drop=True)
