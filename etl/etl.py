"""
Módulo ETL (etl.py)
Inspección inicial, limpieza, normalización exhaustiva y carga a base NoSQL.
Soporta delimitadores por punto y coma (;) o coma (,), codificación Latin-1/CP1252 
y columnas AÑO/MES/DIA separadas (Dataset 4v6r-wu98).
"""

import sys
import time
import pandas as pd
import re
from unidecode import unidecode
from backend.Bd.db import cargar_datos_nosql

NOMBRE_ARCHIVO = "delitos_informaticos.csv"

# Mapeo de nombres y abreviaturas de meses en español a su número correspondiente
MESES_NUM_MAP = {
    "ENE": 1, "ENERO": 1,
    "FEB": 2, "FEBRERO": 2,
    "MAR": 3, "MARZO": 3,
    "ABR": 4, "ABRIL": 4,
    "MAY": 5, "MAYO": 5,
    "JUN": 6, "JUNIO": 6,
    "JUL": 7, "JULIO": 7,
    "AGO": 8, "AGOS": 8, "AGOSTO": 8,
    "SEP": 9, "SEPT": 9, "SEPTIEMBRE": 9,
    "OCT": 10, "OCTUBRE": 10,
    "NOV": 11, "NOVIEMBRE": 11,
    "DIC": 12, "DICIEMBRE": 12
}

MESES_NOMBRE_MAP = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"
}


def normalizar_texto(texto):
    """Limpia espacios, elimina tildes y convierte a mayúsculas sostenidas."""
    if pd.isna(texto):
        return "NO REPORTADO"
    texto_str = str(texto).strip()
    texto_sin_tildes = unidecode(texto_str)
    texto_limpio = re.sub(r'\s+', ' ', texto_sin_tildes).upper()
    return texto_limpio if texto_limpio else "NO REPORTADO"


def cargar_csv_con_encoding_y_sep(ruta_csv, **kwargs):
    """Prueba combinaciones de codificación y delimitadores (;, ,) comunes."""
    encodings = ['latin-1', 'cp1252', 'utf-8', 'iso-8859-1', 'utf-8-sig']
    separadores = [';', ',', '\t']
    
    for enc in encodings:
        for sep in separadores:
            try:
                df = pd.read_csv(ruta_csv, encoding=enc, sep=sep, **kwargs)
                if len(df.columns) > 1:
                    return df, enc, sep
            except (UnicodeDecodeError, UnicodeError, pd.errors.ParserError):
                continue

    for enc in encodings:
        try:
            df = pd.read_csv(ruta_csv, encoding=enc, **kwargs)
            return df, enc, ','
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise RuntimeError("No se pudo interpretar la estructura o codificación del CSV.")


def parsear_mes_a_numero(val):
    """Convierte cadenas como 'Agos', '08', 8 o 'AGOSTO' a un entero entre 1 y 12."""
    if pd.isna(val):
        return None
    val_str = str(val).strip().upper()
    val_clean = unidecode(val_str)
    
    if val_clean.isdigit():
        num = int(val_clean)
        return num if 1 <= num <= 12 else None
        
    return MESES_NUM_MAP.get(val_clean, None)


