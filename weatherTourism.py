from dash import Dash, dcc, html, Input, Output
from datetime import datetime, timedelta

import openmeteo_requests
import requests_cache
from retry_requests import retry

import pandas as pd
import plotly.graph_objects as go

import warnings
warnings.filterwarnings('ignore')

cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)
today = datetime.today() - timedelta(days = 6.0)
dateformat = '%Y-%m-%d'

TODAY = today.strftime(dateformat)
DAYS_IN_YEAR = 365
data_types = ["temperature_2m_max", "temperature_2m_mean", "temperature_2m_min", "precipitation_sum"]
data_types_as_String = ["Maximum Temperature", "Mean Temperature", "Minimum Temperature", "Precipitation"]
unit_of_data_type = ["°C", "°C", "°C", "mm"]

url = "https://archive-api.open-meteo.com/v1/archive"
params = {
	"latitude": 50.935173,
	"longitude": 6.953101,
	"start_date": "2000-01-01",
	"end_date": TODAY,
	"daily": data_types,
	"timezone": "Europe/London"
}
# ApiRequest
responses = openmeteo.weather_api(url, params=params)
response = responses[0]
daily = response.Daily()

# Datumszeile aus dem ApiRequest in das Dataframe übertragen
daily_data = {"date": pd.date_range(
	start = pd.to_datetime(daily.Time(), unit = "s"),
	end = pd.to_datetime(daily.TimeEnd(), unit = "s"),
	freq = pd.Timedelta(seconds = daily.Interval()),
	inclusive = "left"
)}

# Alle anderen Zeilen in das Dataframe übertragen
for index, data_type in enumerate(data_types):
    daily_data[data_type] = daily.Variables(index).ValuesAsNumpy()

weather_data_df = pd.DataFrame(data = daily_data).round(2)

year_dfs = {}

# Werte werden in ein Dictionary als Dataframes eingefügt; für jedes Jahr ein Dataframe
for year, group in weather_data_df.groupby(weather_data_df['date'].dt.year):
    
    # Kopie erstellen um SettingWithCopyWarning zu umgehen
    year_df = group.copy()  
    
    # Schalttag herausfiltern
    year_df = year_df[~((year_df['date'].dt.month == 2) & (year_df['date'].dt.day == 29))]

    # Das Datum wird durch den Tag des Jahres ersetzt
    year_df['date'] = year_df['date'].dt.dayofyear

    year_dfs[year] = year_df
    

mean_df = pd.DataFrame(columns=['date'])

for data_type in data_types:

    temp_df = pd.DataFrame(columns=['date', data_type])

    # Durchschnitts Dataframe
    for day in range(1, DAYS_IN_YEAR + 1):
        value = 0

        # durch alle Jahres Dataframes iterieren
        for year, year_df in year_dfs.items():

            # Check, dass der betrachtete Wert nicht leer ist
            if (len(year_df[data_type].loc[year_df['date'] == day].values) != 0):

                # Betrachtete Werte werden addiert
                value += year_df[data_type].loc[year_df['date'] == day].values[0]
            else:
                continue

        # Um den Durchschnittswert zu erhalten wird durch die Anzahl der Jahre geteilt 
        # und auf 2 Nachkommastellen gerundet
        value = round(value / len(year_dfs), 2)


        # Tag für Tag werden die Daten angefügt
        temp_df = temp_df.append({'date': day, data_type: value}, ignore_index=True)

    # Nachdem alle Werte für einen Tag berechnet wurden, wird das temporäre DataFrame 
    # mit dem Haupt-DataFrame zusammengeführt
    mean_df = pd.merge(mean_df, temp_df, on='date', how='outer')

# Initialisierung der Dash-Anwendung
app = Dash(__name__)

# Layout der Dash-Anwendung definieren
app.layout = html.Div([
    # Überschrift der Anwendung
    html.H1('Historical Temperaturedisplay - Cologne', style={'textAlign': 'center'}),

    # Button um zwischen den Ansichten zu wechseln
    html.Div(children=[
        html.Button('All', id='sumarized', n_clicks=0),
    ]),

    # Dropdown-Menü um die Art der angezeigten Daten auszuwählen
    html.Div([
        html.Label('Art: '),
        dcc.Dropdown(
            id='data_type_selector',
            options=[
                {'label': 'Maximum Temperature', 'value': 'temperature_2m_max'},
                {'label': 'Mean Temperature', 'value': 'temperature_2m_mean'},
                {'label': 'Minimum Temperature', 'value': 'temperature_2m_min'},
                {'label': 'Precipitation', 'value': 'precipitation_sum'},
            ],
            value="temperature_2m_mean",
            clearable=False,
            multi=False,
            style={
                'width': '55%'}
        ),
    ]),

    # Graph der die Daten anzeigt
    dcc.Graph(id='my_fig', config={
        'displayModeBar': False}),

])

# Callbacks um die Daten zu aktualisieren
@app.callback(
    Output('my_fig', 'figure'),
    Output('sumarized', 'children'),
    Input('data_type_selector', 'value'),
    Input('cumulsumarizedated', 'n_clicks'),

)
def update_output(data_type, n_clicks_cumulated):
    # Daten für den Graphen werden aus dem Dataframe gezogen
    traces = []
    for trace_name in year_dfs:
        print(trace_name)
        traces.append(go.Scatter(
            x=year_dfs[trace_name]['date'],
            y=year_dfs[trace_name][data_type],
            mode='lines',
            hovertemplate=('<b>Year: {} | '.format(trace_name) + 
                           data_types_as_String[data_types.index(data_type)] + 
                           ': %{y} ' + unit_of_data_type[data_types.index(data_type)] + 
                           '</b><extra></extra>'),
            name=trace_name
        ))
    
    # Durchschnittsdaten werden aus dem Dataframe gezogen 
    mean_traces = []
    mean_traces.append(go.Scatter(
        x=mean_df['date'],
        y=mean_df[data_type],
        mode='lines',
        hovertemplate=(data_types_as_String[data_types.index(data_type)] + 
                       ': %{y} ' + unit_of_data_type[data_types.index(data_type)] + 
                       '</b><extra></extra>'),
        name="Summarized Average of all Years"
    ))

    # Layout des Graphen wird definiert
    layout = go.Layout(
        xaxis=dict(title='Day of the Year'), 
        yaxis=dict(title=data_types_as_String[data_types.index(data_type)] + 
                   ' in ' + 
                   unit_of_data_type[data_types.index(data_type)])
        )
    
    # Wenn der Button geklickt wird, wird zwischen den Ansichten gewechselt
    if n_clicks_cumulated % 2 == 1:
        cumulated_text = 'All Years'
        fig = go.Figure(data=traces, layout=layout)
    else:
        cumulated_text = 'Summarized'
        fig = go.Figure(data=mean_traces, layout=layout)
    
    # Layout des Graphen wird weiter definiert
    fig.update_xaxes(rangeslider_thickness=0.1)
    fig.update_layout(showlegend=True,
                      legend=dict(groupclick="toggleitem", orientation="h"),
                      xaxis=dict(rangeslider=dict(visible=True)),
                      height=700, hovermode='x unified')

    return fig, cumulated_text

# Starten der Dash-Anwendung
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050)
