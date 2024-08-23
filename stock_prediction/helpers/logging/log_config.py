import logging

STOCK_LOGGER_NAME = "stock_logger"


def get_logger() -> logging.Logger:
    """
    Returns the logger instance if it exists, otherwise creates a new one.

    Returns
    -------
    logging.Logger
        The logger instance.
    """
    logger = logging.getLogger(STOCK_LOGGER_NAME)

    if not logger.hasHandlers():
        setup_logging()

    return logger


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Sets up the logging configuration for the stock_prediction package.

    Parameters
    ----------
    log_level : str
        The level to set the logger to.

    Returns
    -------
    logging.Logger
        The logger instance.
    """
    logger = logging.getLogger(STOCK_LOGGER_NAME)
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger
