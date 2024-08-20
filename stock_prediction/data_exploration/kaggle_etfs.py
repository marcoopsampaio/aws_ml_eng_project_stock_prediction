import pandas as pd

from stock_prediction.commons import REPO_ROOT

PRICE_DATA_KEY = "price_date"
ETFS_DIR_PATH = REPO_ROOT / "data/raw_data/securities/etfs_and_mutual_funds_kaggle/"


def load_etfs_data():
    """
    Loads ETF prices and ETFs data available in a Kaggle dataset.
    at https://www.kaggle.com/datasets/stefanoleone992/mutual-funds-and-etfs

    Returns
    -------
    df_etf_prices : pd.DataFrame
        ETF prices data
    df_etfs : pd.DataFrame
        ETFs data
    """
    print("Loading ETFs data ...")

    if not ETFS_DIR_PATH.exists():
        raise FileNotFoundError(
            f"Directory not found: {ETFS_DIR_PATH}. \n"
            "Please download the data from Kaggle at "
            "https://www.kaggle.com/datasets/stefanoleone992/mutual-funds-and-etfs."
        )

    df_etf_prices = pd.read_csv(ETFS_DIR_PATH.joinpath("ETF prices.csv"))
    df_etf_prices[PRICE_DATA_KEY] = df_etf_prices[PRICE_DATA_KEY].apply(
        lambda x: pd.Timestamp(x)
    )
    df_etfs = pd.read_csv(ETFS_DIR_PATH.joinpath("ETFs.csv"))
    return df_etf_prices, df_etfs
