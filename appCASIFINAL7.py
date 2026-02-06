import streamlit as st
import sqlite3
import pandas as pd
import os
import base64
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SISTEMA GESTIÓN TRIMECA", layout="wide", initial_sidebar_state="collapsed")

for carpeta in ['fotos_activos', 'docs_activos']:
    if not os.path.exists(carpeta): os.makedirs(carpeta)

# --- BASE DE DATOS ---
def conectar_db():
    return sqlite3.connect('inventario.db', check_same_thread=False, timeout=60)

def inicializar_db():
    with conectar_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS activos (
                        id TEXT PRIMARY KEY, descripcion TEXT, ubicacion TEXT, 
                        ultima_revision DATE, estado TEXT, modelo TEXT, 
                        marca TEXT, motivo_estado TEXT, categoria TEXT, pais TEXT)''')
        
        for col in [("categoria", "TEXT"), ("pais", "TEXT")]:
            try: c.execute(f"ALTER TABLE activos ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError: pass

        c.execute('''CREATE TABLE IF NOT EXISTS ubicaciones (
                        nombre TEXT, 
                        pais TEXT, 
                        PRIMARY KEY (nombre, pais))''')
        conn.commit()

        c.execute('''CREATE TABLE IF NOT EXISTS fotos (id_activo TEXT, path TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS documentos (id_activo TEXT, path TEXT, nombre_real TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial (id_activo TEXT, origen TEXT, destino TEXT, fecha TIMESTAMP, motivo TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS activos_eliminados (id TEXT, ubicacion TEXT, fecha_eliminacion TIMESTAMP, motivo TEXT)''')
        conn.commit()

inicializar_db()

# --- LISTAS DE DATOS ---
CATEGORIAS_LISTA = ["Maquinaria Pesada", "Maquinaria Ligera", "Vehículos (Flota)", "Equipos Industriales/Planta", "Equipos de T.I."]
PAISES_LISTA = ["VENEZUELA", "COLOMBIA", "ESTADOS UNIDOS"]
ITEMS_POR_PAGINA = 5

# --- FUNCIONES DE APOYO ---
def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

def guardar_archivos(id_activo, archivos, tipo):
    carpeta = 'fotos_activos' if tipo == 'foto' else 'docs_activos'
    with conectar_db() as conn:
        for idx, arc in enumerate(archivos):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = os.path.splitext(arc.name)[1]
            ruta = os.path.join(carpeta, f"{id_activo}_{idx}_{timestamp}{ext}")
            with open(ruta, "wb") as f: f.write(arc.getbuffer())
            if tipo == 'foto': conn.execute("INSERT INTO fotos (id_activo, path) VALUES (?,?)", (id_activo, ruta))
            else: conn.execute("INSERT INTO documentos (id_activo, path, nombre_real) VALUES (?,?,?)", (id_activo, ruta, arc.name))
        conn.commit()

# --- DIÁLOGOS ---
@st.dialog("VISOR")
def visor_documento(path, nombre):
    st.write(f"### {nombre}")
    if path.lower().endswith('.pdf'): display_pdf(path)
    else: st.info("**Vista previa solo disponible para archivos PDF.**")
    with open(path, "rb") as f: st.download_button("📥 DESCARGAR", f, file_name=nombre, key=f"dl_{path}")

@st.dialog("ELIMINAR ACTIVO")
def confirmar_eliminar_activo(activo_id):
    st.error(f"⚠️ ¿Desea eliminar permanentemente el activo **{activo_id}**?")
    if st.button("ELIMINAR", use_container_width=True):
        with conectar_db() as conn:
            res = conn.execute("SELECT ubicacion FROM activos WHERE id=?", (activo_id,)).fetchone()
            ubi_act = res[0] if res else "DESCONOCIDA"
            conn.execute("INSERT INTO activos_eliminados (id, ubicacion, fecha_eliminacion, motivo) VALUES (?, ?, ?, ?)", (activo_id, ubi_act, datetime.now(), "ELIMINACIÓN MANUAL"))
            conn.execute("DELETE FROM activos WHERE id=?", (activo_id,))
            conn.execute("DELETE FROM fotos WHERE id_activo=?", (activo_id,))
            conn.execute("DELETE FROM documentos WHERE id_activo=?", (activo_id,))
            conn.commit()
        st.success("Activo eliminado."); st.rerun()

@st.dialog("ELIMINAR UBICACIÓN")
def confirmar_eliminacion_ubi(nombre, pais):
    st.warning(f"¿Eliminar **{nombre}** en **{pais}**?")
    if st.button("ELIMINAR"):
        with conectar_db() as conn:
            conn.execute("DELETE FROM ubicaciones WHERE nombre=? AND pais=?", (nombre, pais))
            conn.commit()
        st.success("Ubicación eliminada."); st.rerun()

@st.dialog("EDITAR UBICACIÓN")
def editar_ubicacion_dialog(nombre_actual, pais_actual):
    st.write(f"Editar nombre de ubicación en **{pais_actual}**")
    nuevo_nombre = st.text_input("NUEVO NOMBRE", value=nombre_actual).upper()
    if st.button("GUARDAR CAMBIOS", use_container_width=True):
        if nuevo_nombre and nuevo_nombre != nombre_actual:
            with conectar_db() as conn:
                try:
                    conn.execute("UPDATE ubicaciones SET nombre=? WHERE nombre=? AND pais=?", (nuevo_nombre, nombre_actual, pais_actual))
                    conn.execute("UPDATE activos SET ubicacion=? WHERE ubicacion=? AND pais=?", (nuevo_nombre, nombre_actual, pais_actual))
                    conn.commit()
                    st.success("**Ubicación actualizada con éxito.**"); st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"❌ **Error: Ya existe una ubicación llamada '{nuevo_nombre}' en {pais_actual}.**")


# --- NAVEGACIÓN ---

opciones_menu = ["DASHBOARD", "REGISTRAR ACTIVO", "TRASLADOS", "GESTIONAR UBICACIONES", "HISTORIAL ELIMINADOS"]

# Si no existe la variable de navegación, la inicializamos
if "navegacion_interna" not in st.session_state:
    st.session_state.navegacion_interna = "DASHBOARD"

# Calculamos el índice basándonos en la selección actual
try:
    indice_actual = opciones_menu.index(st.session_state.navegacion_interna)
except ValueError:
    indice_actual = 0

# IMPORTANTE: Eliminamos el 'key' del radio y usamos 'index'
menu = st.sidebar.radio("MENÚ", opciones_menu, index=indice_actual)

# Sincronizamos la variable por si el usuario hace clic manualmente
st.session_state.navegacion_interna = menu



# --- DASHBOARD ---

if menu == "DASHBOARD":
    col_titulo, col_logo = st.columns([3, 1])
    with col_titulo:
        st.image("logo.png", width=150)
    with col_logo:
       st.title("ACTIVOS") 
    
    with conectar_db() as conn:
        df = pd.read_sql_query("SELECT * FROM activos", conn)
        # Obtenemos todas las ubicaciones con su respectivo país para filtrar luego
        df_todas_ubis = pd.read_sql_query("SELECT nombre, pais FROM ubicaciones", conn)

    # Se añade una opción vacía por defecto
    f_cat = st.selectbox("**SELECCIONAR CATEGORÍA**", ["SELECCIONAR"] + CATEGORIAS_LISTA)

    # Solo mostrar información si se ha seleccionado una categoría válida
    if f_cat != "SELECCIONAR":
        st.subheader(f"🟦 {f_cat}")
        
        # Filtro de categoría global aplicado al dataframe base
        df_f_base = df[df['categoria'] == f_cat]
        
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res4.metric("**TOTAL**", len(df_f_base))
        c_res1.metric("**VENEZUELA** 🇻🇪", len(df_f_base[df_f_base['pais'] == "VENEZUELA"]))
        c_res2.metric("**COLOMBIA** 🇨🇴", len(df_f_base[df_f_base['pais'] == "COLOMBIA"]))
        c_res3.metric("**EE.UU.** 🇺🇸", len(df_f_base[df_f_base['pais'] == "ESTADOS UNIDOS"]))
        st.divider()

        tabs_paises = st.tabs(PAISES_LISTA)

        for i, pais_nombre in enumerate(PAISES_LISTA):
            with tabs_paises[i]:
                # --- FILTROS ESPECÍFICOS POR PAÍS ---
                with st.container(border=True):
                    st.markdown(f"###  ESTAS EN {pais_nombre}:")
                    c_f1, c_f2, c_f3 = st.columns(3)
                    
                    # 1. Filtro de ubicaciones dinámico según el país de la pestaña
                    ubis_pais = df_todas_ubis[df_todas_ubis['pais'] == pais_nombre]['nombre'].tolist()
                    
                    f_est = c_f1.selectbox("🔍 ESTADO", ["TODOS", "OPERATIVO", "DAÑADO", "REPARACION"], key=f"est_{pais_nombre}")
                    f_ubi = c_f2.selectbox("🔍 UBICACIÓN", ["TODAS"] + ubis_pais, key=f"ubi_{pais_nombre}")
                    f_busq = c_f3.text_input("🔍 CÓDIGO O MARCA", key=f"busq_{pais_nombre}").upper()
                
                # --- LÓGICA DE FILTRADO PARA LA VISTA ---
                df_display = df_f_base[df_f_base['pais'] == pais_nombre]

                if f_est != "TODOS": 
                    df_display = df_display[df_display['estado'] == f_est]
                if f_ubi != "TODAS": 
                    df_display = df_display[df_display['ubicacion'] == f_ubi]
                if f_busq: 
                    # 2. La búsqueda ahora solo afecta a los registros del país seleccionado
                    df_display = df_display[df_display['id'].str.contains(f_busq, na=False) | 
                                            df_display['marca'].str.contains(f_busq, na=False)]

                if df_display.empty:
                    st.info(f"No hay activos que coincidan con los filtros en {pais_nombre}.")
                else:
                    # --- LÓGICA DE PAGINACIÓN DE ACTIVOS (5 en 5) ---
                    items_por_pag = 5
                    pag_key = f"pag_dash_{pais_nombre}_{f_cat}"
                    
                    if pag_key not in st.session_state:
                        st.session_state[pag_key] = 0
                    
                    total_activos = len(df_display)
                    total_paginas = (total_activos - 1) // items_por_pag + 1
                    
                    if st.session_state[pag_key] >= total_paginas:
                        st.session_state[pag_key] = 0
                        
                    inicio = st.session_state[pag_key] * items_por_pag
                    fin = inicio + items_por_pag
                    df_pagina = df_display.iloc[inicio:fin]
                    
                    st.caption(f"Mostrando {len(df_pagina)} de {total_activos} activos (Página {st.session_state[pag_key] + 1} de {total_paginas})")

                    for _, row in df_pagina.iterrows():
                        color = "🟢" if row['estado'] == "OPERATIVO" else "🔴" if row['estado'] == "DAÑADO" else "🟡"
                        with st.expander(f"{color} ID: {row['id']} | {row['categoria']} | {row['marca']}"):
                            
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
                                    
                                    emot = st.text_input("MOTIVO / ESTADO", str(row['motivo_estado'] or "")).upper()
                                    # Para la edición cargamos todas las del país del activo
                                    ubis_edit = df_todas_ubis[df_todas_ubis['pais'] == epais]['nombre'].tolist()
                                    eubi = st.selectbox("UBICACIÓN", ubis_edit, index=ubis_edit.index(row['ubicacion']) if row['ubicacion'] in ubis_edit else 0)
                                    edesc = st.text_area("DESCRIPCIÓN", str(row['descripcion'] or "")).upper()

                                    st.write("---")
                                    st.write("🗑️ **ELIMINAR ARCHIVOS EXISTENTES**")
                                    with conectar_db() as conn:
                                        fotos_actuales = conn.execute("SELECT path FROM fotos WHERE id_activo=?", (row['id'],)).fetchall()
                                        docs_actuales = conn.execute("SELECT path, nombre_real FROM documentos WHERE id_activo=?", (row['id'],)).fetchall()
                                    
                                    eliminar_fotos = []
                                    for f_p in fotos_actuales:
                                        if st.checkbox(f"**ELIMINAR FOTO**: {os.path.basename(f_p[0])}", key=f"del_f_box_{f_p[0]}"):
                                            eliminar_fotos.append(f_p[0])
                                    
                                    eliminar_docs = []
                                    for d_p, d_n in docs_actuales:
                                        if st.checkbox(f"**ELIMINAR DOCUMENTO**: {d_n}", key=f"del_d_box_{d_p}"):
                                            eliminar_docs.append(d_p)
                                            
                                    st.write("➕ **AÑADIR ARCHIVOS**")
                                    f, cd = st.columns(2)
                                    nuevas_fotos = f.file_uploader("SUBIR FOTOS", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'], key=f"nf_edit_{row['id']}")
                                    nuevos_docs = cd.file_uploader("SUBIR DOCUMENTOS", accept_multiple_files=True, type=['pdf', 'docx', 'xlsx', 'xls', 'txt'], key=f"nd_edit_{row['id']}")

                                    if st.form_submit_button("💾 GUARDAR CAMBIOS"):
                                        with conectar_db() as conn:
                                            conn.execute("""UPDATE activos SET marca=?, modelo=?, estado=?, motivo_estado=?, 
                                                           ubicacion=?, descripcion=?, categoria=?, ultima_revision=?, pais=? WHERE id=?""", 
                                                         (emarc, emod, eest, emot, eubi, edesc, ecat, erev, epais, row['id']))
                                            for path in eliminar_fotos: conn.execute("DELETE FROM fotos WHERE path=?", (path,))
                                            for path in eliminar_docs: conn.execute("DELETE FROM documentos WHERE path=?", (path,))
                                        if nuevas_fotos: guardar_archivos(row['id'], nuevas_fotos, 'foto')
                                        if nuevos_docs: guardar_archivos(row['id'], nuevos_docs, 'doc')
                                        del st.session_state[f"edit_{row['id']}"]
                                        st.rerun()
                                
                                if st.button("CANCELAR EDICIÓN", key=f"canc_btn_{row['id']}"):
                                    del st.session_state[f"edit_{row['id']}"]
                                    st.rerun()

                            else:
                                col_img, col_info = st.columns([1, 1.2])
                                with col_img:
                                    with conectar_db() as conn:
                                        fotos = [f[0] for f in conn.execute("SELECT path FROM fotos WHERE id_activo=?", (row['id'],)).fetchall()]
                                    if fotos:
                                        idx = st.session_state.get(f"idx_{row['id']}", 0)
                                        st.image(fotos[idx % len(fotos)], use_container_width=True)
                                        ca, cb = st.columns(2)
                                        if ca.button("⬅️", key=f"prev_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx - 1; st.rerun()
                                        if cb.button("➡️", key=f"next_{row['id']}"): st.session_state[f"idx_{row['id']}"] = idx + 1; st.rerun()
                                    else: st.info("Sin fotos registradas.")

                                with col_info:
                                    st.write(f"**MARCA:** {row['marca']} | **MODELO:** {row['modelo']}")
                                    st.write(f"**ESTADO:** {row['estado']} | **UBICACIÓN:** {row['ubicacion']}")
                                    st.write(f"**REVISIÓN:** {row['ultima_revision']}")
                                    st.write("📄 **DOCUMENTOS**")
                                    with conectar_db() as conn:
                                        docs = conn.execute("SELECT path, nombre_real FROM documentos WHERE id_activo=?", (row['id'],)).fetchall()
                                    for i, (d_path, d_nom) in enumerate(docs):
                                        if st.button(f"👁️ Abrir {d_nom}", key=f"btn_v_{d_path}_{i}"): visor_documento(d_path, d_nom)
                                
                                st.divider()
                                c_b1, c_b2 = st.columns(2)
                                if c_b1.button("✏️ EDITAR ACTIVO", key=f"btn_edit_act_{row['id']}", use_container_width=True): 
                                    st.session_state[f"edit_{row['id']}"] = True
                                    st.rerun()
                                if c_b2.button("🗑️ ELIMINAR ACTIVO", key=f"btn_del_act_{row['id']}", use_container_width=True):
                                    confirmar_eliminar_activo(row['id'])

                    # --- BOTONES DE NAVEGACIÓN ---
                    if total_paginas > 1:
                        st.write("---")
                        c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
                        if st.session_state[pag_key] > 0:
                            if c_nav1.button("⬅️ Anterior", key=f"btn_prev_{pais_nombre}", use_container_width=True):
                                st.session_state[pag_key] -= 1
                                st.rerun()
                        if st.session_state[pag_key] < total_paginas - 1:
                            if c_nav3.button("Siguiente ➡️", key=f"btn_next_{pais_nombre}", use_container_width=True):
                                st.session_state[pag_key] += 1
                                st.rerun()
    else:
        st.info("👋 Bienvenido. Por favor, selecciona una **Categoría**.")



#--- REGISTRAR ACTIVO ---

elif menu == "REGISTRAR ACTIVO":
    st.title("📝 REGISTRO DE NUEVO ACTIVO")
    
    def realizar_limpieza_y_exito(id_activo):
        st.toast(f"✅ Activo {id_activo} guardado con éxito", icon='🎉')
        claves_a_limpiar = ["reg_id", "reg_marc", "reg_mod", "reg_mot", "reg_desc", "reg_fotos", "reg_docs"]
        for clave in claves_a_limpiar:
            if clave in st.session_state:
                del st.session_state[clave]
        import time
        time.sleep(1.2)
        st.rerun()

    with conectar_db() as conn:
        df_todas_ubis = pd.read_sql_query("SELECT nombre, pais FROM ubicaciones", conn)
    
    with st.container(border=True):
        if df_todas_ubis.empty: 
            st.warning("⚠️ **DEBE CREAR UNA UBICACIÓN PRIMERO**")
            # Botón de redirección corregido
            if st.button("📍 IR A GESTIONAR UBICACIONES", key="redir_global", use_container_width=True):
                st.session_state.navegacion_interna = "GESTIONAR UBICACIONES"
                st.rerun()
        
        rid = st.text_input("ID ACTIVO*", key="reg_id", help="Código único del activo").upper()
        
        c_p1, c_p2 = st.columns(2)
        rcat = c_p1.selectbox("CATEGORÍA*", CATEGORIAS_LISTA, key="reg_cat")
        rpais = c_p2.selectbox("PAÍS*", PAISES_LISTA, key="reg_pais")
        
        ubis_filtradas = df_todas_ubis[df_todas_ubis['pais'] == rpais]['nombre'].tolist()
        
        if not df_todas_ubis.empty and not ubis_filtradas:
            st.warning(f"⚠️ **No hay ubicaciones creadas para {rpais}**")
            # Botón de redirección específica corregido
            if st.button(f"➕ CREAR UBICACIÓN PARA {rpais}", key="redir_pais", use_container_width=True):
                st.session_state.navegacion_interna = "GESTIONAR UBICACIONES"
                st.rerun()

        c1, c2 = st.columns(2)
        rmarc = c1.text_input("MARCA", key="reg_marc").upper()
        rmod = c2.text_input("MODELO", key="reg_mod").upper()
        
        rubi = c1.selectbox("UBICACIÓN", ubis_filtradas if ubis_filtradas else ["SIN UBICACIÓN"], key="reg_ubi") 
        rest = c2.selectbox("ESTADO", ["OPERATIVO", "DAÑADO", "REPARACION"], key="reg_est")
        
        rmot = ""
        if rest in ["DAÑADO", "REPARACION"]:
            rmot = st.text_input("MOTIVO DE DAÑO / REPARACIÓN*", key="reg_mot").upper()
        
        rdesc = st.text_area("DESCRIPCIÓN / OBSERVACIONES", key="reg_desc").upper()
        
        col_f, col_d = st.columns(2)
        rfotos = col_f.file_uploader("🖼️ **CARGAR FOTOS**", accept_multiple_files=True, type=['png','jpg','jpeg'], key="reg_fotos")
        rdocs = col_d.file_uploader("📄 **CARGAR DOCUMENTOS (PDF/Office)**", accept_multiple_files=True, type=['pdf', 'docx', 'xlsx', 'txt'], key="reg_docs")
        
        if st.button("💾 GUARDAR", use_container_width=True):
            if rid and ubis_filtradas and rubi != "SIN UBICACIÓN" and rcat and (rest == "OPERATIVO" or rmot):
                try:
                    with conectar_db() as conn:
                        conn.execute("""INSERT INTO activos (id, marca, modelo, ubicacion, estado, motivo_estado, descripcion, ultima_revision, categoria, pais) 
                                     VALUES (?,?,?,?,?,?,?,?,?,?)""", 
                                     (rid, rmarc, rmod, rubi, rest, rmot, rdesc, datetime.now().date(), rcat, rpais))
                        conn.commit()
                    
                    if rfotos: guardar_archivos(rid, rfotos, 'foto')
                    if rdocs: guardar_archivos(rid, rdocs, 'doc')
                    realizar_limpieza_y_exito(rid)
                except sqlite3.IntegrityError:
                    st.error(f"❌ El ID '{rid}' ya existe en la base de datos.")
            else:
                st.error("⚠️ **Por favor rellene todos los campos marcados con (*)**.")



#--- TRASLADOS ---

elif menu == "TRASLADOS":
    st.title("🚚 TRASLADOS")
    with conectar_db() as conn:
        activos = pd.read_sql_query("SELECT id, ubicacion, pais FROM activos", conn)
        df_u = pd.read_sql_query("SELECT * FROM ubicaciones", conn)
        df_hist = pd.read_sql_query("SELECT * FROM historial ORDER BY fecha DESC", conn)
    
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
                with conectar_db() as conn:
                    conn.execute("UPDATE activos SET ubicacion=?, pais=? WHERE id=?", (tubi, tpais, sel_id))
                    conn.execute("INSERT INTO historial (id_activo, origen, destino, fecha, motivo) VALUES (?,?,?,?,?)", 
                                 (sel_id, f"{curr['pais']}-{curr['ubicacion']}", f"{tpais}-{tubi}", datetime.now(), mot))
                    conn.commit()
                st.success("Traslado exitoso."); st.rerun()

    st.divider()
    st.write("### HISTORIAL DE MOVIMIENTOS")
    if not df_hist.empty:
        # PAGINACIÓN HISTORIAL TRASLADOS
        if "pag_hist" not in st.session_state: st.session_state.pag_hist = 0
        total_hist = len(df_hist)
        total_pags_hist = (total_hist - 1) // ITEMS_POR_PAGINA + 1
        inicio_h = st.session_state.pag_hist * ITEMS_POR_PAGINA
        st.dataframe(df_hist.iloc[inicio_h : inicio_h + ITEMS_POR_PAGINA], use_container_width=True)
        
        c_h1, c_h2, c_h3 = st.columns([1, 2, 1])
        if st.session_state.pag_hist > 0:
            if c_h1.button("⬅️ Anterior", key="prev_hist", use_container_width=True):
                st.session_state.pag_hist -= 1; st.rerun()
        if st.session_state.pag_hist < total_pags_hist - 1:
            if c_h3.button("Siguiente ➡️", key="next_hist", use_container_width=True):
                st.session_state.pag_hist += 1; st.rerun()
    else: st.info("Sin movimientos registrados.")




#--- GESTIONAR UBICACIONES ---

elif menu == "GESTIONAR UBICACIONES":
    st.title("📍 GESTIONAR UBICACIONES")
    
    # Diccionario de banderas para mantener la estética
    banderas = {
        "VENEZUELA": "🇻🇪",
        "COLOMBIA": "🇨🇴",
        "ESTADOS UNIDOS": "🇺🇸"
    }

    with st.form("form_ubicaciones", clear_on_submit=True):
        st.subheader("Registrar Nueva Ubicación")
        c_u1, c_u2 = st.columns(2)
        upais = c_u1.selectbox(
            "**PAÍS:**", 
            PAISES_LISTA, 
            format_func=lambda x: f"{banderas.get(x, '🌐')} {x}"
        )
        unombre = c_u2.text_input("NOMBRE DE LA UBICACIÓN").upper()
        
        if st.form_submit_button("💾 GUARDAR UBICACIÓN", use_container_width=True):
            if unombre:
                with conectar_db() as conn:
                    try:
                        conn.execute("INSERT INTO ubicaciones (nombre, pais) VALUES (?, ?)", (unombre, upais))
                        conn.commit()
                        st.success(f"✅ ¡{unombre} guardada con éxito en {upais}!")
                        st.rerun()
                    except sqlite3.IntegrityError: 
                        st.error("❌ Esta ubicación ya existe en este país.")

    st.divider()
    st.subheader("Lista de Ubicaciones")
    
    with conectar_db() as conn:
        ubis_db = conn.execute("SELECT nombre, pais FROM ubicaciones ORDER BY rowid DESC").fetchall()
        
        if ubis_db:
            if "pag_ubi" not in st.session_state: 
                st.session_state.pag_ubi = 0
            
            total_u = len(ubis_db)
            total_pags_u = (total_u - 1) // ITEMS_POR_PAGINA + 1
            
            if st.session_state.pag_ubi >= total_pags_u:
                st.session_state.pag_ubi = 0
                
            inicio_u = st.session_state.pag_ubi * ITEMS_POR_PAGINA
            fin_u = inicio_u + ITEMS_POR_PAGINA
            
            # --- LISTADO CON DIVISORES ---
            for u in ubis_db[inicio_u : fin_u]:
                col_i, col_e, col_d = st.columns([4, 0.5, 0.5])
                bandera_actual = banderas.get(u[1], "🚩")
                
                with col_i:
                    st.markdown(f"#### {bandera_actual} {u[0]}")
                    st.caption(f"País: {u[1]}")
                
                if col_e.button("✏️", key=f"ed_u_{u[0]}_{u[1]}", help="Editar"): 
                    editar_ubicacion_dialog(u[0], u[1])
                
                if col_d.button("🗑️", key=f"de_u_{u[0]}_{u[1]}", help="Eliminar"): 
                    confirmar_eliminacion_ubi(u[0], u[1])
                
                st.divider() # <--- Divisor añadido para separar cada registro
            
            # Navegación de páginas
            if total_pags_u > 1:
                c_u1, c_u2, c_u3 = st.columns([1, 2, 1])
                if st.session_state.pag_ubi > 0:
                    if c_u1.button("⬅️ Anterior", key="prev_u", use_container_width=True):
                        st.session_state.pag_ubi -= 1
                        st.rerun()
                
                c_u2.caption(f"<center>Página {st.session_state.pag_ubi + 1} de {total_pags_u}</center>", unsafe_allow_html=True)
                
                if st.session_state.pag_ubi < total_pags_u - 1:
                    if c_u3.button("Siguiente ➡️", key="next_u", use_container_width=True):
                        st.session_state.pag_ubi += 1
                        st.rerun()
        else:
            st.info("Aún no has registrado ninguna ubicación.")





            #--- HISTORIAL ELIMINADOS ---

elif menu == "HISTORIAL ELIMINADOS":
    st.title("🗑️ ACTIVOS ELIMINADOS")
    with conectar_db() as conn:
        df_elim = pd.read_sql_query("SELECT * FROM activos_eliminados ORDER BY fecha_eliminacion DESC", conn)
    
    if not df_elim.empty:
        # PAGINACIÓN ACTIVOS ELIMINADOS
        if "pag_elim" not in st.session_state: st.session_state.pag_elim = 0
        total_e = len(df_elim)
        total_pags_e = (total_e - 1) // ITEMS_POR_PAGINA + 1
        inicio_e = st.session_state.pag_elim * ITEMS_POR_PAGINA
        
        st.dataframe(df_elim.iloc[inicio_e : inicio_e + ITEMS_POR_PAGINA], use_container_width=True)
        
        c_e1, c_e2, c_e3 = st.columns([1, 2, 1])
        if st.session_state.pag_elim > 0:
            if c_e1.button("⬅️ Anterior", key="prev_elim", use_container_width=True):
                st.session_state.pag_elim -= 1; st.rerun()
        if st.session_state.pag_elim < total_pags_e - 1:
            if c_e3.button("Siguiente ➡️", key="next_elim", use_container_width=True):
                st.session_state.pag_elim += 1; st.rerun()
    else: st.info("No hay historial de activos eliminados.")