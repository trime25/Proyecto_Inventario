import streamlit as st
import pandas as pd
import base64
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from PIL import Image





# Cargamos la imagen
favicon = Image.open("logo1.png")
# La configuramos

st.set_page_config(page_title="SISTEMA GESTIÓN TRIMECA", page_icon=favicon, layout="wide", initial_sidebar_state="collapsed")





# --- CONFIGURACIÓN ---

# Ocultar elementos de la interfaz de Streamlit
# --- 2. INYECCIÓN DE CSS (SOLUCIÓN MENÚ) ---

hide_st_style = """
<style>
    /* --- SECCIÓN 1: OCULTAR ELEMENTOS INDIVIDUALES --- */

    /* 1. Ocultar el botón de Menú (Los tres puntos verticales) */
    [data-testid="stMainMenu"] {
        visibility: hidden !important;
        display: none !important;
    }

    /* 2. Ocultar el botón "Deploy" (si aparece) */
    [data-testid="stDeployButton"] {
        visibility: hidden !important;
        display: none !important;
    }

    /* 3. Ocultar la decoración superior (la línea de colores) */
    [data-testid="stDecoration"] {
        visibility: hidden !important;
        display: none !important;
    }

    /* 4. Ocultar el Footer ("Made with Streamlit") */
    footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* 5. Ocultar el botón "Manage App" (Nube) */
    div[class^='viewerBadge_container'] {
        visibility: hidden !important;
        display: none !important;
    }
    
    /* 6. Ocultar la barra de herramientas completa (el contenedor de Share/Star) */
    /* Usamos visibility: visible en lugar de display: none para mantener el espacio físico 
       y no colapsar el header, evitando que la flecha se mueva */

    [data-testid="stToolbar"] {
        visibility: visible !important;
    }


    /* --- SECCIÓN 2: RECUPERAR LA FLECHA DEL SIDEBAR --- */

    /* A. Forzar que el contenedor del botón sea visible */
    [data-testid="stSidebarCollapsedControl"] {
        visibility: visible !important;
        display: block !important;
        z-index: 999999 !important; /* Estar por encima de todo */
    }

    /* B. 🔥 CRÍTICO: PINTAR LA FLECHA (ICONO SVG) */
    /* A veces la flecha está ahí pero es invisible (blanca sobre blanco). Esto la obliga a ser gris oscura. */
    [data-testid="stSidebarCollapsedControl"] svg {
        fill: rgb(49, 51, 63) !important;
        stroke: rgb(49, 51, 63) !important;
    }
    
    /* Si usas tema oscuro, cambia 'rgb(49, 51, 63)' por '#FFFFFF' (blanco) en las dos líneas de arriba */

</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# ---------------------------------------------------





# --- CONEXIÓN A BASE DE DATOS (POSTGRESQL/SUPABASE) ---

def get_engine():
    try:
        # Intenta leer desde secrets.toml
        db_config = st.secrets["connections"]["postgresql"]
        url = f"postgresql+psycopg2://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        return create_engine(url)
    except Exception as e:
        st.error(f"Error de configuración de BD: {e}")
        return None

engine = get_engine()





# --- FUNCIONES BASE DE DATOS ---

def run_query(query, params=None):
    """Ejecuta consultas de modificación (INSERT, UPDATE, DELETE)"""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(query), params if params else {})
            trans.commit()
        except Exception as e:
            trans.rollback()
            raise e

def read_query(query, params=None):
    """Ejecuta consultas de lectura y devuelve DataFrame"""
    with engine.connect() as conn:
        return pd.read_sql_query(text(query), conn, params=params if params else {})

def inicializar_db():
    queries = [
        '''CREATE TABLE IF NOT EXISTS activos (
            id VARCHAR(50) PRIMARY KEY, 
            descripcion TEXT, 
            ubicacion VARCHAR(100), 
            ultima_revision DATE, 
            estado VARCHAR(50), 
            modelo VARCHAR(100), 
            marca VARCHAR(100), 
            motivo_estado TEXT, 
            categoria VARCHAR(100), 
            pais VARCHAR(50),
            placa VARCHAR(50)
        )''',
        '''CREATE TABLE IF NOT EXISTS ubicaciones (
            nombre VARCHAR(100), 
            pais VARCHAR(50), 
            PRIMARY KEY (nombre, pais)
        )''',
        '''CREATE TABLE IF NOT EXISTS fotos (
            id SERIAL PRIMARY KEY,
            id_activo VARCHAR(50), 
            nombre_archivo VARCHAR(255),
            datos_binarios BYTEA
        )''',
        '''CREATE TABLE IF NOT EXISTS documentos (
            id SERIAL PRIMARY KEY,
            id_activo VARCHAR(50), 
            nombre_archivo VARCHAR(255),
            datos_binarios BYTEA
        )''',
        '''CREATE TABLE IF NOT EXISTS historial (
            id SERIAL PRIMARY KEY,
            id_activo VARCHAR(50), 
            origen VARCHAR(100), 
            destino VARCHAR(100), 
            fecha TIMESTAMP, 
            motivo TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS activos_eliminados (
            id VARCHAR(50), 
            ubicacion VARCHAR(100), 
            fecha_eliminacion TIMESTAMP, 
            motivo TEXT
        )'''
    ]
    
    if engine:
        with engine.connect() as conn:
            trans = conn.begin()
            for q in queries:
                conn.execute(text(q))
            
            # Actualización de columnas existentes si es necesario
            for col, tipo in [("categoria", "VARCHAR(100)"), ("pais", "VARCHAR(50)"), ("placa", "VARCHAR(50)")]:
                try:
                    conn.execute(text(f"ALTER TABLE activos ADD COLUMN IF NOT EXISTS {col} {tipo}"))
                except SQLAlchemyError:
                    pass 
            trans.commit()


# Inicializar al arrancar
if engine:
    inicializar_db()





# --- LISTAS DE DATOS ---


CATEGORIAS_LISTA = ["Maquinaria Pesada", "Maquinaria Ligera", "Vehículos (Flota)", "Equipos Industriales/Planta", "Equipos de T.I."]
PAISES_LISTA = ["VENEZUELA", "COLOMBIA", "ESTADOS UNIDOS"]
ITEMS_POR_PAGINA = 5




# --- FUNCIONES DE APOYO (CORREGIDAS 'BYTES') ---

def display_pdf_from_bytes(file_bytes):
    # CORRECCIÓN: Convertir memoryview a bytes explícitamente
    base64_pdf = base64.b64encode(bytes(file_bytes)).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

def guardar_archivos_bd(id_activo, archivos, tipo):
    """Guarda el archivo directamente en la BD como binario"""
    tabla = 'fotos' if tipo == 'foto' else 'documentos'
    
    for arc in archivos:
        datos = arc.read() # Esto ya devuelve bytes
        run_query(
            f"INSERT INTO {tabla} (id_activo, nombre_archivo, datos_binarios) VALUES (:id, :nombre, :datos)",
            {"id": id_activo, "nombre": arc.name, "datos": datos}
        )




# --- DIÁLOGOS ---


@st.dialog("VISOR")
def visor_documento(nombre, datos_binarios):
    st.write(f"### {nombre}")
    
    # CORRECCIÓN: Asegurar que es bytes
    datos_bytes = bytes(datos_binarios)

    if nombre.lower().endswith('.pdf'):
        display_pdf_from_bytes(datos_bytes)
    else:
        st.info("**Vista previa solo disponible para archivos PDF.**")
    
    st.download_button("📥 DESCARGAR", datos_bytes, file_name=nombre, key=f"dl_{nombre}")



@st.dialog("ELIMINAR ACTIVO")
def confirmar_eliminar_activo(activo_id):
    st.error(f"⚠️ ¿Desea eliminar permanentemente el activo **{activo_id}**?")
    if st.button("ELIMINAR", use_container_width=True):
        try:
            res = read_query("SELECT ubicacion FROM activos WHERE id=:id", {"id": activo_id})
            ubi_act = res.iloc[0]['ubicacion'] if not res.empty else "DESCONOCIDA"
            
            run_query("INSERT INTO activos_eliminados (id, ubicacion, fecha_eliminacion, motivo) VALUES (:id, :ubi, :fecha, :motivo)", 
                     {"id": activo_id, "ubi": ubi_act, "fecha": datetime.now(), "motivo": "ELIMINACIÓN MANUAL"})
            
            run_query("DELETE FROM activos WHERE id=:id", {"id": activo_id})
            run_query("DELETE FROM fotos WHERE id_activo=:id", {"id": activo_id})
            run_query("DELETE FROM documentos WHERE id_activo=:id", {"id": activo_id})
            
            st.success("Activo eliminado."); st.rerun()
        except Exception as e:
            st.error(f"Error al eliminar: {e}")



@st.dialog("ELIMINAR UBICACIÓN")
def confirmar_eliminacion_ubi(nombre, pais):
    st.warning(f"¿Eliminar **{nombre}** en **{pais}**?")
    if st.button("ELIMINAR"):
        run_query("DELETE FROM ubicaciones WHERE nombre=:nombre AND pais=:pais", {"nombre": nombre, "pais": pais})
        st.success("Ubicación eliminada."); st.rerun()



@st.dialog("EDITAR UBICACIÓN")
def editar_ubicacion_dialog(nombre_actual, pais_actual):
    st.write(f"Editar nombre de ubicación en **{pais_actual}**")
    nuevo_nombre = st.text_input("NUEVO NOMBRE", value=nombre_actual).upper()
    if st.button("GUARDAR CAMBIOS", use_container_width=True):
        if nuevo_nombre and nuevo_nombre != nombre_actual:
            try:
                with engine.connect() as conn:
                    trans = conn.begin()
                    conn.execute(text("UPDATE ubicaciones SET nombre=:nuevo WHERE nombre=:viejo AND pais=:pais"), 
                                {"nuevo": nuevo_nombre, "viejo": nombre_actual, "pais": pais_actual})
                    conn.execute(text("UPDATE activos SET ubicacion=:nuevo WHERE ubicacion=:viejo AND pais=:pais"), 
                                {"nuevo": nuevo_nombre, "viejo": nombre_actual, "pais": pais_actual})
                    trans.commit()
                st.success("**Ubicación actualizada con éxito.**"); st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")





# --- NAVEGACIÓN ---


opciones_menu = ["DASHBOARD", "REGISTRAR ACTIVO", "TRASLADOS", "GESTIONAR UBICACIONES", "HISTORIAL ELIMINADOS"]

if "navegacion_interna" not in st.session_state:
    st.session_state.navegacion_interna = "DASHBOARD"

try:
    indice_actual = opciones_menu.index(st.session_state.navegacion_interna)
except ValueError:
    indice_actual = 0

menu = st.sidebar.radio("MENÚ", opciones_menu, index=indice_actual)
st.session_state.navegacion_interna = menu





# --- DASHBOARD ---

if menu == "DASHBOARD":
    col_titulo, col_logo = st.columns([3, 1])
    with col_titulo:
        st.image("logo.png", width=150)
    with col_logo:
        st.title("ACTIVOS")

    banderas = {"VENEZUELA": "🇻🇪", "COLOMBIA": "🇨🇴", "ESTADOS UNIDOS": "🇺🇸"}

    # --- 🔍 INICIO DEL ANÁLISIS ---
    df = read_query("SELECT * FROM activos")
    
    # Ordenamos descendente por ID
    if not df.empty and 'id' in df.columns:
        df = df.sort_values(by='id', ascending=False)
    
    df_todas_ubis = read_query("SELECT nombre, pais FROM ubicaciones")

    f_cat = st.selectbox("**SELECCIONAR CATEGORÍA**", ["SELECCIONAR"] + CATEGORIAS_LISTA)

    if f_cat != "SELECCIONAR":
        st.subheader(f"🟦 {f_cat}")
        
        df_f_base = df[df['categoria'] == f_cat]
        
        # ---------------------------------------------------------------------
        # 🔄 CÁLCULO DINÁMICO DE CONTADORES BASADO EN FILTROS ACTIVOS
        # ---------------------------------------------------------------------
        
        conteo_paises = {}
        total_global = 0

        for p_code in PAISES_LISTA:
            # Subconjunto base del país
            temp_df = df_f_base[df_f_base['pais'] == p_code]
            
            # Recuperamos valores de los filtros desde la memoria (session_state)
            k_est = f"est_{p_code}"
            k_ubi = f"ubi_{p_code}"
            k_busq = f"busq_{p_code}"
            
            val_est = st.session_state.get(k_est, "TODOS")
            val_ubi = st.session_state.get(k_ubi, "TODAS")
            val_busq = st.session_state.get(k_busq, "").upper()

            # Aplicamos la lógica de filtrado para el contador
            if val_est != "TODOS":
                temp_df = temp_df[temp_df['estado'] == val_est]
            
            if val_ubi != "TODAS":
                temp_df = temp_df[temp_df['ubicacion'] == val_ubi]
                
            if val_busq:
                # ✅ AQUI AGREGAMOS LA BÚSQUEDA POR PLACA
                temp_df = temp_df[
                    temp_df['id'].astype(str).str.contains(val_busq, na=False) | 
                    temp_df['marca'].str.contains(val_busq, na=False) |
                    temp_df['placa'].astype(str).str.contains(val_busq, na=False)
                ]
            
            count = len(temp_df)
            conteo_paises[p_code] = count
            total_global += count

        # ---------------------------------------------------------------------

        # Mostramos las métricas actualizadas
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res4.metric("**TOTAL**", total_global)
        c_res1.metric("**VENEZUELA** 🇻🇪", conteo_paises.get("VENEZUELA", 0))
        c_res2.metric("**COLOMBIA** 🇨🇴", conteo_paises.get("COLOMBIA", 0))
        c_res3.metric("**EE.UU.** 🇺🇸", conteo_paises.get("ESTADOS UNIDOS", 0))
        st.divider()

        tabs_paises = st.tabs(PAISES_LISTA)

        for i, pais_nombre in enumerate(PAISES_LISTA):
            with tabs_paises[i]:
                with st.container(border=True):
                    st.markdown(f"### {banderas[pais_nombre]} {pais_nombre}")
                    
                    c_f1, c_f2, c_f3 = st.columns(3)
                    
                    ubis_pais = df_todas_ubis[df_todas_ubis['pais'] == pais_nombre]['nombre'].tolist()
                    
                    # Filtros visuales
                    f_est = c_f1.selectbox("🔍 ESTADO", ["TODOS", "OPERATIVO", "DAÑADO", "REPARACION"], key=f"est_{pais_nombre}")
                    f_ubi = c_f2.selectbox("🔍 UBICACIÓN", ["TODAS"] + ubis_pais, key=f"ubi_{pais_nombre}")
                    f_busq = c_f3.text_input("🔍 CÓDIGO, MARCA O PLACA", key=f"busq_{pais_nombre}").upper()
                
                # Filtrado de la tabla
                df_display = df_f_base[df_f_base['pais'] == pais_nombre]

                if f_est != "TODOS": 
                    df_display = df_display[df_display['estado'] == f_est]
                if f_ubi != "TODAS": 
                    df_display = df_display[df_display['ubicacion'] == f_ubi]
                if f_busq: 
                    # ✅ AQUI AGREGAMOS LA BÚSQUEDA POR PLACA TAMBIÉN
                    df_display = df_display[
                        df_display['id'].astype(str).str.contains(f_busq, na=False) | 
                        df_display['marca'].str.contains(f_busq, na=False) |
                        df_display['placa'].astype(str).str.contains(f_busq, na=False)
                    ]

                if df_display.empty:
                    st.info(f"No hay activos registrados en **{pais_nombre}**")
                else:
                    items_por_pag = ITEMS_POR_PAGINA
                    pag_key = f"pag_dash_{pais_nombre}_{f_cat}"
                    if pag_key not in st.session_state: st.session_state[pag_key] = 0
                    
                    total_activos = len(df_display)
                    total_paginas = (total_activos - 1) // items_por_pag + 1
                    if st.session_state[pag_key] >= total_paginas: st.session_state[pag_key] = 0
                        
                    inicio = st.session_state[pag_key] * items_por_pag
                    fin = inicio + items_por_pag
                    
                    df_pagina = df_display.iloc[inicio:fin]
                    
                    st.caption(f"Mostrando {len(df_pagina)} de {total_activos} activos (Página {st.session_state[pag_key] + 1} de {total_paginas})")

                    for _, row in df_pagina.iterrows():
                        color = "🟢" if row['estado'] == "OPERATIVO" else "🔴" if row['estado'] == "DAÑADO" else "🟡"
                        # Añadí la placa al título del expander para identificarla rápido
                        titulo_expander = f"{color} ID: {row['id']} | {row['marca']}"
                        if row['placa']:
                            titulo_expander += f" | PLACA: {row['placa']}"
                            
                        with st.expander(titulo_expander):

                            # --- SECCIÓN DE EDICIÓN ---
                            if f"edit_{row['id']}" in st.session_state:
                                with st.form(f"form_edit_{row['id']}"):
                                    
                                    st.subheader("✏️ EDITAR ACTIVO")
                                    c1, c2 = st.columns(2)
                                    emarc = c1.text_input("MARCA", str(row['marca'] or "")).upper()
                                    emod = c2.text_input("MODELO", str(row['modelo'] or "")).upper()
                                    ecat = st.selectbox("CATEGORÍA", CATEGORIAS_LISTA, index=CATEGORIAS_LISTA.index(row['categoria']) if row['categoria'] in CATEGORIAS_LISTA else 0)
                                    epais = st.selectbox("PAÍS", PAISES_LISTA, index=PAISES_LISTA.index(row['pais']) if row['pais'] in PAISES_LISTA else 0)
                                    est_list = ["OPERATIVO", "DAÑADO", "REPARACION"]
                                    eest = st.selectbox("ESTADO", est_list, index=est_list.index(row['estado']) if row['estado'] in est_list else 0)
                                    
                                    try: fecha_actual = datetime.strptime(str(row['ultima_revision']), '%Y-%m-%d').date()
                                    except: fecha_actual = datetime.now().date()
                                    erev = st.date_input("FECHA ÚLTIMA REVISIÓN", fecha_actual)
                                    
                                    emot = st.text_input("MOTIVO  ESTADO", str(row['motivo_estado'] or "")).upper()
                                    
                                    ubis_edit_df = read_query("SELECT nombre FROM ubicaciones WHERE pais=:pais", {"pais": epais})
                                    ubis_edit = ubis_edit_df['nombre'].tolist()
                                    
                                    current_ubi = row['ubicacion'] if row['ubicacion'] in ubis_edit else (ubis_edit[0] if ubis_edit else "SIN UBICACION")
                                    eubi = st.selectbox("UBICACIÓN", ubis_edit, index=ubis_edit.index(current_ubi) if current_ubi in ubis_edit else 0)
                                    edesc = st.text_area("DESCRIPCIÓN", str(row['descripcion'] or "")).upper()

                                    st.write("---")
                                    st.write("🗑️ **ELIMINAR ARCHIVOS EXISTENTES**")
                                    
                                    fotos_actuales = read_query("SELECT id, nombre_archivo FROM fotos WHERE id_activo=:id", {"id": row['id']})
                                    docs_actuales = read_query("SELECT id, nombre_archivo FROM documentos WHERE id_activo=:id", {"id": row['id']})
                                    
                                    eliminar_fotos_ids = []
                                    for idx, f_row in fotos_actuales.iterrows():
                                        if st.checkbox(f"**ELIMINAR FOTO**: {f_row['nombre_archivo']}", key=f"del_f_box_{f_row['id']}"):
                                            eliminar_fotos_ids.append(f_row['id'])
                                    
                                    eliminar_docs_ids = []
                                    for idx, d_row in docs_actuales.iterrows():
                                        if st.checkbox(f"**ELIMINAR DOCUMENTO**: {d_row['nombre_archivo']}", key=f"del_d_box_{d_row['id']}"):
                                            eliminar_docs_ids.append(d_row['id'])

                                    st.write("➕ **AÑADIR ARCHIVOS**")
                                    f, cd = st.columns(2)
                                    nuevas_fotos = f.file_uploader("SUBIR FOTOS", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'], key=f"nf_edit_{row['id']}")
                                    nuevos_docs = cd.file_uploader("SUBIR DOCUMENTOS", accept_multiple_files=True, type=['pdf', 'docx', 'xlsx', 'xls', 'txt'], key=f"nd_edit_{row['id']}")

                                    if st.form_submit_button("💾 GUARDAR CAMBIOS"):
                                        run_query("""UPDATE activos SET marca=:ma, modelo=:mo, estado=:st, motivo_estado=:mst, 
                                                   ubicacion=:ub, descripcion=:de, categoria=:ca, ultima_revision=:ur, pais=:pa WHERE id=:id""", 
                                                 {"ma": emarc, "mo": emod, "st": eest, "mst": emot, "ub": eubi, "de": edesc, 
                                                  "ca": ecat, "ur": erev, "pa": epais, "id": row['id']})
                                        
                                        for fid in eliminar_fotos_ids: run_query("DELETE FROM fotos WHERE id=:id", {"id": fid})
                                        for did in eliminar_docs_ids: run_query("DELETE FROM documentos WHERE id=:id", {"id": did})
                                        
                                        if nuevas_fotos: guardar_archivos_bd(row['id'], nuevas_fotos, 'foto')
                                        if nuevos_docs: guardar_archivos_bd(row['id'], nuevos_docs, 'doc')
                                        
                                        del st.session_state[f"edit_{row['id']}"]
                                        st.rerun()
                                
                                if st.button("CANCELAR EDICIÓN", key=f"canc_btn_{row['id']}"):
                                    del st.session_state[f"edit_{row['id']}"]
                                    st.rerun()

                            else:
                                # --- VISTA NORMAL DEL ACTIVO ---
                                col_img, col_info = st.columns([1, 1.2])
                                with col_img:
                                    fotos_df = read_query("SELECT id, datos_binarios FROM fotos WHERE id_activo=:id", {"id": row['id']})
                                    if not fotos_df.empty:
                                        idx = st.session_state.get(f"idx_{row['id']}", 0)
                                        image_data = fotos_df.iloc[idx % len(fotos_df)]['datos_binarios']
                                        st.image(bytes(image_data), use_container_width=True)
                                        
                                        ca, cb = st.columns(2)
                                        if ca.button("⬅️", key=f"prev_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx - 1; st.rerun()
                                        if cb.button("➡️", key=f"next_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx + 1; st.rerun()
                                    else: st.info("Sin fotos registradas.")

                                with col_info:
                                    st.write(f"**MARCA:** {row['marca']} | **MODELO:** {row['modelo']} | **PLACA:** {row['placa']}")

                                    if row['motivo_estado']:
                                        st.write(f"**ESTADO:** {row['estado']} | **MOTIVO:** {row['motivo_estado']}")
                                    else:
                                        st.write(f"**ESTADO:** {row['estado']}")
                                        
                                    st.write(f"**UBICACIÓN:** {row['ubicacion']}")
                                    st.write(f"**DESCRIPCIÓN:** {row['descripcion']}")
                                    st.write(f"**REVISIÓN:** {row['ultima_revision']}")
                                    #if row['placa']: st.write(f"**PLACA:** {row['placa']}")
                                    
                                    st.write("📄 **DOCUMENTOS**")

                                    docs_df = read_query("SELECT id, nombre_archivo, datos_binarios FROM documentos WHERE id_activo=:id", {"id": row['id']})                      
                                    for idx, d_row in docs_df.iterrows():
                                            if st.button(f"👁️ Abrir {d_row['nombre_archivo']}", key=f"btn_v_{d_row['id']}"): 
                                                visor_documento(d_row['nombre_archivo'], d_row['datos_binarios'])
                                
                                    st.divider()
                                    c_b1, c_b2 = st.columns(2)
                                    if c_b1.button("✏️ EDITAR ACTIVO", key=f"btn_edit_act_{row['id']}", use_container_width=True): 
                                        st.session_state[f"edit_{row['id']}"] = True
                                        st.rerun()
                                    if c_b2.button("🗑️ ELIMINAR ACTIVO", key=f"btn_del_act_{row['id']}", use_container_width=True):
                                        confirmar_eliminar_activo(row['id'])

                    if total_paginas > 1:
                        st.write("---")
                        c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
                        if st.session_state[pag_key] > 0:
                            if c_nav1.button("⬅️ Anterior", key=f"btn_prev_{pais_nombre}", use_container_width=True):
                                st.session_state[pag_key] -= 1; st.rerun()
                        if st.session_state[pag_key] < total_paginas - 1:
                            if c_nav3.button("Siguiente ➡️", key=f"btn_next_{pais_nombre}", use_container_width=True):
                                st.session_state[pag_key] += 1; st.rerun()
    else:
        st.info("👋 Bienvenido. Por favor, selecciona una **Categoría**.")




#--- REGISTRAR ACTIVO ---


#--- REGISTRAR ACTIVO ---
elif menu == "REGISTRAR ACTIVO":
    st.title("📝 REGISTRAR ACTIVO")

    # --- 🟢 CÓDIGO NUEVO: LÓGICA DE LIMPIEZA AL INICIO ---
    # Esto verifica si se ordenó limpiar en la ejecución anterior
    if "limpiar_formulario" not in st.session_state:
        st.session_state.limpiar_formulario = False

    if st.session_state.limpiar_formulario:
        claves_a_borrar = ["reg_id", "reg_placa", "reg_cat", "reg_pais", 
                           "reg_ubi", "reg_marc", "reg_mod", "reg_est", 
                           "reg_mot", "reg_desc", "reg_fotos", "reg_docs"]
        for clave in claves_a_borrar:
            if clave in st.session_state:
                del st.session_state[clave] # Borrar la clave reinicia el widget
        
        st.session_state.limpiar_formulario = False # Apagamos la bandera
    # -----------------------------------------------------

    # ... Aquí continúa tu código normal (df_todas_ubis, containers, inputs, etc) ...

    df_todas_ubis = read_query("SELECT nombre, pais FROM ubicaciones")
    
    with st.container(border=True):
        if df_todas_ubis.empty: 
            st.warning("⚠️ **DEBE CREAR UNA UBICACIÓN PRIMERO**")
            if st.button("📍 IR A GESTIONAR UBICACIONES", key="redir_pais", use_container_width=True):
                st.session_state.navegacion_interna = "GESTIONAR UBICACIONES"; st.rerun()
        
        # --- FILA 1 ---
        c_id1, c_id2 = st.columns([3, 1])
        rid = c_id1.text_input("ID ACTIVO*", key="reg_id", help="Código único del activo").upper()
        rplaca = c_id2.text_input("PLACA*", key="reg_placa", help="Número de placa único (si aplica)").upper()
        
        # --- FILA 2 ---
        c_p1, c_p2 = st.columns(2)
        rcat = c_p1.selectbox("CATEGORÍA*", CATEGORIAS_LISTA, key="reg_cat", index=None, placeholder="Seleccione una categoría...")
        rpais = c_p2.selectbox("PAÍS*", PAISES_LISTA, key="reg_pais", index=None, placeholder="Seleccione un país...")
        
        # Lógica de filtrado de ubicaciones
        ubis_filtradas = []
        if rpais:
            ubis_filtradas = df_todas_ubis[df_todas_ubis['pais'] == rpais]['nombre'].tolist()
        
        if rpais and not ubis_filtradas:
            st.warning(f"⚠️ **No hay ubicaciones creadas para {rpais}**")
            if st.button(f"➕ CREAR UBICACIÓN PARA {rpais}", key="redir_pais", use_container_width=True):
                st.session_state.navegacion_interna = "GESTIONAR UBICACIONES"; st.rerun()

        # --- FILA 3 ---
        c1, c2 = st.columns(2)
        rmarc = c1.text_input("MARCA*", key="reg_marc").upper()
        rmod = c2.text_input("MODELO*", key="reg_mod").upper()
        
        # Selectbox Ubicación (Dependiente)
        rubi = c1.selectbox("UBICACIÓN*", ubis_filtradas if ubis_filtradas else ["SIN UBICACIÓN"], key="reg_ubi", index=None, placeholder="Seleccione ubicación...") 
        
        # Selectbox Estado (Con valor por defecto controlado)
        est_opts = ["OPERATIVO", "DAÑADO", "REPARACION"]
        rest = c2.selectbox("ESTADO", est_opts, key="reg_est") # Por defecto toma el índice 0 (OPERATIVO)
        
        rmot = ""
        if rest in ["DAÑADO", "REPARACION"]:
            rmot = st.text_input("MOTIVO DE DAÑO / REPARACIÓN*", key="reg_mot").upper()
        
        rdesc = st.text_area("DESCRIPCIÓN / OBSERVACIONES", key="reg_desc").upper()
        
        col_f, col_d = st.columns(2)
        rfotos = col_f.file_uploader("🖼️ **CARGAR FOTOS**", accept_multiple_files=True, type=['png','jpg','jpeg'], key="reg_fotos")
        rdocs = col_d.file_uploader("📄 **CARGAR DOCUMENTOS (PDF/Office)**", accept_multiple_files=True, type=['pdf', 'docx', 'xlsx', 'txt'], key="reg_docs")
        
        # --- BOTÓN DE GUARDADO ---
        if st.button("💾 GUARDAR", use_container_width=True):
            # 1. Validación de campos obligatorios
            if not (rid and ubis_filtradas and rubi and rubi != "SIN UBICACIÓN" and rcat and (rest == "OPERATIVO" or rmot)):
                st.error("⚠️ **Por favor rellene todos los campos marcados con (*)**.")
            else:
                # 2. Validación de Duplicados (ID y PLACA)
                problemas = []
                check_id = read_query("SELECT id FROM activos WHERE id = :id", {"id": rid})
                if not check_id.empty: problemas.append(f"El ID **{rid}** ya existe.")
                
                if rplaca:
                    check_placa = read_query("SELECT id FROM activos WHERE placa = :pl AND placa != ''", {"pl": rplaca})
                    if not check_placa.empty: problemas.append(f"La PLACA **{rplaca}** ya existe.")

                if problemas:
                    for p in problemas: st.error(f"❌ {p}")
                else:
                    # 3. Guardado en BD
                    try:
                        run_query("""INSERT INTO activos (id, placa, marca, modelo, ubicacion, estado, motivo_estado, descripcion, ultima_revision, categoria, pais) 
                                     VALUES (:id, :pl, :ma, :mo, :ub, :st, :mst, :de, :ur, :ca, :pa)""", 
                                  {"id": rid, "pl": rplaca, "ma": rmarc, "mo": rmod, "ub": rubi, "st": rest, "mst": rmot, 
                                   "de": rdesc, "ur": datetime.now().date(), "ca": rcat, "pa": rpais})
                        
                        if rfotos: guardar_archivos_bd(rid, rfotos, 'foto')
                        if rdocs: guardar_archivos_bd(rid, rdocs, 'doc')
                        
                        # Éxito y Limpieza
                        st.toast(f"✅ Activo {rid} guardado correctamente", icon='🎉')
                        
                        # --- 🟢 CÓDIGO NUEVO: ACTIVAR BANDERA Y RECARGAR ---
                        st.session_state.limpiar_formulario = True
                        
                        import time
                        time.sleep(1) # Pausa breve para ver el Toast
                        st.rerun()    # Recargamos la página para que la limpieza ocurra arriba
                        # ---------------------------------------------------
                        
                    except Exception as e:
                        st.error(f"❌ Error inesperado: {e}")






#--- TRASLADOS ---


elif menu == "TRASLADOS":
    st.title("🚚 TRASLADOS")
    activos = read_query("SELECT id, ubicacion, pais FROM activos")
    df_u = read_query("SELECT * FROM ubicaciones")
    df_hist = read_query("SELECT * FROM historial ORDER BY fecha DESC")
    
    opais = st.selectbox("**SELECCIONAR ORIGEN**", PAISES_LISTA)
    activos_f = activos[activos['pais'] == opais]
    
    if not activos_f.empty:
        sel_id = st.selectbox("**SELECCIONAR ACTIVO**", activos_f['id'])
        curr = activos_f[activos_f['id'] == sel_id].iloc[0]
        st.info(f"📍 Ubicación Actual: {curr['pais']} - {curr['ubicacion']}")
        
        tpais = st.selectbox("**ELEGIR DESTINO**", PAISES_LISTA)
        u_dest_list = df_u[df_u['pais'] == tpais]['nombre'].tolist()
        tubi = st.selectbox("**UBICACIÓN DESTINO**", u_dest_list if u_dest_list else ["SIN OPCIONES"])
        mot = st.text_input("**MOTIVO**").upper()
        
        if st.button("PROCESAR TRASLADO", use_container_width=True):
            if tubi != "SIN OPCIONES":
                try:
                    with engine.connect() as conn:
                        trans = conn.begin()
                        conn.execute(text("UPDATE activos SET ubicacion=:ub, pais=:pa WHERE id=:id"), 
                                    {"ub": tubi, "pa": tpais, "id": sel_id})
                        conn.execute(text("INSERT INTO historial (id_activo, origen, destino, fecha, motivo) VALUES (:id, :ori, :dest, :fecha, :mot)"), 
                                    {"id": sel_id, "ori": f"{curr['pais']}-{curr['ubicacion']}", 
                                     "dest": f"{tpais}-{tubi}", "fecha": datetime.now(), "mot": mot})
                        trans.commit()
                    st.success("Traslado exitoso."); st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.write("### HISTORIAL DE MOVIMIENTOS")
    if not df_hist.empty:
        if "pag_hist" not in st.session_state: st.session_state.pag_hist = 0
        total_hist = len(df_hist)
        total_pags_hist = (total_hist - 1) // ITEMS_POR_PAGINA + 1
        inicio_h = st.session_state.pag_hist * ITEMS_POR_PAGINA
        st.dataframe(df_hist.iloc[inicio_h : inicio_h + ITEMS_POR_PAGINA], use_container_width=True)
        
        c_h1, c_h2, c_h3 = st.columns([1, 2, 1])
        if st.session_state.pag_hist > 0:
            if c_h1.button("⬅️ Anterior", key="prev_hist", use_container_width=True): st.session_state.pag_hist -= 1; st.rerun()
        if st.session_state.pag_hist < total_pags_hist - 1:
            if c_h3.button("Siguiente ➡️", key="next_hist", use_container_width=True): st.session_state.pag_hist += 1; st.rerun()
    else: st.info("Sin movimientos registrados.")





#--- GESTIONAR UBICACIONES ---


elif menu == "GESTIONAR UBICACIONES":
    st.title("📍 GESTIONAR UBICACIONES")
    banderas = {"VENEZUELA": "🇻🇪", "COLOMBIA": "🇨🇴", "ESTADOS UNIDOS": "🇺🇸"}

    with st.form("form_ubicaciones", clear_on_submit=True):
        st.subheader("Registrar Nueva Ubicación")
        c_u1, c_u2 = st.columns(2)
        upais = c_u1.selectbox("**PAÍS:**", PAISES_LISTA, format_func=lambda x: f"{banderas.get(x, '🌐')} {x}")
        unombre = c_u2.text_input("NOMBRE DE LA UBICACIÓN").upper()
        
        if st.form_submit_button("💾 GUARDAR UBICACIÓN", use_container_width=True):
            if unombre:
                try:
                    run_query("INSERT INTO ubicaciones (nombre, pais) VALUES (:nom, :pais)", {"nom": unombre, "pais": upais})
                    st.success(f"✅ ¡{unombre} guardada con éxito en {upais}!")
                    st.rerun()
                except Exception as e: 
                    st.error(f"❌ Error (¿Ya existe?): {e}")

    st.divider()
    st.subheader("Lista de Ubicaciones")
    
    # 1. Consultamos los datos
    ubis_db = read_query("SELECT nombre, pais FROM ubicaciones")
    
    if not ubis_db.empty:
        # --- MODIFICACIÓN CLAVE AQUÍ ---
        # Invertimos el DataFrame para que el último registro quede primero (Simula LIFO)
        ubis_db = ubis_db.iloc[::-1].reset_index(drop=True)
        # -------------------------------

        if "pag_ubi" not in st.session_state: st.session_state.pag_ubi = 0
        total_u = len(ubis_db)
        total_pags_u = (total_u - 1) // ITEMS_POR_PAGINA + 1
        
        # Corrección de paginación si se borran elementos y queda en página vacía
        if st.session_state.pag_ubi >= total_pags_u: st.session_state.pag_ubi = 0
        
        inicio_u = st.session_state.pag_ubi * ITEMS_POR_PAGINA
        fin_u = inicio_u + ITEMS_POR_PAGINA
        
        # Iteramos sobre la lista ya invertida
        for idx, u in ubis_db.iloc[inicio_u : fin_u].iterrows():
            col_i, col_e, col_d = st.columns([4, 0.5, 0.5])
            bandera_actual = banderas.get(u['pais'], "🚩")
            
            with col_i:
                st.markdown(f"#### {bandera_actual} {u['nombre']}")
                st.caption(f"País: {u['pais']}")
            
            if col_e.button("✏️", key=f"ed_u_{u['nombre']}_{u['pais']}", help="Editar"): editar_ubicacion_dialog(u['nombre'], u['pais'])
            if col_d.button("🗑️", key=f"de_u_{u['nombre']}_{u['pais']}", help="Eliminar"): confirmar_eliminacion_ubi(u['nombre'], u['pais'])
            st.divider()
        
        if total_pags_u > 1:
            c_u1, c_u2, c_u3 = st.columns([1, 2, 1])
            if st.session_state.pag_ubi > 0:
                if c_u1.button("⬅️ Anterior", key="prev_u", use_container_width=True): st.session_state.pag_ubi -= 1; st.rerun()
            
            c_u2.caption(f"<center>Página {st.session_state.pag_ubi + 1} de {total_pags_u}</center>", unsafe_allow_html=True)
            
            if st.session_state.pag_ubi < total_pags_u - 1:
                if c_u3.button("Siguiente ➡️", key="next_u", use_container_width=True): st.session_state.pag_ubi += 1; st.rerun()
    else:
        st.info("Aún no has registrado ninguna ubicación.")





#--- HISTORIAL ELIMINADOS ---


elif menu == "HISTORIAL ELIMINADOS":
    st.title("🗑️ ACTIVOS ELIMINADOS")
    df_elim = read_query("SELECT * FROM activos_eliminados ORDER BY fecha_eliminacion DESC")
    
    if not df_elim.empty:
        if "pag_elim" not in st.session_state: st.session_state.pag_elim = 0
        total_e = len(df_elim)
        total_pags_e = (total_e - 1) // ITEMS_POR_PAGINA + 1
        inicio_e = st.session_state.pag_elim * ITEMS_POR_PAGINA
        
        st.dataframe(df_elim.iloc[inicio_e : inicio_e + ITEMS_POR_PAGINA], use_container_width=True)
        
        c_e1, c_e2, c_e3 = st.columns([1, 2, 1])
        if st.session_state.pag_elim > 0:
            if c_e1.button("⬅️ Anterior", key="prev_elim", use_container_width=True): st.session_state.pag_elim -= 1; st.rerun()
        if st.session_state.pag_elim < total_pags_e - 1:
            if c_e3.button("Siguiente ➡️", key="next_elim", use_container_width=True): st.session_state.pag_elim += 1; st.rerun()
    else: st.info("No hay historial de activos eliminados.")