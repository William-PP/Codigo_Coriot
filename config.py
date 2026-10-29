"""Configuración central del proyecto Código Rescate."""

from pathlib import Path

# Rutas base: se calculan desde la ubicación de este archivo,
# así funcionan aunque ejecutes desde otra carpeta.
RAIZ = Path(__file__).resolve().parent
MODELO_DIR = RAIZ / "modelo"
PESOS_DIR = MODELO_DIR / "pesos"

# Modelo y dataset
MODELO_BASE = PESOS_DIR / "yolo11n.pt"
DATASET_YAML = MODELO_DIR / "rescate.yaml"

# Clases del reglamento: H = herida (naranja), S = suministros (morado)
CLASES = {0: "H", 1: "S"}

# Umbrales de inferencia
CONF_MIN = 0.25   # confianza mínima para aceptar una detección
IOU_MIN = 0.45    # solapamiento máximo entre cajas

# Fuente de video: 0 = webcam; o una URL tipo "http://IP:8000/video"
FUENTE_VIDEO = 0

# Comunicación IoT (el protocolo se define más adelante)
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883