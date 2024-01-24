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
types = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum"]

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

        # Um den Durchschnittswert zu erhalten wird durch die Anzahl der Jahre geteilt
        value = value / len(jahres_dfs)


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
                {'label': 'Minimum Temperature', 'value': 'temperature_2m_min'},
                {'label': 'Durchschitts Temperature', 'value': 'temperature_2m_mean'},
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


    html.Div(children=[
        dcc.RangeSlider(id='rangeslider',
                        min=min(df['date']),
                        max=max(df['date']),
                        value=[min(df['date']), max(df['date'])],
                        step=1,
                        # display the date in the marks
                        updatemode='drag')
    ]),

])


@app.callback(
    Output('my_fig', 'figure'),
    Output('cumulated', 'children'),
    Input('art', 'value'),
    Input('cumulated', 'n_clicks'),   
    Input('rangeslider', 'value')

)
def update_output(art, n_clicks_cumulated, rangesl_value):
    start_timestamp = rangesl_value[0]
    end_timestamp = rangesl_value[1]

    df_filtered = df

    # df_filtered = df[(df['date'] >= start_timestamp) & (df['date'] <= end_timestamp)]

    # df_filtered['date'] = pd.to_datetime(df_filtered['date'], unit='s')

    # print('filtered')
    # print(df_filtered)


    """for column in df_filtered.loc[:, df_filtered.columns != 'date']:
        df_filtered [column] = df_filtered[column] * (one_time / df.iloc[0][column])"""

    traces = []
    for trace_name in jahres_dfs:
        traces.append(go.Scatter(
            x=df_filtered['date'],
            y=jahres_dfs[trace_name][art],
            mode='lines',
            name=trace_name
        ))

    durschnitts_traces = []
    for trace_name in jahres_dfs:
        durschnitts_traces.append(go.Scatter(
        x=df_filtered['date'],
        y=durschnitts_df[art],
        mode='lines',
        name=trace_name
    ))

    layout = go.Layout(xaxis=dict(title='Month'), yaxis=dict(title='Einheit'))
    
    if n_clicks_cumulated % 2 == 1:
        cumulated_text = 'All'

        fig = go.Figure(data=traces, layout=layout)
    else:
        cumulated_text = 'Cumulated'
        
        fig = go.Figure(data=durschnitts_traces, layout=layout)

    fig.update_layout(showlegend=True,
                      legend=dict(groupclick="toggleitem", orientation="h"),
                      xaxis=dict(rangeslider=dict(visible=True)),
                      height=700)
    fig.update_xaxes(title="Month",rangeslider_thickness=0.1)

    return fig, cumulated_text


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050)
