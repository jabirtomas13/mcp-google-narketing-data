import streamlit as st
import openai
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import altair as alt

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Agente Analítico", layout="wide")
st.title("🤖 Agente Analítico con LLM + APIs de Google")

# --- CLAVES Y CREDENCIALES ---
openai.api_key = st.secrets["OPENAI_API_KEY"]
SERVICE_ACCOUNT_INFO = st.secrets["GOOGLE_SERVICE_ACCOUNT"]

# --- AUTENTICACIÓN GOOGLE ---
creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
)

# --- FUNCIÓN PARA CONSULTAR SEARCH CONSOLE ---
def get_search_console_ctr(site_url, start_date, end_date, query_filter=None):
    service = build('searchconsole', 'v1', credentials=creds)
    request = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query'],
        'rowLimit': 20,
    }
    if query_filter:
        request['dimensionFilterGroups'] = [{
            'filters': [{
                'dimension': 'query',
                'operator': 'contains',
                'expression': query_filter
            }]
        }]
    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
    rows = response.get('rows', [])
    df = pd.DataFrame(rows)
    return df

# --- DEFINICIÓN DE FUNCIONES PARA LLM ---
functions = [
  {
    "name": "get_search_console_ctr",
    "description": "Obtiene el CTR de una propiedad en Search Console",
    "parameters": {
        "type": "object",
        "properties": {
            "site_url": {"type": "string"},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "query_filter": {"type": "string"}
        },
        "required": ["site_url", "start_date", "end_date"]
    }
  }
]

# --- ENTRADA DEL USUARIO ---
query = st.text_input("Haz una pregunta sobre tus datos de Search Console")

# --- PARÁMETROS PREDEFINIDOS PARA TESTING ---
definir_rango = st.checkbox("Usar últimos 30 días automáticamente", value=True)
if definir_rango:
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=30)
    start_date, end_date = str(start_date), str(end_date)
else:
    start_date = st.date_input("Fecha de inicio").isoformat()
    end_date = st.date_input("Fecha de fin").isoformat()

site_url = st.text_input("URL de la propiedad de Search Console", "https://tusitio.com")

# --- SELECCIÓN DE VISUALIZACIÓN ---
tipo_grafico = st.selectbox("Tipo de visualización", ["Tabla", "Gráfico de barras", "Línea de tiempo"])

# --- PROCESO PRINCIPAL ---
if query:
    with st.spinner("Consultando modelo..."):
        response = openai.ChatCompletion.create(
            model="gpt-4-0613",
            messages=[{"role": "user", "content": query}],
            functions=functions,
            function_call="auto"
        )

        function_call = response.choices[0].message.get("function_call")

        if function_call:
            args = eval(function_call["arguments"])
            df_result = get_search_console_ctr(
                site_url=args.get("site_url", site_url),
                start_date=args.get("start_date", start_date),
                end_date=args.get("end_date", end_date),
                query_filter=args.get("query_filter")
            )

            st.success("Consulta realizada correctamente")
            if tipo_grafico == "Tabla":
                st.dataframe(df_result)
            elif tipo_grafico == "Gráfico de barras":
                if 'clicks' in df_result.columns and 'keys' in df_result.columns:
                    chart = alt.Chart(df_result).mark_bar().encode(
                        x=alt.X('keys:N', title='Consulta'),
                        y=alt.Y('clicks:Q', title='Clics'),
                        tooltip=['keys', 'clicks']
                    ).properties(title="Clics por consulta")
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.warning("No se encontraron columnas adecuadas para el gráfico de barras.")
            elif tipo_grafico == "Línea de tiempo":
                if 'position' in df_result.columns and 'keys' in df_result.columns:
                    chart = alt.Chart(df_result).mark_line().encode(
                        x=alt.X('keys:N', title='Consulta'),
                        y=alt.Y('position:Q', title='Posición media'),
                        tooltip=['keys', 'position']
                    ).properties(title="Posición media por consulta")
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.warning("No se encontraron columnas adecuadas para la línea de tiempo.")
        else:
            st.warning("El modelo no pudo identificar una función para esta pregunta.")
