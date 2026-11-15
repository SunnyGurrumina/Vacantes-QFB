import requests
import pandas as pd
from datetime import datetime, timedelta
import smtplib
import os
import re
import unicodedata
from email.message import EmailMessage

# =============================
# CONFIGURACIÓN API ADZUNA
# =============================
APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")
if not APP_ID or not APP_KEY:
    raise ValueError("ADZUNA_APP_ID o ADZUNA_APP_KEY no están configuradas en los secrets de GitHub")
URL_ADZUNA = "https://api.adzuna.com/v1/api/jobs/mx/search/1"

# =============================
# CONFIGURACIÓN API JOOBLE
# =============================
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")
if not JOOBLE_API_KEY:
    raise ValueError("JOOBLE_API_KEY no está configurada en los secrets de GitHub")
URL_JOOBLE = f"https://jooble.org/api/{JOOBLE_API_KEY}"

# =============================
# CONFIGURACIÓN API JSEARCH (RapidAPI)
# =============================
JSEARCH_API_KEY = os.getenv("JSEARCH_API_KEY")
if not JSEARCH_API_KEY:
    raise ValueError("JSEARCH_API_KEY no está configurada en los secrets de GitHub")
URL_JSEARCH = "https://jsearch.p.rapidapi.com/search-v2"
HEADERS_JSEARCH = {
    "x-rapidapi-host": "jsearch.p.rapidapi.com",
    "x-rapidapi-key": JSEARCH_API_KEY
}

# =============================
# PARÁMETROS DE BÚSQUEDA
# =============================
ciudades = ["Guadalajara"]
keywords = ["QFB", "Farmaceutico", "Farmacia", "Quimico", "Responsable Sanitario", "Regulacion Sanitaria", "Farmacobiologo", "Asuntos Reguñatorios"]

def parse_salario_jooble(valor):
    """Extrae un número de un string de salario de Jooble (maneja $, comas y sufijo 'k')."""
    if not valor:
        return None
    valor = valor.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", valor, re.IGNORECASE)
    if not match:
        return None
    numero = float(match.group(1))
    if match.group(2):
        numero *= 1000
    return numero
    
# =============================
# EXTRACCIÓN DE VACANTES
# =============================
resultados = []

print("Iniciando extracción de vacantes (Adzuna + Jooble + JSearch)...")

for ciudad in ciudades:
    for keyword in keywords:
        print(f"Buscando '{keyword}' en {ciudad}...")

        # ---------- Adzuna ----------
        params_adzuna = {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "what": keyword,
            "where": ciudad,
            "distance": 20,
            "results_per_page": 20,
            "sort_by": "date",
            "salary_min": 10000,
            "max_days_old": 4
        }
        try:
            response_adzuna = requests.get(URL_ADZUNA, params=params_adzuna, timeout=10)
            if response_adzuna.status_code == 200:
                data = response_adzuna.json()
                for job in data.get("results", []):
                    salario_max = job.get("salary_max")
                    salario_mensual_max = float(salario_max) / 12 if salario_max else None
                    
                    resultados.append({
                        "Ciudad": ciudad,
                        "Keyword": keyword,
                        "Título": job.get("title"),
                        "Empresa": job.get("company", {}).get("display_name"),
                        "Salario mínimo": job.get("salary_min"),
                        "Salario máximo": job.get("salary_max"),
                        "Salario Mensual Max": salario_mensual_max,  # Nueva columna agregada
                        "Fecha publicación": job.get("created"),
                        "Ubicación": job.get("location", {}).get("display_name"),
                        "URL": job.get("redirect_url"),
                        "Fuente": "Adzuna"
                    })
        except Exception as e:
            print(f"Error en Adzuna: {e}")

        # ---------- Jooble ----------
        payload_jooble = {
            "keywords": keyword,
            "location": "Guadalajara, Jal." if ciudad == "Guadalajara" else "Monterrey, Nuevo León",
            #"radius": "26",
            "page": "1",
            "ResultOnPage": 50
        }
        headers_jooble = {"Content-Type": "application/json"}

        try:
            response_jooble = requests.post(URL_JOOBLE, json=payload_jooble, headers=headers_jooble, timeout=10)
            print(f"  Jooble status: {response_jooble.status_code}")
            if response_jooble.status_code == 200:
                data_jooble = response_jooble.json()
                print(f"  Jooble jobs devueltos: {len(data_jooble.get('jobs', []))}")
                for job in data_jooble.get("jobs", []):
                    salario_str = job.get("salary", "")
                    salario_min = salario_max = None
                    if salario_str:
                        if "-" in salario_str:
                            partes = salario_str.split("-", 1)
                            salario_min = parse_salario_jooble(partes[0])
                            salario_max = parse_salario_jooble(partes[1])
                        else:
                            salario_min = salario_max = parse_salario_jooble(salario_str)
                    salario_mensual_max = salario_max / 12 if salario_max else None

                    resultados.append({
                        "Ciudad": ciudad,
                        "Keyword": keyword,
                        "Título": job.get("title"),
                        "Empresa": job.get("company"),
                        "Salario mínimo": salario_min,
                        "Salario máximo": salario_max,
                        "Salario Mensual Max": salario_mensual_max,  # Nueva columna agregada
                        "Fecha publicación": job.get("updated"),
                        "Ubicación": job.get("location"),
                        "URL": job.get("link"),
                        "Fuente": "Jooble"
                    })
            else:
                print(f"  Error Jooble: {response_jooble.text[:200]}")
        except Exception as e:
            print(f"Error en Jooble: {e}")

        # ---------- JSearch ----------
        params_jsearch = {
            "query": f"{keyword} in {ciudad}, Mexico",
            "country": "mx",
            "language": "es",
            "num_pages": "1",
            "date_posted": "3days"
        }
        try:
            response_jsearch = requests.get(URL_JSEARCH, headers=HEADERS_JSEARCH, params=params_jsearch, timeout=10)
            print(f"  JSearch status: {response_jsearch.status_code}")
            if response_jsearch.status_code == 200:
                data_jsearch = response_jsearch.json()
                for job in data_jsearch.get("data", {}).get("jobs", []):
                    if job.get("job_country") and job.get("job_country") != "MX":
                        continue
                    salario_max = job.get("job_max_salary")
                    salario_mensual_max = float(salario_max) / 12 if salario_max else None

                    resultados.append({
                        "Ciudad": ciudad,
                        "Keyword": keyword,
                        "Título": job.get("job_title"),
                        "Empresa": job.get("employer_name"),
                        "Salario mínimo": job.get("job_min_salary"),
                        "Salario máximo": salario_max,
                        "Salario Mensual Max": salario_mensual_max,
                        "Fecha publicación": job.get("job_posted_at_datetime_utc"),
                        "Ubicación": job.get("job_city") or ciudad,
                        "URL": job.get("job_apply_link"),
                        "Fuente": "JSearch"
                    })
            else:
                print(f"  Error JSearch: {response_jsearch.text[:200]}")
        except Exception as e:
            print(f"Error en JSearch: {e}")

