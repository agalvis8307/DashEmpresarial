# app.py
import os
from datetime import datetime
import numpy as np
import pandas as pd

# ======================================
# Auto-setup: crea/reescribe archivos
# ======================================
def ensure_project_files(overwrite: bool = True, create_demo_csv: bool = True):
    os.makedirs(".streamlit", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    reqs = """streamlit>=1.37
pandas>=2.2
numpy>=1.26
plotly>=5.23
sqlalchemy>=2.0
psycopg2-binary>=2.9 ; platform_system!="Windows"
pyarrow>=16.0
prophet>=1.1 ; python_version>="3.9"
"""
    cfg = """[theme]
base="light"
primaryColor="#0F766E"
backgroundColor="#FFFFFF"
secondaryBackgroundColor="#F6F8FA"
textColor="#0B1220"
font="sans serif"

[client]
showErrorDetails = true

[server]
headless = true
enableXsrfProtection = true
"""

    with open("requirements.txt", "w") as f:
        f.write(reqs)

    with open(".streamlit/config.toml", "w") as f:
        f.write(cfg)

    # CSV DEMO para prueba de vida
    demo_csv_path = "data/ventas_demo.csv"
    if create_demo_csv:
        rng = np.random.default_rng(7)
        fechas = pd.date_range("2024-01-01", datetime.today().date(), freq="D")
        regiones = ["Norte", "Sur", "Este", "Oeste"]
        canales = ["Retail", "Online", "Partners"]
        productos = [f"P{i:02d}" for i in range(1, 16)]
        clientes = [f"C{i:04d}" for i in range(1, 401)]

        rows = []
        for f in fechas:
            n = rng.integers(120, 320)
            reg = rng.choice(regiones, size=n)
            can = rng.choice(canales, size=n, p=[0.5, 0.4, 0.1])
            prod = rng.choice(
                productos, size=n,
                p=np.linspace(0.16, 0.01, len(productos)) /
                  np.linspace(0.16, 0.01, len(productos)).sum()
            )
            cli = rng.choice(clientes, size=n)
            cantidad = rng.poisson(2, size=n) + 1
            precio_base = 18 + (np.array([int(p[1:]) for p in prod]) * 0.7)
            season = 1 + 0.18*np.sin(2*np.pi*(f.day_of_year)/365)
            precio = precio_base * season * rng.normal(1.0, 0.06, size=n)
            costo = precio * rng.uniform(0.55, 0.78, size=n)

            rows.append(pd.DataFrame({
                "fecha": f,
                "region": reg,
                "canal": can,
                "producto": prod,
                "cliente": cli,
                "cantidad": cantidad,
                "precio": np.round(precio, 2),
                "costo": np.round(costo, 2),
            }))

        demo_df = pd.concat(rows, ignore_index=True)
        demo_df.to_csv(demo_csv_path, index=False)

# Reescribir SIEMPRE y crear CSV demo
ensure_project_files(overwrite=True, create_demo_csv=True)

# ======================================
# Dashboard (Streamlit + Plotly)
# ======================================
import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="Dashboard Empresarial",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------- Utils ---------
def money(x: float) -> str:
    try:
        return f"${x:,.0f}"
    except Exception:
        return "-"

@st.cache_data(show_spinner=False)
def load_data(csv_path: str | None = None, sql_url: str | None = None, table: str | None = None) -> pd.DataFrame:
    """
    Carga CSV o DB (si se proporciona). Si no hay datos, simula.
    Esquema esperado:
    ['fecha','region','canal','producto','cliente','precio','costo','cantidad']
    """
    demo_default = "data/ventas_demo.csv"
    if csv_path is None:
        csv_path = demo_default
    if csv_path and os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=['fecha'])
        return df

    if sql_url and table:
        from sqlalchemy import create_engine, text
        eng = create_engine(sql_url)
        with eng.connect() as con:
            df = pd.read_sql(text(f"SELECT * FROM {table}"), con)
        if 'fecha' in df.columns:
            df['fecha'] = pd.to_datetime(df['fecha'])
        return df

    # Simulación como último recurso
    rng = np.random.default_rng(11)
    fechas = pd.date_range("2023-01-01", datetime.today().date(), freq="D")
    regiones = ["Norte", "Sur", "Este", "Oeste"]
    canales = ["Retail", "Online", "Partners"]
    productos = [f"P{i:02d}" for i in range(1, 16)]
    clientes = [f"C{i:04d}" for i in range(1, 501)]
    rows = []
    for f in fechas:
        n = rng.integers(200, 420)
        reg = rng.choice(regiones, size=n)
        can = rng.choice(canales, size=n, p=[0.45, 0.45, 0.10])
        prod = rng.choice(productos, size=n)
        cli = rng.choice(clientes, size=n)
        cantidad = rng.poisson(2, size=n) + 1
        precio_base = 20 + (np.array([int(p[1:]) for p in prod]) * 0.6)
        season = 1 + 0.15*np.sin(2*np.pi*(f.day_of_year)/365)
        precio = precio_base * season * rng.normal(1.0, 0.05, size=n)
        costo = precio * rng.uniform(0.55, 0.8, size=n)

        rows.append(pd.DataFrame({
            "fecha": f,
            "region": reg,
            "canal": can,
            "producto": prod,
            "cliente": cli,
            "cantidad": cantidad,
            "precio": np.round(precio, 2),
            "costo": np.round(costo, 2)
        }))
    return pd.concat(rows, ignore_index=True)

def compute_kpis(df: pd.DataFrame) -> dict:
    df = df.assign(ingreso=df["precio"]*df["cantidad"],
                   costo_total=df["costo"]*df["cantidad"],
                   margen=lambda d: d["ingreso"]-d["costo_total"],
                   margen_pct=lambda d: np.where(d["ingreso"]>0, d["margen"]/d["ingreso"], np.nan))
    ingresos = float(df["ingreso"].sum())
    margen = float(df["margen"].sum())
    margen_pct = (margen / ingresos) if ingresos > 0 else np.nan
    num_clientes = int(df["cliente"].nunique())
    num_ventas = int(len(df))
    arpu = (ingresos / num_clientes) if num_clientes > 0 else np.nan
    return dict(ingresos=ingresos, margen=margen, margen_pct=margen_pct,
                clientes=num_clientes, ventas=num_ventas, arpu=arpu)

def detect_anomalies(series: pd.Series, z=3.0) -> pd.Series:
    s = series.dropna()
    sd = s.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return pd.Series(False, index=series.index)
    mu = s.mean()
    flags = (np.abs((series - mu)/sd) > z)
    return flags.fillna(False)

# -------- Sidebar: Fuente & Filtros -------
st.sidebar.header("🔌 Fuente de datos")
src = st.sidebar.radio("Selecciona la fuente", ["Demo (CSV generado)", "CSV local", "Base de datos"])
csv_path = sql_url = table = None
if src == "Demo (CSV generado)":
    csv_path = "data/ventas_demo.csv"
elif src == "CSV local":
    csv_path = st.sidebar.text_input("Ruta CSV (con columna 'fecha')", "data/ventas.csv")
else:
    sql_url = st.sidebar.text_input("SQLAlchemy URL (ej. postgresql+psycopg2://user:pass@host:5432/db)", "")
    table = st.sidebar.text_input("Tabla/Vista", "ventas")

df_raw = load_data(csv_path=csv_path, sql_url=sql_url, table=table)

st.sidebar.header("🧭 Filtros")
min_f, max_f = df_raw["fecha"].min(), df_raw["fecha"].max()
rango = st.sidebar.date_input("Rango de fechas", value=(min_f, max_f), min_value=min_f, max_value=max_f)
region_sel = st.sidebar.multiselect("Región", options=sorted(df_raw["region"].unique()))
canal_sel = st.sidebar.multiselect("Canal", options=sorted(df_raw["canal"].unique()))
prod_sel = st.sidebar.multiselect("Producto", options=sorted(df_raw["producto"].unique()))

