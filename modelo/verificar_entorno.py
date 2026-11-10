"""Verifica el entorno: versiones, carga del modelo e inferencia."""

from pathlib import Path

import cv2
import numpy as np
import ultralytics
from ultralytics import YOLO

import config

# 1. Versiones instaladas
print(f"ultralytics: {ultralytics.__version__}")
print(f"opencv:      {cv2.__version__}")

# 2. Pesos base obligatorios (no se descargan)
pesos = config.PESOS_DIR / "yolo11n.pt"
if not pesos.exists():
    raise SystemExit(f"Falta el modelo base: {pesos}. Copialo desde el kit (kit/PESOS_MODELO.txt).")

# 3. Cargar YOLO11n
modelo = YOLO(str(pesos))

# 4. Inferencia sobre una imagen sintética (sin red)
imagen = (np.zeros((640, 640, 3), dtype=np.uint8) + 127).astype("uint8")
resultado = modelo.predict(imagen, conf=0.25, verbose=False)[0]

# 5. Mostrar detecciones (puede ser 0 en una imagen gris; lo importante es que corra)
print(f"detecciones en imagen sintética: {len(resultado.boxes)}")
print("Entorno OK.")