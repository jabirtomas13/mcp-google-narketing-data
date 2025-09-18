import streamlit as st
import openai
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import altair as alt
import json

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Agente Analítico", layout="wide")
st.title("🤖 Agente Analítico con LLM + APIs de Google")

# --- SIDEBAR PARA CONFIGURACIÓN ---
with st.sidebar:
    st.header("🔑 Configuración de Credenciales")
    
    # OpenAI API Key
    st.subheader("OpenAI")
    openai_key = st.text_input(
        "OpenAI API Key", 
        type="password", 
        placeholder="sk-...",
        help="Ingresa tu clave de API de OpenAI"
    )
    
    if openai_key:
        openai.api_key = openai_key
        st.success("✅ Clave de OpenAI configurada")
    else:
        st.warning("⚠️ Falta la clave de OpenAI")
    
    st.divider()
    
    # Google Service Account
    st.subheader("Google Service Account")
    
    # Opción 1: JSON completo
    st.write("**Opción 1: Pegar JSON completo**")
    json_credentials = st.text_area(
        "Credenciales JSON",
        placeholder='{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}',
        height=150,
        help="Pega aquí el contenido completo del archivo JSON de tu Service Account"
    )
    
    # Opción 2: Campos individuales
    st.write("**Opción 2: Campos individuales**")
    with st.expander("Introducir campos manualmente"):
        project_id = st.text_input("Project ID")
        private_key_id = st.text_input("Private Key ID")
        private_key = st.text_area(
            "Private Key", 
            placeholder="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
            help="Incluye las líneas BEGIN y END PRIVATE KEY"
        )
        client_email = st.text_input("Client Email", placeholder="...@....iam.gserviceaccount.com")
        client_id = st.text_input("Client ID")
    
    # Validar credenciales de Google
    google_creds = None
    if json_credentials.strip():
        with st.spinner("🤖 Analizando con IA..."):
            service_account_info = json.loads(json_credentials)
            google_creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )
            st.success("✅ Credenciales de Google (JSON) configuradas")
        except json.JSONDecodeError:
            st.error("❌ JSON inválido")
        except Exception as e:
            st.error(f"❌ Error en credenciales: {str(e)}")
    
    elif all([project_id, private_key_id, private_key, client_email, client_id]):
        try:
            service_account_info = {
                "type": "service_account",
                "project_id": project_id,
                "private_key_id": private_key_id,
                "private_key": private_key.replace('\\n', '\n'),
                "client_email": client_email,
                "client_id": client_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}"
            }
            google_creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )
            st.success("✅ Credenciales de Google (manual) configuradas")
        except Exception as e:
            st.error(f"❌ Error en credenciales: {str(e)}")
    else:
        st.warning("⚠️ Faltan credenciales de Google")

# --- VERIFICAR QUE TODO ESTÉ CONFIGURADO ---
if not openai_key:
    st.error("❌ Por favor, configura tu clave de OpenAI en la barra lateral")
    st.stop()

if not google_creds:
    st.error("❌ Por favor, configura tus credenciales de Google Service Account en la barra lateral")
    st.info("""
    ### 📝 Cómo obtener las credenciales de Google:
    1. Ve a [Google Cloud Console](https://console.cloud.google.com)
    2. Crea un nuevo proyecto o selecciona uno existente
    3. Habilita la API de Search Console
    4. Ve a "IAM & Admin" > "Service Accounts"
    5. Crea un nuevo Service Account
    6. Genera y descarga la clave JSON
    7. En Search Console, agrega el email del Service Account como usuario
    """)
    st.stop()

# --- FUNCIÓN PARA CONSULTAR SEARCH CONSOLE ---
def get_search_console_ctr(site_url, start_date, end_date, query_filter=None):
    try:
        service = build('searchconsole', 'v1', credentials=google_creds)
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query'],
            'rowLimit': 50,
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
        
        if not rows:
            return pd.DataFrame()
        
        # Procesar los datos
        data = []
        for row in rows:
            data.append({
                'query': row.get('keys', [''])[0] if row.get('keys') else '',
                'clicks': row.get('clicks', 0),
                'impressions': row.get('impressions', 0),
                'ctr': round(row.get('ctr', 0) * 100, 2),  # Convertir a porcentaje
                'position': round(row.get('position', 0), 1)
            })
        
        df = pd.DataFrame(data)
        return df
        
    except Exception as e:
        st.error(f"Error al consultar Search Console: {str(e)}")
        return pd.DataFrame()

