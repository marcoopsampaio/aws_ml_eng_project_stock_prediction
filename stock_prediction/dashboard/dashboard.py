import dash
import pandas as pd
import plotly.graph_objs as go
from dash import dash_table, dcc, html
from dash.dependencies import Input, Output

global list_dict_symbols

# Set up the app
app = dash.Dash(__name__)
server = app.server

DEFAULT_SYMBOLS = ["SPY", "QQQ"]

# TODO: fix duplicate date
df_results = pd.read_feather("example_predictions.feather")

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

URL_BLOG_POST = "https://medium.com/@marcoopsampaio/covid-19-a-surprisingly-effective-data-driven-model-1a3bb0361d7a?sk=2460a64b45ff4b63cf666dc9274eee31"
GIT_LAB_REPO = "https://gitlab.com/marcoopsampaio/covid19"


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
                        "TODO: Description of what this dashboard is about and how the model was built",
                        html.A(
                            "here",
                            href="https://www.kaggle.com/sudalairajkumar/novel-corona-virus-2019-dataset",
                            target="_blank",
                        ),
                        ". The model used for forecasting is the double exponential model "
                        "I have presented in ",
                        html.A(
                            "this medium blog post", href=URL_BLOG_POST, target="_blank"
                        ),
                        ". The code can be found in this ",
                        html.A("gitlab repo", href=GIT_LAB_REPO, target="_blank"),
                        ".",
                    ]
                ),
            ],
            style={"width": "100%", "display": "inline-block"},
        ),
        html.Div(
            [
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
                    style={"width": "20%", "float": "left", "display": "inline-block"},
                ),
                html.Div(
                    [dcc.Graph(id="symbols-graph"), html.P("")],
                    style={"width": "80%", "display": "inline-block"},
                ),
            ],
            style={"width": "100%"},
        ),
        html.Div(
            [
                html.Table(id="forecast-table"),
                html.P(""),
            ],
            style={"width": "100%"},
        ),
    ]
)


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


# for the table
@app.callback(
    Output("forecast-table", "children"), [Input("symbols-dropdown", "value")]
)
def generate_table(selected_dropdown_values):
    df = results_filtered(selected_dropdown_values)
    df = df.round(2)
    df = df.iloc[-5:]
    df.index = [str(x) for x in df.index.date]
    df = df.T.reset_index()
    return dash_table.DataTable(
        df.to_dict("records"), [{"name": i, "id": i} for i in df.columns], id="tbl"
    )


def results_filtered(selected_dropdown_values):
    return df_results[selected_dropdown_values]


def timeline_symbols_filtered_by_keys(results_filtered):
    # Make a timeline
    trace_list = []

    xmin = None
    xmax = pd.Timestamp(0)

    i = 0
    for symbol in results_filtered.columns:
        color_index = i % (len(colors_list))
        # color = colors_list[color_index]
        color_faint = colors_list_faint[color_index]
        i += 1
        x_vals2 = results_filtered[symbol].index.values[-20:]
        trace1 = go.Scatter(
            x=x_vals2,
            y=results_filtered[symbol].values[-20:],
            mode="lines",
            name="Prediction",
            showlegend=False,
            line=dict(color=color_faint, width=2),
        )
        trace_list.append(trace1)
        x_vals = results_filtered[symbol].index.values[:-20]
        trace2 = go.Scatter(
            x=x_vals,
            y=results_filtered[symbol].values[:-20],
            mode="lines",
            name=symbol,
            line=dict(color=color_faint, width=2),
            # marker=dict(
            #     color='rgba(0, 0, 0, 0.)',
            #     line=dict(
            #         color=color,
            #         width=1
            #     ),
            #     size=1
            # )
        )
        trace_list.append(trace2)
        xmax_this = max(x_vals[-1], x_vals2[-1])
        if xmin is None:
            xmin = x_vals[0]
        xmin = min(x_vals[0], xmin)
        xmax = max(xmax_this, xmax)

    return trace_list, xmin, xmax


if __name__ == "__main__":
    # app.run_server(debug=True)
    app.run_server(debug=False, host="0.0.0.0", port=8050)
