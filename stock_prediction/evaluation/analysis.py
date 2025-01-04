import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def summary_analysis(
    df: pd.DataFrame,
    n_predict: int,
    predictions: np.ndarray,
    actuals: np.ndarray,
    index_start: int,
    index_end: int,
    symbol: str = "SPY",
    figsize: tuple = (15, 5),
    bins: int = 20,
    alpha: float = 0.5,
):
    df_cumprod = (1 + df).cumprod()

    # Plot some examples of predictions
    for pos in [1, n_predict // 2, n_predict - 1]:
        plt.figure(figsize=figsize)
        symbol_pos = np.where(df.columns == symbol)[0][0]
        series = df_cumprod[symbol].iloc[index_start:index_end]
        plt.plot((series * predictions[:, symbol_pos, pos]).shift(pos))
        plt.plot(series)
        plt.ylabel("Cumulative Return")
        plt.xlabel("Date")
        plt.legend([f"Prediction (n = {pos})", "Actual"])
        plt.show()

        plt.figure(figsize=figsize)
        plt.plot(predictions[:, symbol_pos, pos] - 1)
        plt.plot(actuals[:, symbol_pos, pos] - 1)
        plt.ylabel("Return at n")
        plt.xlabel("Date")
        plt.legend([f"Prediction (n = {pos})", "Actual"])
        plt.show()

    # Get the prediction errors
    df_pred_errors = pd.DataFrame(
        np.mean(np.abs(actuals - predictions) / actuals, axis=2),
        columns=df.columns,
        index=df.index[index_start:index_end],
    )

    # Show summary plots of average prediction errors around the actual series
    plt.figure(figsize=figsize)
    y = df_cumprod[symbol].iloc[index_start:index_end]
    x = y.index
    plt.errorbar(x, y, yerr=df_pred_errors[symbol].values * y, alpha=alpha)
    plt.plot(y)
    plt.ylabel(f"Price evolution for {symbol}")
    plt.legend(["Actual Series", f"MAPE band for {n_predict} days prediction"])
    plt.show()

    plt.figure(figsize=figsize)
    plt.errorbar(
        x,
        y / y.shift(1) - 1,
        yerr=np.abs(df_pred_errors[symbol].values * y),
        alpha=alpha,
    )
    plt.plot(y / y.shift(1) - 1)
    plt.ylabel(f"Returns evolution for {symbol}")
    plt.legend(["Actual Series", f"MAPE band for {n_predict} days prediction"])
    plt.show()

    # Histogram of relative mean errors
    df_pred_errors_stats = df_pred_errors.describe()

    plt.figure(figsize=figsize)
    df_pred_errors_stats.loc["50%"].hist(bins=bins)
    plt.xlabel("Symbol Median Error")
    plt.ylabel("Count")
    plt.title("Histogram of Median Percent Prediction Errors")
    plt.show()
    print(df_pred_errors_stats.loc["50%"].describe())

    # Median of median errors
    median_of_median_errors = df_pred_errors_stats.loc["50%"].describe().loc["50%"]
    # Mean of median errors
    mean_of_median_errors = df_pred_errors_stats.loc["50%"].mean()
    # Overall mean of mean errors
    mean_of_mean_errors = df_pred_errors.mean().mean()

    # Make a dataframe with the 3 errors and print
    ser_errors = pd.Series(
        {
            "Median of Median Errors": median_of_median_errors,
            "Mean of Median Errors": mean_of_median_errors,
            "Mean of Mean Errors": mean_of_mean_errors,
        }
    )
    print(ser_errors)
    return ser_errors
