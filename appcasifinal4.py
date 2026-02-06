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

        # Definición de Clave Primaria Compuesta: (nombre, pais)
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

def limpiar_campos_registro():
    campos = ["reg_id", "reg_marc", "reg_mod", "reg_mot", "reg_desc", "reg_fotos", "reg_docs"]
    for campo in campos:
        if campo in st.session_state:
            st.session_state[campo] = "" if "fotos" not in campo and "docs" not in campo else None

# --- DIÁLOGOS ---
@st.dialog("VISOR")
def visor_documento(path, nombre):
    st.write(f"### {nombre}")
    if path.lower().endswith('.pdf'): display_pdf(path)
    else: st.info("**Vista previa solo disponible para archivos PDF.**")
    with open(path, "rb") as f: st.download_button("📥 DESCARGAR", f, file_name=nombre, key=f"dl_{path}")

@st.dialog("CONFIRMAR ELIMINACIÓN DE ACTIVO")
def confirmar_eliminar_activo(activo_id):
    st.error(f"⚠️ ¿Desea eliminar permanentemente el activo **{activo_id}**?")
    if st.button("SÍ, ELIMINAR", use_container_width=True):
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
    if st.button("CONFIRMAR"):
        with conectar_db() as conn:
            conn.execute("DELETE FROM ubicaciones WHERE nombre=? AND pais=?", (nombre, pais))
            conn.commit()
        st.success("Ubicación eliminada."); st.rerun()

@st.dialog("EDITAR UBICACIÓN")
def editar_ubicacion_dialog(nombre_actual, pais_actual):
    st.write(f"Modificando nombre de la ubicación en **{pais_actual}**")
    nuevo_nombre = st.text_input("NUEVO NOMBRE", value=nombre_actual).upper()
    
    st.warning("⚠️ **Nota: Al cambiar el nombre, todos los activos asociados a esta ubicación se actualizarán automáticamente.**")
    
    if st.button("GUARDAR CAMBIOS", use_container_width=True):
        if nuevo_nombre and nuevo_nombre != nombre_actual:
            with conectar_db() as conn:
                try:
                    # 1. Actualizar el nombre en la tabla de ubicaciones
                    conn.execute("UPDATE ubicaciones SET nombre=? WHERE nombre=? AND pais=?", 
                                 (nuevo_nombre, nombre_actual, pais_actual))
                    # 2. Actualizar los activos vinculados para mantener integridad
                    conn.execute("UPDATE activos SET ubicacion=? WHERE ubicacion=? AND pais=?", 
                                 (nuevo_nombre, nombre_actual, pais_actual))
                    conn.commit()
                    st.success("**Ubicación actualizada con éxito.**")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"❌ **Error: Ya existe una ubicación llamada '{nuevo_nombre}' en {pais_actual}.**")
        elif nuevo_nombre == nombre_actual:
            st.info("No hay cambios detectados.")
        else:
            st.error("**El nombre no puede estar vacío.**")

# --- NAVEGACIÓN ---
menu = st.sidebar.radio("MENÚ", ["DASHBOARD", "REGISTRAR ACTIVO", "TRASLADOS", "GESTIONAR UBICACIONES", "HISTORIAL ELIMINADOS"])

