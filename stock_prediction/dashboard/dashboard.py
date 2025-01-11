import io

import boto3
import dash
import pandas as pd
import plotly.graph_objs as go
from dash import dash_table, dcc, html
from dash.dependencies import Input, Output

from stock_prediction.deployment.utils import BUCKET_NAME, PREDICTIONS_FILE_NAME

# AWS S3 Configuration
REGION_NAME = "us-east-1"
# Initialize S3 client
s3_client = boto3.client("s3", region_name=REGION_NAME)

global list_dict_symbols

# Set up the app
app = dash.Dash(__name__)
server = app.server

DEFAULT_SYMBOLS = ["SPY", "QQQ"]


# Load initial data
def fetch_predictions_from_s3():
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=PREDICTIONS_FILE_NAME)
        df = pd.read_feather(io.BytesIO(response["Body"].read()))
        return df
    except Exception as e:
        print(f"Error fetching data from S3: {e}")
        return pd.DataFrame()


df_results = fetch_predictions_from_s3()

global colors_list
global colors_list_faint

colors_list = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]

colors_list_faint = [
    "#96c9ed",
    "#ffc08a",
    "#8bdf8b",
    "#ea8f8f",
    "#c5addb",
    "#c8a098",
    "#efb3dd",
    "#bdbdbd",
    "#e8e87d",
    "#71e3ef",
]

GIT_REPO = "https://github.com/marcoopsampaio/aws_ml_eng_project_stock_prediction"


list_dict_symbols = [
    {"value": symbol, "label": symbol} for symbol in df_results.columns
]


app.layout = html.Div(
    [
        # Title section
        html.Div(
            [
                html.H1("ETF price forecaster"),
                html.H4(
                    [
                        html.A(
                            "by Marco O. P. Sampaio",
                            href="https://www.linkedin.com/in/marcoopsampaio/",
                        )
                    ],
                    style={"color": "gray"},
                ),
            ],
            style={"width": "100%"},
        ),
        # General Information
        html.Div(
            [
                html.P(
                    [
                        "This is a simple dashboard to forecast the future price of selected ETFs. ",
                        "A simple LightGBM model per available ETF was trained using data from ",
                        html.A(
                            "Yahoo Finance",
                            href="https://finance.yahoo.com/",
                            target="_blank",
                        ),
                        "The code can be found in this ",
                        html.A("gitlab repo", href=GIT_REPO, target="_blank"),
                        ".",
                    ]
                ),
            ],
            style={"width": "100%", "display": "inline-block"},
        ),
        html.Div(
            [
                html.H6("Choose Symbols:"),
                dcc.Dropdown(
                    id="symbols-dropdown",
                    options=list_dict_symbols,
                    multi=True,
                    value=DEFAULT_SYMBOLS,
                ),
            ],
            style={"width": "100%", "float": "left", "display": "inline-block"},
        ),
        html.Div(
            [
                html.Div(
                    [dcc.Graph(id="symbols-graph"), html.P("")],
                    style={"width": "50%", "display": "inline-block"},
                ),
                html.Div(
                    [dcc.Graph(id="symbols-graph2"), html.P("")],
                    style={"width": "50%", "display": "inline-block"},
                ),
            ],
            style={"width": "100%"},
        ),
        html.Div(
            [
                html.Table(id="forecast-table"),
                html.P(""),
            ],
            style={"width": "100%", "overflowX": "auto"},
        ),
        # Interval component for periodic updates
        dcc.Interval(
            id="update-interval",
            interval=3600 * 1000,  # Update every hour
            n_intervals=0,
        ),
    ]
)


# Callback to refresh data from S3
@app.callback(
    Output("symbols-dropdown", "options"),
    Input("update-interval", "n_intervals"),
)
def refresh_data(n_intervals):
    global df_results, list_dict_symbols
    df_results = fetch_predictions_from_s3()
    list_dict_symbols = [
        {"value": symbol, "label": symbol} for symbol in df_results.columns
    ]
    return list_dict_symbols


# Callback to update the left graph
@app.callback(Output("symbols-graph", "figure"), [Input("symbols-dropdown", "value")])
def update_graph(selected_dropdown_value):

    df = results_filtered(selected_dropdown_value)

    data, xmin, xmax = timeline_symbols_filtered_by_keys(df)

    # Edit the layout
    layout = dict(
        title="Price evolution and forecast",
        xaxis=dict(range=[xmin, xmax]),
        yaxis=dict(title="Value (USD)"),
    )
    figure = dict(data=data, layout=layout)
    return figure


# Callback to update the right graph
@app.callback(Output("symbols-graph2", "figure"), [Input("symbols-dropdown", "value")])
def update_graph2(selected_dropdown_value):

    df = results_filtered(selected_dropdown_value)

    data, xmin, xmax = timeline_symbols_filtered_by_keys(df, n_xzoom=40)

    # Edit the layout
    layout = dict(
        title="Zoom",
        xaxis=dict(range=[xmin, xmax]),
        yaxis=dict(title="Value (USD)"),
    )
    figure = dict(data=data, layout=layout)
    return figure


# Generate and update the table
@app.callback(
    Output("forecast-table", "children"), [Input("symbols-dropdown", "value")]
)
def generate_table(selected_dropdown_values):
    df = results_filtered(selected_dropdown_values)
    df = df.round(2)
    df = df.iloc[-20:]
    df.index = [str(x) for x in df.index.date]
    df = df.T.reset_index()
    return dash_table.DataTable(
        df.to_dict("records"), [{"name": i, "id": i} for i in df.columns], id="tbl"
    )


def results_filtered(selected_dropdown_values):
    return df_results[selected_dropdown_values]


def timeline_symbols_filtered_by_keys(results_filtered, n_xzoom=None):
    # Make a timeline
    trace_list = []

    xmin = None
    xmax = pd.Timestamp(0)

    i = 0
    for symbol in results_filtered.columns:
        # Choose a color
        color_index = i % (len(colors_list))
        color_faint = colors_list_faint[color_index]
        # Plot prediction
        i += 1
        x_vals2 = results_filtered[symbol].index.values[-20:]
        trace1 = go.Scatter(
            x=x_vals2,
            y=results_filtered[symbol].values[-20:],
            mode="lines",
            name="Prediction",
            showlegend=False,
            line=dict(color=color_faint, width=2, dash="dash"),
        )
        trace_list.append(trace1)
        # Plot history
        if n_xzoom:
            x_vals = results_filtered[symbol].index.values[-n_xzoom:-20]
            y_vals = results_filtered[symbol].values[-n_xzoom:-20]
        else:
            x_vals = results_filtered[symbol].index.values[:-20]
            y_vals = results_filtered[symbol].values[:-20]
        trace2 = go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            name=symbol,
            line=dict(color=color_faint, width=2),
        )
        trace_list.append(trace2)
        xmax_this = max(x_vals[-1], x_vals2[-1])
        if xmin is None:
            xmin = x_vals[0]
        xmin = min(x_vals[0], xmin)
        xmax = max(xmax_this, xmax)

    return trace_list, xmin, xmax


if __name__ == "__main__":
    app.run_server(debug=False, host="0.0.0.0", port=8050)
