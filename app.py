from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


DATA_DIR = Path("data")
DEMO_CSV_PATH = DATA_DIR / "ventas_demo.csv"
REQUIRED_COLUMNS = ["fecha", "region", "canal", "producto", "cliente", "precio", "costo", "cantidad"]
NUMERIC_COLUMNS = ["precio", "costo", "cantidad"]
SAFE_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


st.set_page_config(
    page_title="Dashboard Empresarial",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def money(x: float) -> str:
    try:
        return f"${x:,.0f}"
    except Exception:
        return "-"


def generate_demo_data(end_date: datetime | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    end_date = end_date or datetime.today()
    fechas = pd.date_range("2024-01-01", end_date.date(), freq="D")
    regiones = ["Norte", "Sur", "Este", "Oeste"]
    canales = ["Retail", "Online", "Partners"]
    productos = [f"P{i:02d}" for i in range(1, 16)]
    clientes = [f"C{i:04d}" for i in range(1, 401)]
    product_weights = np.linspace(0.16, 0.01, len(productos))
    product_weights = product_weights / product_weights.sum()

    rows = []
    for fecha in fechas:
        n = rng.integers(120, 320)
        prod = rng.choice(productos, size=n, p=product_weights)
        precio_base = 18 + (np.array([int(p[1:]) for p in prod]) * 0.7)
        season = 1 + 0.18 * np.sin(2 * np.pi * fecha.day_of_year / 365)
        precio = precio_base * season * rng.normal(1.0, 0.06, size=n)

        rows.append(
            pd.DataFrame(
                {
                    "fecha": fecha,
                    "region": rng.choice(regiones, size=n),
                    "canal": rng.choice(canales, size=n, p=[0.5, 0.4, 0.1]),
                    "producto": prod,
                    "cliente": rng.choice(clientes, size=n),
                    "cantidad": rng.poisson(2, size=n) + 1,
                    "precio": np.round(precio, 2),
                    "costo": np.round(precio * rng.uniform(0.55, 0.78, size=n), 2),
                }
            )
        )

    return pd.concat(rows, ignore_index=True)


def ensure_demo_csv(path: Path = DEMO_CSV_PATH) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        generate_demo_data().to_csv(path, index=False)
    return path


def validate_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=["fecha", *NUMERIC_COLUMNS])
    if df.empty:
        raise ValueError("La fuente de datos no contiene filas válidas después de la limpieza.")

    for column in ["region", "canal", "producto", "cliente"]:
        df[column] = df[column].astype(str).str.strip()

    return df


def quote_table_name(table: str) -> str:
    table = table.strip()
    if not SAFE_TABLE_NAME.match(table):
        raise ValueError("Nombre de tabla inválido. Usa solo letras, números, guiones bajos y un punto opcional.")
    return ".".join(f'"{part}"' for part in table.split("."))


@st.cache_data(show_spinner=False)
def load_data(csv_path: str | None = None, sql_url: str | None = None, table: str | None = None) -> pd.DataFrame:
    if csv_path:
        path = Path(csv_path)
        if path == DEMO_CSV_PATH:
            path = ensure_demo_csv(path)
        if not path.exists():
            raise FileNotFoundError(f"No encontré el archivo CSV: {path}")
        return validate_dataset(pd.read_csv(path))

    if sql_url and table:
        from sqlalchemy import create_engine, text

        safe_table = quote_table_name(table)
        engine = create_engine(sql_url)
        with engine.connect() as con:
            df = pd.read_sql(text(f"SELECT * FROM {safe_table}"), con)
        return validate_dataset(df)

    return validate_dataset(generate_demo_data())


def compute_kpis(df: pd.DataFrame) -> dict:
    df = df.assign(
        ingreso=df["precio"] * df["cantidad"],
        costo_total=df["costo"] * df["cantidad"],
        margen=lambda d: d["ingreso"] - d["costo_total"],
    )
    ingresos = float(df["ingreso"].sum())
    margen = float(df["margen"].sum())
    margen_pct = (margen / ingresos) if ingresos > 0 else np.nan
    clientes = int(df["cliente"].nunique())
    ventas = int(len(df))
    arpu = (ingresos / clientes) if clientes > 0 else np.nan
    return dict(ingresos=ingresos, margen=margen, margen_pct=margen_pct, clientes=clientes, ventas=ventas, arpu=arpu)


def detect_anomalies(series: pd.Series, z: float = 3.0) -> pd.Series:
    s = series.dropna()
    sd = s.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return pd.Series(False, index=series.index)
    flags = np.abs((series - s.mean()) / sd) > z
    return flags.fillna(False)


def add_business_metrics(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(
        ingreso=lambda d: d["precio"] * d["cantidad"],
        costo_total=lambda d: d["costo"] * d["cantidad"],
        margen=lambda d: (d["precio"] - d["costo"]) * d["cantidad"],
    )


def monthly_growth(df: pd.DataFrame) -> float:
    monthly = (
        df.assign(ingreso=lambda d: d["precio"] * d["cantidad"])
        .groupby(pd.Grouper(key="fecha", freq="MS"))["ingreso"]
        .sum()
        .reset_index()
    )
    if len(monthly) < 2:
        return np.nan

    current_month = pd.Timestamp.today().to_period("M")
    completed = monthly[monthly["fecha"].dt.to_period("M") < current_month]
    basis = completed if len(completed) >= 2 else monthly
    return float(basis["ingreso"].pct_change().iloc[-1])


@st.cache_data(show_spinner=False)
def build_forecast(daily_df: pd.DataFrame, periods: int = 60) -> pd.DataFrame:
    mpl_cache = Path(os.environ.get("MPLCONFIGDIR", "/tmp/matplotlib-cache"))
    mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))

    from prophet import Prophet

    dfp = daily_df.rename(columns={"fecha": "ds", "ingreso": "y"})[["ds", "y"]].dropna()
    if len(dfp) < 30:
        raise ValueError("Se necesitan al menos 30 días de datos para calcular el pronóstico.")

    model = Prophet(seasonality_mode="multiplicative", weekly_seasonality=True, yearly_seasonality=True)
    model.fit(dfp)
    future = model.make_future_dataframe(periods=periods)
    return model.predict(future)


