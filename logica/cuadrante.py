"""Cuadrante de la pista según el color del piso bajo el robot."""

import json

import cv2
import numpy as np

import config

# Franja del frame que se usa para leer el piso: la parte baja (cerca del robot).
FRANJA = (0.85, 1.0)
# Se muestrea 1 de cada PASO píxeles: suficiente y mucho más rápido.
PASO = 4
# Distancia HSV máxima para aceptar un cuadrante (menor = más estricto).
DIST_MAX = 0.30
# Saturación mínima para considerar que el piso tiene color: un gris no tiene
# tono, así que su "rojo" (H=0) es un valor sin sentido.
SAT_MIN = 50


def leer_piso(frame):
    """Devuelve el color HSV (h, s, v) promedio de la franja inferior del frame.

    h va en 0-179 (escala de OpenCV), s y v en 0-255.
    """
    alto = frame.shape[0]
    banda = frame[int(alto * FRANJA[0]):alto:PASO, ::PASO]
    hsv = cv2.cvtColor(banda, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)

    # El tono es circular (0 y 179 son el mismo rojo): se promedia como vector
    # y se pondera por saturación para que el gris no arrastre el resultado.
    angulo = np.deg2rad(hsv[:, 0] * 2.0)
    peso = np.maximum(hsv[:, 1], 1.0)
    cos = float(np.sum(np.cos(angulo) * peso))
    sin = float(np.sum(np.sin(angulo) * peso))
    h = (np.rad2deg(np.arctan2(sin, cos)) % 360.0) / 2.0

    return h, float(np.mean(hsv[:, 1])), float(np.mean(hsv[:, 2]))


def distancia(a, b):
    """Distancia entre dos colores HSV: 0 = iguales, ~1 = muy distintos."""
    dh = abs(a[0] - b[0])
    dh = min(dh, 180.0 - dh) / 90.0  # el tono es circular
    ds = abs(a[1] - b[1]) / 255.0
    dv = abs(a[2] - b[2]) / 255.0
    return 0.6 * dh + 0.25 * ds + 0.15 * dv


def cargar():
    """Lee los colores calibrados: {1: (h, s, v), ...}. Vacío si no hay archivo."""
    if not config.PISO_JSON.exists():
        return {}
    datos = json.loads(config.PISO_JSON.read_text(encoding="utf-8"))
    return {int(clave): tuple(valor) for clave, valor in datos.items()}


def guardar(colores):
    """Escribe los colores calibrados en config.PISO_JSON."""
    config.PISO_JSON.parent.mkdir(parents=True, exist_ok=True)
    datos = {str(n): [round(x, 1) for x in hsv] for n, hsv in colores.items()}
    config.PISO_JSON.write_text(json.dumps(datos, indent=2), encoding="utf-8")


def clasificar(hsv, colores, dist_max=DIST_MAX):
    """Devuelve (cuadrante, distancia); cuadrante 0 si ninguno se parece."""
    if not colores or hsv[1] < SAT_MIN:
        return 0, float("inf")

    numero, dist = min(
        ((n, distancia(hsv, c)) for n, c in colores.items()),
        key=lambda par: par[1],
    )
    return (numero if dist <= dist_max else 0), dist


def main():
    """Prueba en vivo: python -m logica.cuadrante"""
    from stream.recibir import Camara

    colores = cargar()
    if not colores:
        raise SystemExit("Sin calibración: corre python -m logica.calibrar_piso")

    cam = Camara()
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue

            hsv = leer_piso(frame)
            numero, dist = clasificar(hsv, colores)

            alto, ancho = frame.shape[:2]
            cv2.rectangle(frame, (0, int(alto * FRANJA[0])), (ancho - 1, alto - 1), (0, 255, 0), 1)
            cv2.putText(
                frame,
                f"cuadrante: {numero or '-'}   dist: {dist:.2f}" if numero else "cuadrante: -   (piso sin color)",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )
            cv2.putText(
                frame,
                f"piso HSV: {hsv[0]:.0f} {hsv[1]:.0f} {hsv[2]:.0f}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                1,
            )
            cv2.imshow("Cuadrante por color de piso  |  q = salir", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