# --- FUNCIÓN PARA OBTENER PROPIEDADES ---
def get_user_sites():
    try:
        service = build('searchconsole', 'v1', credentials=google_creds)
        response = service.sites().list().execute()
        sites = response.get('siteEntry', [])
        return [site['siteUrl'] for site in sites if site.get('permissionLevel') in ['siteOwner', 'siteFullUser']]
    except Exception as e:
        st.error(f"Error al obtener propiedades: {str(e)}")
        return []

# --- DEFINICIÓN DE FUNCIONES PARA LLM ---
functions = [
    {
        "name": "get_search_console_ctr",
        "description": "Obtiene datos de CTR, clics, impresiones y posición de una propiedad en Search Console",
        "parameters": {
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "description": "URL de la propiedad en Search Console"
                },
                "start_date": {
                    "type": "string",
                    "description": "Fecha de inicio en formato YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha de fin en formato YYYY-MM-DD"
                },
                "query_filter": {
                    "type": "string",
                    "description": "Filtro opcional para las consultas de búsqueda (busca consultas que contengan este texto)"
                }
            },
            "required": ["site_url", "start_date", "end_date"]
        }
    }
]

# --- INTERFAZ PRINCIPAL ---
st.header("🔍 Análisis de Search Console")

# Obtener propiedades del usuario
user_sites = get_user_sites()

col1, col2 = st.columns([2, 1])

with col1:
    if user_sites:
        site_url = st.selectbox("Selecciona una propiedad:", user_sites)
    else:
        site_url = st.text_input("URL de la propiedad:", placeholder="https://example.com/")

with col2:
    # Botón para refrescar propiedades
    if st.button("🔄 Actualizar propiedades"):
        st.rerun()

# --- CONFIGURACIÓN DE FECHAS ---
col3, col4, col5 = st.columns([1, 1, 1])

with col3:
    periodo_predefinido = st.selectbox(
        "Período:", 
        ["Personalizado", "Últimos 7 días", "Últimos 30 días", "Últimos 90 días"]
    )

if periodo_predefinido != "Personalizado":
    end_date = datetime.today().date()
    days_map = {"Últimos 7 días": 7, "Últimos 30 días": 30, "Últimos 90 días": 90}
    start_date = end_date - timedelta(days=days_map[periodo_predefinido])
    start_date, end_date = str(start_date), str(end_date)
    
    with col4:
        st.info(f"Del {start_date}")
    with col5:
        st.info(f"Al {end_date}")
else:
    with col4:
        start_date = st.date_input("Fecha de inicio").isoformat()
    with col5:
        end_date = st.date_input("Fecha de fin").isoformat()

# --- CONSULTA PRINCIPAL ---
st.subheader("💬 Haz tu consulta")

# Ejemplos de preguntas
with st.expander("💡 Ejemplos de preguntas"):
    st.markdown("""
    - "¿Cuáles son las 10 consultas con mayor CTR?"
    - "Muéstrame las consultas que contienen 'python'"
    - "¿Cuál es la posición promedio de mis consultas principales?"
    - "¿Qué consultas tienen más de 100 clics?"
    - "Muéstrame las consultas con CTR menor al 2%"
    - "¿Cuáles son las consultas con mejor posición?"
    """)

query = st.text_area(
    "Tu pregunta:",
    placeholder="Ejemplo: ¿Cuáles son mis 10 mejores consultas por CTR?",
    height=80
)

# --- SELECCIÓN DE VISUALIZACIÓN ---
col6, col7 = st.columns(2)
with col6:
    tipo_grafico = st.selectbox("Visualización:", ["Tabla", "Gráfico de barras", "Línea - Posición", "Línea - CTR"])
with col7:
    max_results = st.slider("Máximo resultados:", 10, 100, 20)

# --- BOTONES DE ACCIÓN ---
col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])

with col_btn1:
    analyze_button = st.button("🤖 Analizar con IA", type="primary")

with col_btn2:
    direct_query = st.button("📊 Consulta directa")

with col_btn3:
    if st.button("🔄 Consulta de prueba"):
        query = "¿Cuáles son las 10 consultas con mayor CTR?"
        st.rerun()
