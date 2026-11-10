"""Detector de víctimas con YOLO (misma interfaz que deteccion_color)."""

import config

_modelo = None


def _cargar():
    """Carga los pesos entrenados. Falla si no existen (no usa COCO)."""
    global _modelo
    if _modelo is None:
        from ultralytics import YOLO

        ruta = config.PESOS_ENTRENADO
        if not ruta.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo entrenado: {ruta}. "
                "Entrena con 'python -m modelo.entrenar' o usa '--modo color' "
                "solo para pruebas."
            )
        _modelo = YOLO(str(ruta))
    return _modelo


def detectar(frame):
    """Devuelve [(clase, confianza, (x, y, w, h)), ...] para un frame BGR."""
    resultado = _cargar().predict(
        frame,
        conf=config.CONF_MIN,
        iou=config.IOU_MIN,
        verbose=False,
    )[0]

    detecciones = []
    for caja in resultado.boxes:
        clase = config.CLASES.get(int(caja.cls))
        if clase is None:      # clases COCO que no son H ni S
            continue
        x1, y1, x2, y2 = (float(v) for v in caja.xyxy[0])
        detecciones.append(
            (clase, float(caja.conf), (int(x1), int(y1), int(x2 - x1), int(y2 - y1)))
        )
    return detecciones