df = df_raw.copy()
df = df[(df["fecha"]>=pd.to_datetime(rango[0])) & (df["fecha"]<=pd.to_datetime(rango[1]))]
if region_sel: df = df[df["region"].isin(region_sel)]
if canal_sel:  df = df[df["canal"].isin(canal_sel)]
if prod_sel:   df = df[df["producto"].isin(prod_sel)]

kpis = compute_kpis(df)

# --------- Header ---------
st.title("📊 Dashboard Empresarial — Decisiones en Tiempo Casi Real")
st.caption("Equipo: Elenita-ALejo y compañía")
st.caption("Streamlit • Plotly • SQL/CSV • Forecast opcional • Detección de anomalías • What-if")

# --------- KPIs ---------
st.subheader("Resumen ejecutivo")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Ingresos", money(kpis["ingresos"]))
col2.metric("Margen", money(kpis["margen"]), f'{kpis["margen_pct"]*100:,.1f}%')
col3.metric("Clientes únicos", f'{kpis["clientes"]:,}')
col4.metric("Transacciones", f'{kpis["ventas"]:,}')
col5.metric("ARPU", money(kpis["arpu"]) if pd.notna(kpis["arpu"]) else "—")
df_month = (df.assign(ingreso=lambda d: d["precio"]*d["cantidad"])
              .groupby(pd.Grouper(key="fecha", freq="MS"))["ingreso"].sum().reset_index())
m_growth = (df_month["ingreso"].pct_change().iloc[-1] if len(df_month)>1 else np.nan)
col6.metric("Crec. mensual", f'{(m_growth*100):.1f}% ' if pd.notna(m_growth) else "—")

# --------- Tabs ---------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Ventas y margen", "Clientes", "Productos", "Forecast & Alertas", "What-if"
])

with tab1:
    st.markdown("### Serie temporal de ingresos y margen")
    dfa = df.assign(ingreso=lambda d: d["precio"]*d["cantidad"],
                    margen=lambda d: (d["precio"]-d["costo"])*d["cantidad"])
    ts = dfa.groupby(pd.Grouper(key="fecha", freq="W"))[["ingreso","margen"]].sum().reset_index()
    fig = px.line(ts, x="fecha", y=["ingreso","margen"], markers=True, labels={"value":"USD","variable":""})
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Desglose por segmento")
    c1, c2 = st.columns(2)
    by_region = dfa.groupby("region")[["ingreso","margen"]].sum().reset_index()
    by_canal  = dfa.groupby("canal")[["ingreso","margen"]].sum().reset_index()
    f1 = px.bar(by_region, x="region", y=["ingreso","margen"], barmode="group", title="Región")
    f2 = px.bar(by_canal,  x="canal",  y=["ingreso","margen"], barmode="group", title="Canal")
    c1.plotly_chart(f1, use_container_width=True)
    c2.plotly_chart(f2, use_container_width=True)

with tab2:
    st.markdown("### Métricas de clientes (aprox.)")
    df_cli = (df.assign(ingreso=lambda d: d["precio"]*d["cantidad"])
                .groupby([pd.Grouper(key="fecha", freq="MS"), "cliente"])["ingreso"].sum().reset_index())
    clientes_mes = df_cli.groupby("fecha")["cliente"].nunique().reset_index(name="clientes_activos")
    fig_cli = px.line(clientes_mes, x="fecha", y="clientes_activos", markers=True, title="Clientes activos / mes")
    st.plotly_chart(fig_cli, use_container_width=True)

    st.markdown("#### Top clientes por ingreso")
    top_cli = (df.assign(ingreso=lambda d: d["precio"]*d["cantidad"])
                 .groupby("cliente")["ingreso"].sum().nlargest(20).reset_index())
    fig_top = px.bar(top_cli, x="cliente", y="ingreso")
    st.plotly_chart(fig_top, use_container_width=True)