if menu == "DASHBOARD":
    col_titulo, col_logo = st.columns([3, 1])
    with col_titulo: st.image("logotrieca.png", width=150)
    with col_logo: st.title("ACTIVOS") 
    
    with conectar_db() as conn:
        df = pd.read_sql_query("SELECT * FROM activos", conn)
        ubis = pd.read_sql_query("SELECT nombre FROM ubicaciones", conn)['nombre'].tolist()

    f_cat = st.selectbox("**SELECCIONAR CATEGORÍA**", ["SELECCIONAR"] + CATEGORIAS_LISTA)

    if f_cat != "SELECCIONAR":
        st.subheader(f"🟦 {f_cat}")
        with st.container(border=True):
            st.markdown("### 🔍 BUSCAR POR:")
            c_f1, c_f2, c_f3 = st.columns(3)
            f_est = c_f1.selectbox("ESTADO", ["TODOS", "OPERATIVO", "DAÑADO", "REPARACION"])
            f_ubi = c_f2.selectbox("UBICACIÓN", ["TODAS"] + ubis)
            f_busq = c_f3.text_input("CÓDIGO O MARCA").upper()

        df_f = df[df['categoria'] == f_cat].copy()
        if f_est != "TODOS": df_f = df_f[df_f['estado'] == f_est]
        if f_ubi != "TODAS": df_f = df_f[df_f['ubicacion'] == f_ubi]
        if f_busq: df_f = df_f[df_f['id'].str.contains(f_busq, na=False) | df_f['marca'].str.contains(f_busq, na=False)]
        
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res4.metric("**TOTAL**", len(df_f))
        c_res1.metric("**VENEZUELA** 🇻🇪", len(df_f[df_f['pais'] == "VENEZUELA"]))
        c_res2.metric("**COLOMBIA** 🇨🇴", len(df_f[df_f['pais'] == "COLOMBIA"]))
        c_res3.metric("**EE.UU.** 🇺🇸", len(df_f[df_f['pais'] == "ESTADOS UNIDOS"]))
        st.divider()

        tabs_paises = st.tabs(PAISES_LISTA)

        for i, pais_nombre in enumerate(PAISES_LISTA):
            with tabs_paises[i]:
                df_pais = df_f[df_f['pais'] == pais_nombre]

                if df_pais.empty:
                    st.info(f"No hay activos registrados en '{f_cat}' para {pais_nombre}.")
                else:
                    # --- LÓGICA DE PAGINACIÓN (5 en 5) ---
                    items_por_pagina = 5
                    total_activos = len(df_pais)
                    num_paginas = (total_activos + items_por_pagina - 1) // items_por_pagina
                    
                    if num_paginas > 1:
                        col_p1, col_p2 = st.columns([1, 4])
                        pagina_actual = col_p1.number_input(f"Página (1-{num_paginas})", 1, num_paginas, 1, key=f"pag_{pais_nombre}")
                    else:
                        pagina_actual = 1
                    
                    inicio = (pagina_actual - 1) * items_por_pagina
                    fin = inicio + items_por_pagina
                    df_display = df_pais.iloc[inicio:fin]
                    # ---------------------------------------

                    for _, row in df_display.iterrows():
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
                                    eubi = st.selectbox("UBICACIÓN", ubis, index=ubis.index(row['ubicacion']) if row['ubicacion'] in ubis else 0)
                                    edesc = st.text_area("DESCRIPCIÓN", str(row['descripcion'] or "")).upper()

                                    if st.form_submit_button("💾 GUARDAR CAMBIOS"):
                                        with conectar_db() as conn:
                                            conn.execute("""UPDATE activos SET marca=?, modelo=?, estado=?, motivo_estado=?, 
                                                           ubicacion=?, descripcion=?, categoria=?, ultima_revision=?, pais=? WHERE id=?""", 
                                                         (emarc, emod, eest, emot, eubi, edesc, ecat, erev, epais, row['id']))
                                            conn.commit()
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
    else:
        st.info("👋 Bienvenido. Por favor, selecciona una **Categoría**.")

