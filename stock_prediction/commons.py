from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

DEFAULT_SYMBOLS_CSV_PATH = REPO_ROOT / "data/data_exploration/top_etfs.csv"
DEFAULT_DATA_EXTRACTION_OUTPUT_PATH = REPO_ROOT / "data/etl/symbols_returns.csv"

PANDAS_STYLE_VERTICAL_COLNAMES = [
    dict(selector="th", props=[("max-width", "80px")]),
    dict(
        selector="th.col_heading",
        props=[
            ("writing-mode", "vertical-rl"),
            ("transform", "rotateZ(-180deg)"),
        ],
    ),
]
