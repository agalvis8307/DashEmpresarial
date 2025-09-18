# Streamlit Dashboard — Hugging Face Spaces (Docker)

## Estructura
```
.
├─ app.py
├─ requirements.txt
├─ Dockerfile
└─ .streamlit/
   └─ config.toml
```

## Deploy en Hugging Face Spaces
1. Crea un Space y selecciona **SDK = Docker**.
2. Sube estos archivos (o conecta el repo).
3. El build usará el `Dockerfile` y expondrá el puerto 8501.
4. Tu app quedará disponible en `https://huggingface.co/spaces/<user>/<space>`.

> `app.py` genera un CSV demo en `data/ventas_demo.csv` automáticamente.
> Puedes conectar bases de datos vía URL en el sidebar.
