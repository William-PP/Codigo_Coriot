"""Configuración central del proyecto Código Rescate (v2)."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas base (se calculan desde este archivo, no desde el directorio actual)
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
MODELO_DIR = RAIZ / "modelo"
PESOS_DIR = MODELO_DIR / "pesos"

# Modelo y dataset
MODELO_BASE = PESOS_DIR / "yolo11n.pt"
PESOS_ENTRENADO = PESOS_DIR / "rescate.pt"   # sale de modelo/entrenar.py
DATASET_YAML = MODELO_DIR / "rescate.yaml"

# Clases del reglamento: H = herida (naranja), S = suministros (morado)
CLASES = {0: "H", 1: "S"}

# Umbrales de inferencia
CONF_MIN = 0.25   # confianza mínima para aceptar una detección
IOU_MIN = 0.45    # solapamiento máximo entre cajas

# ---------------------------------------------------------------------------
# Fuente de video
# ---------------------------------------------------------------------------
# Se cambia sin tocar el código con la variable de entorno CORIOT_VIDEO:
#   $env:CORIOT_VIDEO = "0"                      # webcam de la laptop
#   $env:CORIOT_VIDEO = "http://IP:8080/video"   # celular con IP Webcam
FUENTE_VIDEO_DEFECTO = "http://192.168.80.145:8080/video"


def _fuente_video():
    """Lee CORIOT_VIDEO; si es un número lo devuelve como índice de cámara."""
    valor = os.environ.get("CORIOT_VIDEO", "").strip()
    if not valor:
        return FUENTE_VIDEO_DEFECTO
    # cv2.VideoCapture("0") busca un archivo; con int(0) abre la webcam.
    return int(valor) if valor.isdigit() else valor


FUENTE_VIDEO = _fuente_video()

# ---------------------------------------------------------------------------
# Detección por color (HSV de OpenCV: H 0-179, S y V 0-255)
# ---------------------------------------------------------------------------
RANGOS_HSV = {
    "H": ((0, 111, 80), (25, 255, 255)),    # naranja
    "S": ((125, 80, 60), (160, 255, 255)),  # morado
}
AREA_MIN = 300       # píxeles mínimos para considerar un blob

# Modo de detección. En competencia debe ser "yolo".
# "color" queda solo para pruebas y exige activarlo explícitamente:
#   $env:CORIOT_MODO_DETECCION = "color"    (o python main.py --modo color)
_modo = os.environ.get("CORIOT_MODO_DETECCION", "").strip().lower()
MODO_DETECCION = _modo or "yolo"
if MODO_DETECCION not in ("yolo", "color"):
    raise SystemExit(
        f"CORIOT_MODO_DETECCION inválido: {MODO_DETECCION!r}; usa 'yolo' o 'color'."
    )

# Forma de la víctima: alto / ancho mínimo. Es un filtro de RUNTIME para
# descartar figuras derribadas; no es una regla de etiquetado del dataset.
ASPECTO_MIN = 1.2

# ---------------------------------------------------------------------------
# Pista (tabla oficial, v2 §2). Coordenadas en mm, origen en la esquina
# inferior izquierda.
# ---------------------------------------------------------------------------
CUADRANTES = {
    "rojo": (500, 1500),       # superior izquierda
    "azul": (1500, 1500),      # superior derecha
    "verde": (500, 500),       # inferior izquierda
    "amarillo": (1500, 500),   # inferior derecha
}
START = (100, 100)             # esquina inferior izquierda del cuadrante verde
PUNTOS_X_TOTAL = 24
PUNTOS_POR_CUADRANTE = 6
VICTIMAS_POR_PRUEBA = 12
# TODO: coordenadas exactas de las 24 X. Se miden en la pista; no inventar.
PUNTOS_X = None

# ---------------------------------------------------------------------------
# Broker MQTT
# ---------------------------------------------------------------------------
BROKER_HOST = "127.0.0.1"       # TODO: confirmar con la organización
BROKER_PORT = 1883
BROKER_USUARIO = ""             # dejar vacío si el broker no pide credenciales
BROKER_PASSWORD = ""

# ---------------------------------------------------------------------------
# Temas MQTT (v2 §6.1)
# ---------------------------------------------------------------------------
ROBOT_ID = "E01"
TEMA_VISION = f"coriot/vision/{ROBOT_ID}"                 # laptop -> robot
TEMA_REPORTE_ROBOT = f"coriot/robot/{ROBOT_ID}/reporte"   # robot -> laptop
TEMA_ACK_ROBOT = f"coriot/robot/{ROBOT_ID}/ack"           # laptop -> robot
SERVIDOR_TEMA = "coriot/reporte"                          # TODO: tema oficial
BROKER_CLIENTE = f"laptop-{ROBOT_ID}"   # único en el broker, distinto del robot

# Límite de envío al servidor (reglamento §10.2: máximo 1 mensaje por segundo).
INTERVALO_SERVIDOR = 1.0

# ---------------------------------------------------------------------------
# Entrenamiento YOLO (valores pensados para un dataset pequeño y CPU)
# ---------------------------------------------------------------------------
EPOCAS = 50
LOTE = 8
TAMANO_IMG = 640
PACIENCIA = 15   # épocas sin mejora antes de detener el entrenamiento

# Validación mínima para considerar confiable el mAP (modelo/entrenar.py).
MIN_IMAGENES_VAL = 30
MIN_INSTANCIAS_POR_CLASE = 10