def inspeccionar_y_limpiar_csv(ruta_csv: str):
    """
    Inspecciona el CSV, detecta separador y codificación, procesa las columnas de fecha,
    limpia los datos y los carga en la base NoSQL.
    """
    print("=" * 70)
    print(" PASO 1: INSPECCIÓN INICIAL DEL ARCHIVO CSV REAL")
    print("=" * 70)
    
    try:
        df_sample, enc_detectado, sep_detectado = cargar_csv_con_encoding_y_sep(ruta_csv, nrows=5)
        print(f"[INFO] Codificación detectada: '{enc_detectado}' | Separador: '{sep_detectado}'")
    except FileNotFoundError:
        print(f"[ERROR CRÍTICO] Archivo '{ruta_csv}' no encontrado en el directorio raíz.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se pudo leer el archivo CSV: {e}")
        sys.exit(1)

    print(f"\n[Columnas Reales Detectadas en el CSV ({len(df_sample.columns)})]:")
    for col in df_sample.columns:
        print(f"  - '{col.strip()}' (Tipo detectado: {df_sample[col].dtype})")

    print("\n[Muestra de las Primeras 5 Filas de Datos Reales]:")
    print(df_sample.to_string())
    print("=" * 70)

    print("\nIniciando lectura completa y procesamiento del dataset (~274.000 filas)...")
    inicio_tiempo = time.time()
    
    # Lectura completa del dataset
    df_raw, _, _ = cargar_csv_con_encoding_y_sep(ruta_csv, low_memory=False)
    total_leidos = len(df_raw)

    # Limpiar nombres de columnas
    mantenimiento_cols = {col: unidecode(str(col)).strip().lower().replace(' ', '_') for col in df_raw.columns}
    df_raw.rename(columns=mantenimiento_cols, inplace=True)

    # Mapeo dinámico de columnas
    col_fecha = next((c for c in df_raw.columns if 'fecha' in c), None)
    col_anio = next((c for c in df_raw.columns if 'ano' in c or 'anio' in c), None)
    col_mes = next((c for c in df_raw.columns if 'mes' in c), None)
    col_dia = next((c for c in df_raw.columns if 'dia' in c), None)
    
    col_depto = next((c for c in df_raw.columns if 'depa' in c or 'dpto' in c), None)
    col_muni = next((c for c in df_raw.columns if 'muni' in c or 'ciudad' in c), None)
    col_delito = next((c for c in df_raw.columns if 'nombre_legal' in c or 'conducta' in c or 'delito' in c or 'tipologia' in c or 'descripcion' in c or 'articulo' in c), None)
    col_cantidad = next((c for c in df_raw.columns if 'canti' in c or 'total' in c or 'casos' in c), None)

    df = pd.DataFrame()

    # Procesamiento de Fechas (Fecha completa vs Año/Mes/Día separados)
    if col_fecha:
        df['fecha_dt'] = pd.to_datetime(df_raw[col_fecha], errors='coerce', dayfirst=True)
        df['anio'] = df['fecha_dt'].dt.year
        df['mes_num'] = df['fecha_dt'].dt.month
    elif col_anio and col_mes:
        df['anio'] = pd.to_numeric(df_raw[col_anio], errors='coerce')
        df['mes_num'] = df_raw[col_mes].apply(parsear_mes_a_numero)
        
        dias_num = pd.to_numeric(df_raw[col_dia], errors='coerce').fillna(1).astype(int) if col_dia else 1
            
        # Reconstruir string de fecha YYYY-MM-DD
        def armar_fecha(row, dia_val):
            try:
                a = int(row['anio'])
                m = int(row['mes_num'])
                d = int(dia_val)
                return f"{a:04d}-{m:02d}-{d:02d}"
            except Exception:
                return None

        df['fecha_str'] = [
            armar_fecha({'anio': a, 'mes_num': m}, d) 
            for a, m, d in zip(df['anio'], df['mes_num'], dias_num)
        ]
        df['fecha_dt'] = pd.to_datetime(df['fecha_str'], errors='coerce')
    else:
        print("[ERROR] No se encontraron columnas válidas de fecha.")
        sys.exit(1)

    df['mes_nombre'] = df['mes_num'].map(MESES_NOMBRE_MAP)
    df['fecha'] = df['fecha_dt'].dt.strftime('%Y-%m-%d')

    # Normalización de textos
    df['departamento'] = df_raw[col_depto].apply(normalizar_texto) if col_depto else "NO REPORTADO"
    df['municipio'] = df_raw[col_muni].apply(normalizar_texto) if col_muni else "NO REPORTADO"
    df['tipologia'] = df_raw[col_delito].apply(normalizar_texto) if col_delito else "NO REPORTADO"

    # Cantidad
    if col_cantidad and col_cantidad in df_raw.columns:
        df['cantidad'] = pd.to_numeric(df_raw[col_cantidad], errors='coerce').fillna(1).astype(int)
    else:
        df['cantidad'] = 1

    # Depuración de filas inválidas o duplicadas
    df_clean = df.dropna(subset=['fecha', 'anio', 'mes_num', 'departamento', 'municipio', 'tipologia']).copy()
    df_clean = df_clean[df_clean['cantidad'] > 0]
    df_clean.drop_duplicates(subset=['fecha', 'departamento', 'municipio', 'tipologia', 'cantidad'], inplace=True)
    df_clean['anio'] = df_clean['anio'].astype(int)
    df_clean['mes_num'] = df_clean['mes_num'].astype(int)

    total_cargados = len(df_clean)
    total_descartados = total_leidos - total_cargados
    duracion = round(time.time() - inicio_tiempo, 2)

    print("\n" + "=" * 70)
    print(" RESUMEN DEL PROCESO ETL (HU1)")
    print("=" * 70)
    print(f" Total registros leídos del CSV:  {total_leidos:,}")
    print(f" Total registros limpios cargados: {total_cargados:,}")
    print(f" Total registros descartados:      {total_descartados:,}")
    print(f" Tiempo total de procesamiento:    {duracion} segundos")
    print("=" * 70)

    # Carga a NoSQL
    print("\nCargando datos a la base de datos NoSQL...")
    columnas_finales = ['fecha', 'anio', 'mes_num', 'mes_nombre', 'departamento', 'municipio', 'tipologia', 'cantidad']
    cargar_datos_nosql(df_clean[columnas_finales])
    print("[ETL FINALIZADO CON ÉXITO]")


if __name__ == "__main__":
    inspeccionar_y_limpiar_csv(NOMBRE_ARCHIVO)