elif menu == "REGISTRAR ACTIVO":
    st.title("📝 REGISTRO DE NUEVO ACTIVO")
    
    # Centralizamos la limpieza en una función que no cause conflictos de estado
    def realizar_limpieza_y_exito(id_activo):
        st.toast(f"✅ Activo {id_activo} guardado con éxito", icon='🎉')
        # Borramos las claves del estado para que los widgets se reinicien
        claves_a_limpiar = ["reg_id", "reg_marc", "reg_mod", "reg_mot", "reg_desc", "reg_fotos", "reg_docs"]
        for clave in claves_a_limpiar:
            if clave in st.session_state:
                del st.session_state[clave]
        # Esperamos un momento para que el usuario vea el toast antes del rerun
        import time
        time.sleep(1.2)
        st.rerun()

    with conectar_db() as conn:
        df_todas_ubis = pd.read_sql_query("SELECT nombre, pais FROM ubicaciones", conn)
    
    with st.container(border=True):
        if df_todas_ubis.empty: 
            st.warning("⚠️ **DEBE CREAR UNA UBICACIÓN PRIMERO**")
        
        rid = st.text_input("ID ACTIVO*", key="reg_id", help="Código único del activo").upper()
        
        c_p1, c_p2 = st.columns(2)
        rcat = c_p1.selectbox("CATEGORÍA*", CATEGORIAS_LISTA, key="reg_cat")
        rpais = c_p2.selectbox("PAÍS*", PAISES_LISTA, key="reg_pais")
        
        # Filtrado dinámico de ubicaciones por país
        ubis_filtradas = df_todas_ubis[df_todas_ubis['pais'] == rpais]['nombre'].tolist()
        
        if not df_todas_ubis.empty and not ubis_filtradas:
            st.warning(f"⚠️**No hay ubicaciones creadas para {rpais}**")

        c1, c2 = st.columns(2)
        rmarc = c1.text_input("MARCA", key="reg_marc").upper()
        rmod = c2.text_input("MODELO", key="reg_mod").upper()
        
        rubi = c1.selectbox("UBICACIÓN", ubis_filtradas if ubis_filtradas else ["SIN UBICACIÓN"], key="reg_ubi") 
        rest = c2.selectbox("ESTADO", ["OPERATIVO", "DAÑADO", "REPARACION"], key="reg_est")
        
        rmot = ""
        if rest in ["DAÑADO", "REPARACION"]:
            rmot = st.text_input("MOTIVO DE DAÑO / REPARACIÓN*", key="reg_mot").upper()
        
        rdesc = st.text_area("DESCRIPCIÓN ADICIONAL", key="reg_desc").upper()
        
        col_f, col_d = st.columns(2)
        rfotos = col_f.file_uploader("🖼️ FOTOS", accept_multiple_files=True, type=['png','jpg','jpeg'], key="reg_fotos")
        rdocs = col_d.file_uploader("📄 DOCUMENTOS (PDF/Office)", accept_multiple_files=True, type=['pdf', 'docx', 'xlsx', 'txt'], key="reg_docs")
        
        if st.button("💾 GUARDAR", use_container_width=True):
            # Validación de campos obligatorios
            if rid and ubis_filtradas and rubi != "SIN UBICACIÓN" and rcat and (rest == "OPERATIVO" or rmot):
                try:
                    with conectar_db() as conn:
                        conn.execute("""INSERT INTO activos (id, marca, modelo, ubicacion, estado, motivo_estado, descripcion, ultima_revision, categoria, pais) 
                                     VALUES (?,?,?,?,?,?,?,?,?,?)""", 
                                     (rid, rmarc, rmod, rubi, rest, rmot, rdesc, datetime.now().date(), rcat, rpais))
                        conn.commit()
                    
                    if rfotos: guardar_archivos(rid, rfotos, 'foto')
                    if rdocs: guardar_archivos(rid, rdocs, 'doc')
                    
                    # Ejecutamos la limpieza y notificamos
                    realizar_limpieza_y_exito(rid)
                    
                except sqlite3.IntegrityError:
                    st.error(f"❌ El ID '{rid}' ya existe en la base de datos.")
            else:
                st.error("⚠️ **Por favor rellene todos los campos marcados con (*)**.")

elif menu == "TRASLADOS":
    st.title("🚚 TRASLADOS")
    with conectar_db() as conn:
        # Cargamos todos los activos y ubicaciones para el filtrado dinámico
        activos = pd.read_sql_query("SELECT id, ubicacion, pais FROM activos", conn)
        df_u = pd.read_sql_query("SELECT * FROM ubicaciones", conn)
    
    # 1. Selección de País de Origen
    st.subheader("Origen")
    opais = st.selectbox("PAÍS ORIGEN", PAISES_LISTA)
    
    # 2. Filtrar activos que pertenecen únicamente al país de origen seleccionado
    activos_filtrados = activos[activos['pais'] == opais]
    
    if not activos_filtrados.empty:
        # 3. Selección de activo basada en el filtro anterior
        sel_id = st.selectbox("SELECCIONE ACTIVO", activos_filtrados['id'])
        curr = activos_filtrados[activos_filtrados['id'] == sel_id].iloc[0]
        
        st.info(f"📍 Ubicación Actual: {curr['pais']} - {curr['ubicacion']}")
        st.divider()
        
        # 4. Selección de Destino
        st.subheader("Destino")
        ct1, ct2 = st.columns(2)
        tpais = ct1.selectbox("PAÍS DESTINO", PAISES_LISTA)
        
        # Filtrar ubicaciones disponibles en el país destino seleccionado
        u_dest_list = df_u[df_u['pais'] == tpais]['nombre'].tolist()
        tubi = ct2.selectbox("UBICACIÓN DESTINO", u_dest_list if u_dest_list else ["SIN OPCIONES"])
        
        mot = st.text_input("MOTIVO").upper()
        
        if st.button("PROCESAR", use_container_width=True):
            if tubi != "SIN OPCIONES":
                with conectar_db() as conn:
                    conn.execute("UPDATE activos SET ubicacion=?, pais=? WHERE id=?", (tubi, tpais, sel_id))
                    conn.execute("INSERT INTO historial (id_activo, origen, destino, fecha, motivo) VALUES (?,?,?,?,?)", 
                                 (sel_id, f"{curr['pais']}-{curr['ubicacion']}", f"{tpais}-{tubi}", datetime.now(), mot))
                    conn.commit()
                st.success(f"Traslado del activo {sel_id} realizado con éxito."); st.rerun()
            else:
                st.error("Error: No se ha seleccionado una ubicación de destino válida.")
    else:
        st.warning(f"⚠️ No hay activos registrados para **{opais}**.")
        st.write("---")


    st.write("### HISTORIAL DE MOVIMIENTOS")
    with conectar_db() as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM historial ORDER BY fecha DESC", conn), use_container_width=True)

