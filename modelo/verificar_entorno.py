"""Verifica el entorno: versiones, carga del modelo e inferencia."""

import urllib.request
from pathlib import Path

import cv2
import numpy as np
import ultralytics
from ultralytics import YOLO

# 1. Versiones instaladas
print(f"ultralytics: {ultralytics.__version__}")
print(f"opencv:      {cv2.__version__}")

# 2. Cargar YOLO11n (se descarga solo si no existe)
pesos = Path(__file__).resolve().parent / "pesos" / "yolo11s.pt"
pesos.parent.mkdir(parents=True, exist_ok=True)
modelo = YOLO(str(pesos))

# 3. Descargar la imagen en memoria (sin crear archivos fuera de modelo/)
url = "https://ultralytics.com/images/bus.jpg"
datos = urllib.request.urlopen(url).read()
imagen = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)

# 4. Inferencia sobre la imagen
resultado = modelo.predict(imagen, conf=0.25, verbose=False)[0]

# 5. Mostrar clase y confianza de cada detección
for caja in resultado.boxes:
    clase = modelo.names[int(caja.cls)]
    print(f"{clase}: {float(caja.conf):.2%}")