st.sidebar.header("🔌 Fuente de datos")
src = st.sidebar.radio("Selecciona la fuente", ["Demo (CSV generado)", "CSV local", "Base de datos"])
csv_path = sql_url = table = None
if src == "Demo (CSV generado)":
    csv_path = str(DEMO_CSV_PATH)
elif src == "CSV local":
    csv_path = st.sidebar.text_input("Ruta CSV", "data/ventas.csv")
else:
    sql_url = st.sidebar.text_input("SQLAlchemy URL", "", type="password")
    table = st.sidebar.text_input("Tabla o vista", "ventas")

try:
    df_raw = load_data(csv_path=csv_path, sql_url=sql_url, table=table)
except Exception as exc:
    st.error("No pude cargar la fuente de datos.")
    st.caption(str(exc))
    st.stop()

st.sidebar.header("🧭 Filtros")
min_f, max_f = df_raw["fecha"].min().date(), df_raw["fecha"].max().date()
rango = st.sidebar.date_input("Rango de fechas", value=(min_f, max_f), min_value=min_f, max_value=max_f)
region_sel = st.sidebar.multiselect("Región", options=sorted(df_raw["region"].unique()))
canal_sel = st.sidebar.multiselect("Canal", options=sorted(df_raw["canal"].unique()))
prod_sel = st.sidebar.multiselect("Producto", options=sorted(df_raw["producto"].unique()))

if isinstance(rango, tuple) and len(rango) == 2:
    start_date, end_date = rango
else:
    start_date = end_date = rango

df = df_raw.copy()
df = df[(df["fecha"] >= pd.to_datetime(start_date)) & (df["fecha"] <= pd.to_datetime(end_date))]
if region_sel:
    df = df[df["region"].isin(region_sel)]
if canal_sel:
    df = df[df["canal"].isin(canal_sel)]
if prod_sel:
    df = df[df["producto"].isin(prod_sel)]

st.title("📊 Dashboard Empresarial — Decisiones en Tiempo Casi Real")
st.caption("Equipo: Elenita-ALejo y compañía")
st.caption("Streamlit • Plotly • SQL/CSV • Forecast bajo demanda • Detección de anomalías • What-if")

if df.empty:
    st.warning("No hay registros para los filtros seleccionados.")
    st.stop()

kpis = compute_kpis(df)
df_metrics = add_business_metrics(df)

st.subheader("Resumen ejecutivo")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Ingresos", money(kpis["ingresos"]))
col2.metric("Margen", money(kpis["margen"]), f'{kpis["margen_pct"] * 100:,.1f}%')
col3.metric("Clientes únicos", f'{kpis["clientes"]:,}')
col4.metric("Transacciones", f'{kpis["ventas"]:,}')
col5.metric("ARPU", money(kpis["arpu"]) if pd.notna(kpis["arpu"]) else "—")
m_growth = monthly_growth(df)
col6.metric("Crec. mensual", f"{m_growth * 100:.1f}%" if pd.notna(m_growth) else "—")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Ventas y margen", "Clientes", "Productos", "Forecast & Alertas", "What-if"])

with tab1:
    st.markdown("### Serie temporal de ingresos y margen")
    ts = df_metrics.groupby(pd.Grouper(key="fecha", freq="W"))[["ingreso", "margen"]].sum().reset_index()
    fig = px.line(ts, x="fecha", y=["ingreso", "margen"], markers=True, labels={"value": "USD", "variable": ""})
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Desglose por segmento")
    c1, c2 = st.columns(2)
    by_region = df_metrics.groupby("region")[["ingreso", "margen"]].sum().reset_index()
    by_canal = df_metrics.groupby("canal")[["ingreso", "margen"]].sum().reset_index()
    f1 = px.bar(by_region, x="region", y=["ingreso", "margen"], barmode="group", title="Región")
    f2 = px.bar(by_canal, x="canal", y=["ingreso", "margen"], barmode="group", title="Canal")
    c1.plotly_chart(f1, width="stretch")
    c2.plotly_chart(f2, width="stretch")