with tab3:
    st.markdown("### Portafolio de productos (Pareto 80/20)")
    prod_sum = (df.assign(ingreso=lambda d: d["precio"]*d["cantidad"])
                  .groupby("producto")["ingreso"].sum().reset_index()
                  .sort_values("ingreso", ascending=False))
    prod_sum["share"] = prod_sum["ingreso"]/prod_sum["ingreso"].sum()
    prod_sum["cum_share"] = prod_sum["share"].cumsum()
    prod_sum["Pareto_80"] = prod_sum["cum_share"]<=0.8
    c1, c2 = st.columns([2,1])
    fig_p = px.bar(prod_sum, x="producto", y="ingreso", color="Pareto_80",
                   title="Contribución por producto (80/20)")
    c1.plotly_chart(fig_p, use_container_width=True)
    c2.metric("Productos que generan ~80%", f"{int(prod_sum['Pareto_80'].sum())} / {len(prod_sum)}")

with tab4:
    st.markdown("### Detección de anomalías y pronóstico")
    dfts = (df.assign(ingreso=lambda d: d["precio"]*d["cantidad"])
              .groupby(pd.Grouper(key="fecha", freq="D"))["ingreso"].sum().reset_index())
    dfts["anomaly"] = detect_anomalies(dfts["ingreso"], z=3.0)
    f_a = px.scatter(dfts, x="fecha", y="ingreso", color="anomaly", title="Anomalías (z>3)")
    st.plotly_chart(f_a, use_container_width=True)

    st.markdown("#### Pronóstico (Prophet, opcional)")
    try:
        from prophet import Prophet
        dfp = dfts.rename(columns={"fecha":"ds","ingreso":"y"})
        m = Prophet(seasonality_mode="multiplicative", weekly_seasonality=True, yearly_seasonality=True)
        m.fit(dfp)
        future = m.make_future_dataframe(periods=60)
        forecast = m.predict(future)
        fig_fc = px.line(forecast, x="ds", y=["yhat","yhat_lower","yhat_upper"], title="Forecast 60 días")
        fig_fc.add_scatter(x=dfp["ds"], y=dfp["y"], mode="markers", name="histórico")
        st.plotly_chart(fig_fc, use_container_width=True)
    except Exception as e:
        st.info("Prophet no está disponible en este entorno. Instálalo para habilitar el forecast.")
        st.code(str(e))

with tab5:
    st.markdown("### Simulador What-if (precio, costo, descuento)")
    dfa = df.assign(ingreso=lambda d: d["precio"]*d["cantidad"],
                    costo_total=lambda d: d["costo"]*d["cantidad"])
    base_ing = float(dfa["ingreso"].sum())
    base_margin = float((dfa["ingreso"] - dfa["costo_total"]).sum())

    c1, c2, c3 = st.columns(3)
    d_precio = c1.slider("Δ% precio", -20, 20, 0, step=1)
    d_costo  = c2.slider("Δ% costo",  -20, 20, 0, step=1)
    desc     = c3.slider("Descuento adicional (%)", 0, 30, 0, step=1)

    factor_p = (1 + d_precio/100) * (1 - desc/100)
    factor_c = (1 + d_costo/100)

    new_ing = float((dfa["precio"]*factor_p * dfa["cantidad"]).sum())
    new_cost = float((dfa["costo"]*factor_c * dfa["cantidad"]).sum())
    delta_ing = new_ing - base_ing
    delta_margin = (new_ing - new_cost) - base_margin

    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos (sim)", money(new_ing), f"{(delta_ing/base_ing)*100:,.1f}%")
    k2.metric("Margen (sim)", money(new_ing - new_cost), f"{(delta_margin/base_margin)*100:,.1f}%")
    k3.metric("Spread precio-costo", f"{(factor_p/factor_c - 1)*100:,.1f}% pts")

st.markdown("---")
st.caption("© Tu Empresa — Dashboard con Streamlit. Café en mano = mejor ROI ☕️.")
