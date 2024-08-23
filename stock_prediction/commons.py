from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

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
