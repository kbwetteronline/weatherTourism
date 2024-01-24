from datetime import datetime, timedelta

import openmeteo_requests
import requests_cache

import pandas as pd
import plotly.graph_objects as go

import warnings
warnings.filterwarnings('ignore')

from retry_requests import retry


from dash import Dash, dcc, html, Input, Output

cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)
today = datetime.today() - timedelta(days = 6.0)
dateformat = '%Y-%m-%d'

TODAY = today.strftime(dateformat)
types = ["temperature_2m_max", "temperature_2m_mean", "temperature_2m_min", "precipitation_sum"]
types_as_String = ["Maximum Temperature", "Mean Temperature", "Minimum Temperature", "Precipitation"]
unit_of_type = ["°C", "°C", "°C", "mm"]

url = "https://archive-api.open-meteo.com/v1/archive"
params = {
	"latitude": 50.935173,
	"longitude": 6.953101,
	"start_date": "2000-01-01",
	"end_date": TODAY,
	"daily": types,
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
for index, type in enumerate(types):
    daily_data[type] = daily.Variables(index).ValuesAsNumpy()

df = pd.DataFrame(data = daily_data)
df = df.round(2)
print(df)

jahres_dfs = {}

# Werte werden in ein Dictionary als Dataframes eingefügt; für jedes Jahr ein Dataframe
for jahr, group in df.groupby(df['date'].dt.year):
    
    # Kopie erstellen um SettingWithCopyWarning zu umgehen
    jahres_df = group.copy()  
    
    # Schalttag herausfiltern
    jahres_df = jahres_df[~((jahres_df['date'].dt.month == 2) & (jahres_df['date'].dt.day == 29))]

    # Das Datum wird durch den Tag des Jahres ersetzt
    jahres_df['date'] = jahres_df['date'].dt.dayofyear

    jahres_dfs[jahr] = jahres_df
    

durschnitts_df = pd.DataFrame(columns=['date'])

for type in types:

    temp_df = pd.DataFrame(columns=['date', type])

    # Durchschnitts Dataframe
    for day in range(1, 366):
        value = 0

        # durch alle Jahres Dataframes iterieren
        for year, year_df in jahres_dfs.items():

            # Check, dass der betrachtete Wert nicht leer ist
            if (len(year_df[type].loc[year_df['date'] == day].values) != 0):

                # Betrachtete Werte werden addiert
                value += year_df[type].loc[year_df['date'] == day].values[0]
            else:
                continue

        # Um den Durchschnittswert zu erhalten wird durch die Anzahl der Jahre geteilt und auf 2 Nachkommastellen gerundet
        value = round(value / len(jahres_dfs), 2)


        # Tag für Tag werden die Daten angefügt
        temp_df = temp_df.append({'date': day, type: value}, ignore_index=True)

        
    durschnitts_df = pd.merge(durschnitts_df, temp_df, on='date', how='outer')

print(durschnitts_df.head())

app = Dash(__name__)

app.layout = html.Div([
    html.H1('Historical Temperaturedisplay - Cologne', style={'textAlign': 'center'}),

    html.Div(children=[
        html.Button('All', id='cumulated', n_clicks=0),
    ]),

    html.Div([
        html.Label('Art: '),
        dcc.Dropdown(
            id='art',
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


    dcc.Graph(id='my_fig', config={
        'displayModeBar': False}),

])


@app.callback(
    Output('my_fig', 'figure'),
    Output('cumulated', 'children'),
    Input('art', 'value'),
    Input('cumulated', 'n_clicks'),

)
def update_output(art, n_clicks_cumulated):

    traces = []
    for trace_name in jahres_dfs:
        print(trace_name)
        traces.append(go.Scatter(
            x=jahres_dfs[trace_name]['date'],
            y=jahres_dfs[trace_name][art],
            mode='lines',
            hovertemplate=('<b>Year: {} | '.format(trace_name) + types_as_String[types.index(art)] + ': %{y} ' + unit_of_type[types.index(art)] + '</b><extra></extra>'),
            name=trace_name
        ))

    durschnitts_traces = []
    durschnitts_traces.append(go.Scatter(
        x=durschnitts_df['date'],
        y=durschnitts_df[art],
        mode='lines',
        hovertemplate=('<b>Day: %{x} <br>' + types_as_String[types.index(art)] + ': %{y} ' + unit_of_type[types.index(art)] + '</b><extra></extra>'),
        name="Summarized Average of all Years"
    ))

    layout = go.Layout(xaxis=dict(title='Day of the Year'), yaxis=dict(title=types_as_String[types.index(art)] + ' in ' + unit_of_type[types.index(art)]))
    
    if n_clicks_cumulated % 2 == 1:
        cumulated_text = 'All Years'

        fig = go.Figure(data=traces, layout=layout)
    else:
        cumulated_text = 'Summarized'
        
        fig = go.Figure(data=durschnitts_traces, layout=layout)
        

    fig.update_layout(showlegend=True,
                      legend=dict(groupclick="toggleitem", orientation="h"),
                      xaxis=dict(rangeslider=dict(visible=True)),
                      height=700, hovermode='x unified')
    fig.update_xaxes(rangeslider_thickness=0.1)

    return fig, cumulated_text


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050)