with tab2:
    st.markdown("### Métricas de clientes")
    df_cli = df_metrics.groupby([pd.Grouper(key="fecha", freq="MS"), "cliente"])["ingreso"].sum().reset_index()
    clientes_mes = df_cli.groupby("fecha")["cliente"].nunique().reset_index(name="clientes_activos")
    fig_cli = px.line(clientes_mes, x="fecha", y="clientes_activos", markers=True, title="Clientes activos / mes")
    st.plotly_chart(fig_cli, width="stretch")

    st.markdown("#### Top clientes por ingreso")
    top_cli = df_metrics.groupby("cliente")["ingreso"].sum().nlargest(20).reset_index()
    fig_top = px.bar(top_cli, x="cliente", y="ingreso")
    st.plotly_chart(fig_top, width="stretch")

with tab3:
    st.markdown("### Portafolio de productos (Pareto 80/20)")
    prod_sum = df_metrics.groupby("producto")["ingreso"].sum().reset_index().sort_values("ingreso", ascending=False)
    prod_sum["share"] = prod_sum["ingreso"] / prod_sum["ingreso"].sum()
    prod_sum["cum_share"] = prod_sum["share"].cumsum()
    prod_sum["Pareto_80"] = prod_sum["cum_share"] <= 0.8
    c1, c2 = st.columns([2, 1])
    fig_p = px.bar(prod_sum, x="producto", y="ingreso", color="Pareto_80", title="Contribución por producto (80/20)")
    c1.plotly_chart(fig_p, width="stretch")
    c2.metric("Productos que generan ~80%", f"{int(prod_sum['Pareto_80'].sum())} / {len(prod_sum)}")

with tab4:
    st.markdown("### Detección de anomalías y pronóstico")
    dfts = df_metrics.groupby(pd.Grouper(key="fecha", freq="D"))["ingreso"].sum().reset_index()
    dfts["anomaly"] = detect_anomalies(dfts["ingreso"], z=3.0)
    f_a = px.scatter(dfts, x="fecha", y="ingreso", color="anomaly", title="Anomalías (z>3)")
    st.plotly_chart(f_a, width="stretch")

    st.markdown("#### Pronóstico")
    forecast_periods = st.slider("Días a pronosticar", 15, 120, 60, step=15)
    run_forecast = st.toggle("Calcular pronóstico con Prophet", value=False)
    if run_forecast:
        try:
            with st.spinner("Calculando pronóstico..."):
                forecast = build_forecast(dfts, periods=forecast_periods)
            fig_fc = px.line(forecast, x="ds", y=["yhat", "yhat_lower", "yhat_upper"], title=f"Forecast {forecast_periods} días")
            fig_fc.add_scatter(x=dfts["fecha"], y=dfts["ingreso"], mode="markers", name="histórico")
            st.plotly_chart(fig_fc, width="stretch")
        except Exception as exc:
            st.info("No pude calcular el pronóstico en este entorno.")
            st.code(str(exc))
    else:
        st.info("Activa el pronóstico solo cuando lo necesites; así la app carga más rápido.")

with tab5:
    st.markdown("### Simulador What-if (precio, costo, descuento)")
    base_ing = float(df_metrics["ingreso"].sum())
    base_margin = float((df_metrics["ingreso"] - df_metrics["costo_total"]).sum())

    c1, c2, c3 = st.columns(3)
    d_precio = c1.slider("Δ% precio", -20, 20, 0, step=1)
    d_costo = c2.slider("Δ% costo", -20, 20, 0, step=1)
    desc = c3.slider("Descuento adicional (%)", 0, 30, 0, step=1)

    factor_p = (1 + d_precio / 100) * (1 - desc / 100)
    factor_c = 1 + d_costo / 100
    new_ing = float((df_metrics["precio"] * factor_p * df_metrics["cantidad"]).sum())
    new_cost = float((df_metrics["costo"] * factor_c * df_metrics["cantidad"]).sum())
    new_margin = new_ing - new_cost
    delta_ing_pct = ((new_ing - base_ing) / base_ing) if base_ing else np.nan
    delta_margin_pct = ((new_margin - base_margin) / base_margin) if base_margin else np.nan

    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos (sim)", money(new_ing), f"{delta_ing_pct * 100:,.1f}%" if pd.notna(delta_ing_pct) else "—")
    k2.metric("Margen (sim)", money(new_margin), f"{delta_margin_pct * 100:,.1f}%" if pd.notna(delta_margin_pct) else "—")
    k3.metric("Spread precio-costo", f"{(factor_p / factor_c - 1) * 100:,.1f}% pts")

st.markdown("---")
st.caption("© Equipo de Elenita-ALejo y compañía — Dashboard con Streamlit.")