if (analyze_button or direct_query) and query and query.strip() and site_url:
    # Consulta directa sin IA
    if direct_query:
        with st.spinner("📊 Obteniendo datos directamente..."):
            df_result = get_search_console_ctr(
                site_url=site_url,
                start_date=start_date,
                end_date=end_date,
                query_filter=None  # Sin filtro para consulta directa
            )
            
            if df_result.empty:
                st.warning("⚠️ No se encontraron datos para los criterios especificados")
            else:
                st.success(f"✅ Datos obtenidos: {len(df_result)} consultas")
                
                # Mostrar métricas y visualización (reutilizar código existente)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📊 Total Consultas", len(df_result))
                with col2:
                    st.metric("👆 Total Clics", f"{int(df_result['clicks'].sum()):,}")
                with col3:
                    st.metric("👀 Total Impresiones", f"{int(df_result['impressions'].sum()):,}")
                with col4:
                    avg_ctr = df_result['ctr'].mean()
                    st.metric("📈 CTR Promedio", f"{avg_ctr:.2f}%")
                
                # Respuesta simple para la consulta directa
                if "mayor CTR" in query.lower() or "mejor CTR" in query.lower():
                    top_ctr = df_result.nlargest(10, 'ctr')
                    st.subheader("🏆 Top 10 consultas con mayor CTR:")
                    st.dataframe(top_ctr[['query', 'ctr', 'clicks', 'position']], use_container_width=True)
                
                elif "más clics" in query.lower() or "mayor tráfico" in query.lower():
                    top_clicks = df_result.nlargest(10, 'clicks')
                    st.subheader("🚀 Top 10 consultas con más clics:")
                    st.dataframe(top_clicks[['query', 'clicks', 'ctr', 'position']], use_container_width=True)
                
                elif "mejor posición" in query.lower() or "posición" in query.lower():
                    top_position = df_result.nsmallest(10, 'position')
                    st.subheader("📈 Top 10 consultas con mejor posición:")
                    st.dataframe(top_position[['query', 'position', 'clicks', 'ctr']], use_container_width=True)
                
                else:
                    # Mostrar datos generales ordenados por clics
                    df_display = df_result.head(max_results)
                    st.subheader("📈 Resultados generales:")
                    st.dataframe(df_display, use_container_width=True)
    
    # Análisis con IA
    elif analyze_button:
        try:
            try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            
            # Crear un prompt más específico que incluya el contexto
            enhanced_prompt = f"""
            Tengo una propiedad de Search Console en: {site_url}
            Quiero analizar datos del {start_date} al {end_date}
            
            Pregunta del usuario: {query}
            
            Para responder a esta pregunta, necesitas usar la función get_search_console_ctr con los parámetros apropiados.
            Si la pregunta menciona filtros específicos (como palabras clave), úsalos en query_filter.
            """
            
            response = client.chat.completions.create(
                model="gpt-4-0613",
                messages=[
                    {"role": "system", "content": "Eres un analista de datos especializado en Search Console. Siempre debes usar las funciones disponibles para obtener datos reales antes de responder preguntas sobre métricas de búsqueda."},
                    {"role": "user", "content": enhanced_prompt}
                ],
                tools=[{"type": "function", "function": func} for func in functions],
                tool_choice={"type": "function", "function": {"name": "get_search_console_ctr"}}
            )

            # Verificar si se debe llamar a una función
            if response.choices[0].message.tool_calls:
                function_call = response.choices[0].message.tool_calls[0].function
                
                try:
                    args = json.loads(function_call.arguments)
                    
                    with st.spinner("📊 Obteniendo datos de Search Console..."):
                        df_result = get_search_console_ctr(
                            site_url=args.get("site_url", site_url),
                            start_date=args.get("start_date", start_date),
                            end_date=args.get("end_date", end_date),
                            query_filter=args.get("query_filter")
                        )

                    if df_result.empty:
                        st.warning("⚠️ No se encontraron datos para los criterios especificados")
                        st.info("Posibles causas: fechas muy recientes, filtros muy restrictivos, o la propiedad no tiene datos")
                    else:
                        st.success(f"✅ Se encontraron {len(df_result)} consultas")
                        
                        # Limitar resultados
                        df_display = df_result.head(max_results)
                        
                        # Mostrar métricas clave
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("📊 Total Consultas", len(df_result))
                        with col2:
                            st.metric("👆 Total Clics", f"{int(df_result['clicks'].sum()):,}")
                        with col3:
                            st.metric("👀 Total Impresiones", f"{int(df_result['impressions'].sum()):,}")
                        with col4:
                            avg_ctr = df_result['ctr'].mean()
                            st.metric("📈 CTR Promedio", f"{avg_ctr:.2f}%")
                        
                        # Visualización
                        st.subheader("📈 Resultados")
                        
                        if tipo_grafico == "Tabla":
                            # Formatear la tabla
                            df_formatted = df_display.copy()
                            df_formatted['clicks'] = df_formatted['clicks'].apply(lambda x: f"{x:,}")
                            df_formatted['impressions'] = df_formatted['impressions'].apply(lambda x: f"{x:,}")
                            df_formatted['ctr'] = df_formatted['ctr'].apply(lambda x: f"{x}%")
                            
                            st.dataframe(
                                df_formatted,
                                column_config={
                                    "query": st.column_config.TextColumn("Consulta", width="large"),
                                    "clicks": st.column_config.TextColumn("Clics"),
                                    "impressions": st.column_config.TextColumn("Impresiones"),
                                    "ctr": st.column_config.TextColumn("CTR"),
                                    "position": st.column_config.NumberColumn("Posición", format="%.1f")
                                },
                                use_container_width=True
                            )
                            
                        elif tipo_grafico == "Gráfico de barras":
                            chart = alt.Chart(df_display).mark_bar().encode(
                                x=alt.X('clicks:Q', title='Clics'),
                                y=alt.Y('query:N', title='Consulta', sort='-x'),
                                tooltip=['query', 'clicks', 'impressions', 'ctr', 'position']
                            ).properties(
                                title=f"Top {len(df_display)} Consultas por Clics",
                                height=400
                            )
                            st.altair_chart(chart, use_container_width=True)
                            
                        elif tipo_grafico == "Línea - Posición":
                            chart = alt.Chart(df_display).mark_line(point=True).encode(
                                x=alt.X('query:N', title='Consulta', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('position:Q', title='Posición promedio', scale=alt.Scale(reverse=True)),
                                tooltip=['query', 'position', 'clicks', 'impressions']
                            ).properties(
                                title="Posición promedio por consulta (menor es mejor)",
                                height=400
                            )
                            st.altair_chart(chart, use_container_width=True)
                            
                        elif tipo_grafico == "Línea - CTR":
                            chart = alt.Chart(df_display).mark_line(point=True).encode(
                                x=alt.X('query:N', title='Consulta', axis=alt.Axis(labelAngle=-45)),
                                y=alt.Y('ctr:Q', title='CTR (%)'),
                                tooltip=['query', 'ctr', 'clicks', 'impressions']
                            ).properties(
                                title="CTR por consulta",
                                height=400
                            )
                            st.altair_chart(chart, use_container_width=True)
                        
                    # Generar respuesta interpretativa después de obtener datos
                    if not df_result.empty:
                        # Análisis automático basado en la consulta
                        analysis_prompt = f"""
                        Basándote en estos datos de Search Console, responde a la pregunta: "{query}"
                        
                        Datos obtenidos:
                        - Total de consultas analizadas: {len(df_result)}
                        - CTR promedio: {df_result['ctr'].mean():.2f}%
                        - Total de clics: {df_result['clicks'].sum()}
                        - Posición promedio: {df_result['position'].mean():.1f}
                        
                        Top 5 consultas por CTR:
                        {df_result.nlargest(5, 'ctr')[['query', 'ctr', 'clicks', 'position']].to_string()}
                        
                        Proporciona un análisis conciso y accionable.
                        """
                        
                        analysis_response = client.chat.completions.create(
                            model="gpt-4-0613",
                            messages=[{"role": "user", "content": analysis_prompt}]
                        )
                        
                        # Botón de descarga
                        csv = df_result.to_csv(index=False)
                        st.download_button(
                            label="📥 Descargar datos completos (CSV)",
                            data=csv,
                            file_name=f"search_console_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )

                except json.JSONDecodeError:
                    st.error("❌ Error al procesar los argumentos de la función")
                except Exception as e:
                    st.error(f"❌ Error al ejecutar la consulta: {str(e)}")
            else:
                # Respuesta directa del modelo
                st.info("💭 Respuesta del modelo:")
                st.write(response.choices[0].message.content)
                
        except Exception as e:
            st.error(f"❌ Error al consultar el modelo de IA: {str(e)}")
            st.info("Verifica que tu clave de OpenAI sea válida y tenga créditos disponibles")

elif query and query.strip() and not site_url:
    st.warning("⚠️ Por favor, selecciona o ingresa una URL de propiedad")

# --- FOOTER CON INFORMACIÓN ---
st.divider()
st.markdown("""
<div style='text-align: center; color: #666;'>
<small>
🔐 Todas las credenciales se mantienen en tu sesión y no se almacenan permanentemente<br>
📊 Datos obtenidos directamente de Google Search Console via API oficial
</small>
</div>
""", unsafe_allow_html=True)
