"""Configuración central del proyecto Código Rescate."""

from pathlib import Path

# Rutas base: se calculan desde la ubicación de este archivo,
# así funcionan aunque ejecutes desde otra carpeta.
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

# Fuente de video: 0 = webcam de la laptop (desarrollo);
# en competencia, URL del stream del robot, ej. "http://192.168.4.1:81/stream"
FUENTE_VIDEO = "http://192.168.80.145:8080/video"

# Colores de piso por cuadrante: se calibran en la pista (no sirven los de casa)
PISO_JSON = MODELO_DIR / "piso.json"

# Comunicación IoT (el protocolo se define más adelante)
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883

# Detección por color (HSV de OpenCV: H 0-179, S y V 0-255)
RANGOS_HSV = {
    "H": ((0, 111, 80), (25, 255, 255)),    # naranja
    "S": ((125, 80, 60), (160, 255, 255)),  # morado
}
AREA_MIN = 300       # píxeles mínimos para considerar un blob
MODO_DETECCION = "color"  # "color" o "yolo"

# Forma de la víctima: alto / ancho mínimo. Una figura derribada (horizontal)
# queda por debajo y se descarta. 1.0 = cuadrada; subir para exigir más vertical.
ASPECTO_MIN = 1.2

# Cuadrante: bloqueado hasta decidir si se usa sensor de color o cámara
USAR_CUADRANTE = False

# Conteo de víctimas: frames seguidos que debe verse una figura para contarla
# (evita que la misma víctima se cuente en cada frame)
CONFIRMA_FRAMES = 5

# Identificador del robot que viaja en el JSON de IoT
ROBOT_ID = "codigo-rescate"