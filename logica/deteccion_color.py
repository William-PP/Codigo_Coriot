"""Detector de víctimas por color (H = naranja, S = morado)."""

import cv2
import numpy as np

import config

KERNEL = np.ones((5, 5), np.uint8)


def detectar(frame):
    """Devuelve [(clase, confianza, (x, y, w, h)), ...] para un frame BGR."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    detecciones = []

    for clase, (bajo, alto) in config.RANGOS_HSV.items():
        # Máscara del color y limpieza de ruido
        mascara = cv2.inRange(hsv, np.array(bajo), np.array(alto))
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, KERNEL)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, KERNEL)

        contornos, _ = cv2.findContours(
            mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area < config.AREA_MIN:
                continue

            x, y, w, h = cv2.boundingRect(contorno)
            # Confianza heurística: tamaño del blob y qué tan lleno está su rectángulo
            solidez = area / (w * h) if w * h else 0.0
            confianza = min(1.0, area / (config.AREA_MIN * 4)) * solidez
            detecciones.append((clase, confianza, (x, y, w, h)))

    return detecciones


if __name__ == "__main__":
    # Prueba sin cámara: dibuja un rectángulo naranja y uno morado
    imagen = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(imagen, (100, 100), (200, 300), (0, 140, 255), -1)  # naranja
    cv2.rectangle(imagen, (400, 150), (500, 350), (128, 0, 128), -1)  # morado

    for clase, confianza, caja in detectar(imagen):
        print(f"{clase}: confianza={confianza:.2f} caja={caja}")