elif menu == "GESTIONAR UBICACIONES":
    st.title("📍 CREAR UBICACIÓN")
    
    # Formulario original sin cambios
    with st.form("form_ubicaciones", clear_on_submit=True):
        c_u1, c_u2 = st.columns(2)
        upais = c_u1.selectbox("**REGISTRAR UBICACIÓN EN:**", PAISES_LISTA)
        unombre = c_u2.text_input("NOMBRE DE LA NUEVA UBICACIÓN (Ej: ALMACÉN GENERAL)").upper()
        btn_add = st.form_submit_button("💾 GUARDAR", use_container_width=True)
        if btn_add:
            if unombre:
                with conectar_db() as conn:
                    try:
                        conn.execute("INSERT INTO ubicaciones (nombre, pais) VALUES (?, ?)", (unombre, upais))
                        conn.commit()
                        st.success(f"✅ Registrado: {unombre} en {upais}"); st.rerun()
                    except sqlite3.IntegrityError: st.error("Ya existe.")
            else: st.warning("Escriba un nombre.")

    st.divider()
    st.subheader("Ubicaciones Registradas")
    
    with conectar_db() as conn:
        ubis_db = conn.execute("SELECT nombre, pais FROM ubicaciones ORDER BY pais ASC, nombre ASC").fetchall()
        
        if not ubis_db:
            st.info("No hay ubicaciones registradas.")
        else:
            # --- LÓGICA DE PAGINACIÓN (5 en 5) ---
            items_por_pagina = 5
            if "pag_ubi" not in st.session_state:
                st.session_state.pag_ubi = 0
            
            total_items = len(ubis_db)
            total_paginas = (total_items - 1) // items_por_pagina + 1
            
            # Ajuste de seguridad por si se eliminan registros y el índice queda fuera
            if st.session_state.pag_ubi >= total_paginas:
                st.session_state.pag_ubi = max(0, total_paginas - 1)
            
            inicio = st.session_state.pag_ubi * items_por_pagina
            fin = inicio + items_por_pagina
            ubis_pagina = ubis_db[inicio:fin]
            
            st.caption(f"Mostrando página {st.session_state.pag_ubi + 1} de {total_paginas} (Total: {total_items} ubicaciones)")

            for u in ubis_pagina:
                col_info, col_edit, col_del = st.columns([4, 0.5, 0.5])
                col_info.write(f"🚩 **{u[1]}** ➔ {u[0]}")
                
                if col_edit.button("✏️", key=f"edit_btn_{u[0]}_{u[1]}"):
                    editar_ubicacion_dialog(u[0], u[1])
                
                if col_del.button("🗑️", key=f"del_{u[0]}_{u[1]}"):
                    cant = conn.execute("SELECT COUNT(*) FROM activos WHERE ubicacion=? AND pais=?", (u[0], u[1])).fetchone()[0]
                    if cant > 0: st.error(f"No se puede eliminar: tiene {cant} activos.")
                    else: confirmar_eliminacion_ubi(u[0], u[1])
            
            # Controles de Navegación
            st.write("---")
            c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
            
            if st.session_state.pag_ubi > 0:
                if c_nav1.button("⬅️ Anterior", use_container_width=True):
                    st.session_state.pag_ubi -= 1; st.rerun()
            
            if st.session_state.pag_ubi < total_paginas - 1:
                if c_nav3.button("Siguiente ➡️", use_container_width=True):
                    st.session_state.pag_ubi += 1; st.rerun()

elif menu == "HISTORIAL ELIMINADOS":
    st.title("🗑️ ACTIVOS ELIMINADOS")
    with conectar_db() as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM activos_eliminados", conn), use_container_width=True)