# =============================
# PROCESAMIENTO FINAL
# =============================
df = pd.DataFrame(resultados)
if df.empty:
    print("No se encontraron vacantes.")
else:
    # Eliminar duplicados por URL y ordenar por salario máximo
    df = df.drop_duplicates(subset=["URL"]).reset_index(drop=True)

    # Excluir vacantes de empresas específicas (sin importar mayúsculas/minúsculas)
    empresas_excluidas = ["San Javier"]
    patron_excluidas = "|".join(empresas_excluidas)
    filas_antes = len(df)
    df = df[~df["Empresa"].str.contains(patron_excluidas, case=False, na=False)].reset_index(drop=True)
    print(f"Vacantes excluidas por empresa: {filas_antes - len(df)}")
    # Excluir vacantes de profesor/docente (por título, sin importar la empresa)
    titulos_excluidos = ["profesor", "docente", "maestro", "Ingeniero", "Auxiliar", "Becario ", "Chofer", "Promotor", "Recepcionista", "Calidad", "Medico"]
    patron_titulos = "|".join(titulos_excluidos)
    filas_antes_titulo = len(df)
    df = df[~df["Título"].str.contains(patron_titulos, case=False, na=False)].reset_index(drop=True)
    print(f"Vacantes excluidas por título: {filas_antes_titulo - len(df)}")
    # Excluir vacantes fuera de México (ubicaciones terminadas en código de estado de EE. UU.)
    
    estados_eeuu = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY",
                     "LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND",
                     "OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"]
    patron_estados_eeuu = r",\s*(?:" + "|".join(estados_eeuu) + r")$"
    filas_antes_ubicacion = len(df)
    df = df[~df["Ubicación"].str.contains(patron_estados_eeuu, regex=True, na=False)].reset_index(drop=True)
    print(f"Vacantes excluidas por ubicación fuera de México: {filas_antes_ubicacion - len(df)}")

    df["Salario máximo"] = pd.to_numeric(df["Salario máximo"], errors="coerce")

print(f"Vacantes únicas encontradas: {len(df)}")

# =============================
# ARCHIVO EXCEL (NOMBRE DINÁMICO)
# =============================
fecha = datetime.now().strftime("%y%m%d")
archivo_excel = f"{fecha}_Vacantes.xlsx"
df.to_excel(archivo_excel, index=False)
print(f"Archivo Excel generado: {archivo_excel}")

# =============================
# TABLA HTML PARA EMAIL
# =============================
tabla_html = df.to_html(index=False, border=0, classes="table table-striped")
html_body = f"""
<html>
  <body>
    <h2>Vacantes actualizadas al {datetime.now().strftime("%d/%m/%Y")}</h2>
    <p><strong>Total de vacantes únicas encontradas:</strong> {len(df)}</p>
    <p>Todas las vacantes (ordenadas por salario máximo descendente):</p>
    {tabla_html}
    <p><br>Se adjunta el archivo Excel con todas las vacantes.</p>
    <p>Saludos,</p>
    <p>Tu buscador automático de vacantes</p>
  </body>
</html>
"""

# =============================
# ENVÍO DE EMAIL
# =============================
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")

if EMAIL_USER and EMAIL_PASS and EMAIL_TO:
    msg = EmailMessage()
    msg["Subject"] = f"Vacantes actualizadas - {fecha}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.set_content("Tu cliente de correo no soporta HTML.")
    msg.add_alternative(html_body, subtype="html")

    with open(archivo_excel, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=archivo_excel
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print("Email enviado correctamente.")
    except Exception as e:
        print(f"Error al enviar email: {e}")
else:
    print("Credenciales de email no configuradas. Email no enviado (configura secrets en GitHub).")

print("Proceso completado.")




