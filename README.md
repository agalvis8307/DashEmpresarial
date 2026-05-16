# DashEmpresarial

Dashboard empresarial en Streamlit para explorar ventas, margen, clientes,
productos, alertas simples y escenarios What-if.

## Estructura
```
.
├─ app.py
├─ requirements.txt
├─ Dockerfile
├─ data/
└─ .streamlit/
   └─ config.toml
```

## Ejecutar localmente
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

La app crea `data/ventas_demo.csv` solo si no existe. No reescribe
`requirements.txt` ni la configuración del proyecto al arrancar.

## Fuentes de datos
- Demo generado automáticamente.
- CSV local con columnas: `fecha`, `region`, `canal`, `producto`, `cliente`,
  `precio`, `costo`, `cantidad`.
- Base de datos vía SQLAlchemy URL. Usa secretos o variables de entorno para
  credenciales reales.

## Pronóstico
El forecast con Prophet está desactivado por defecto para que el dashboard
cargue rápido. Actívalo en la pestaña `Forecast & Alertas` cuando lo necesites.

## Deploy en Hugging Face Spaces
1. Crea un Space y selecciona **SDK = Docker**.
2. Sube estos archivos (o conecta el repo).
3. El build usará el `Dockerfile` y expondrá el puerto 8501.
4. Tu app quedará disponible en `https://huggingface.co/spaces/<user>/<space>`.
