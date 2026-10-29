"""Calibra en vivo los rangos HSV de una clase (H o S)."""

import sys

import cv2
import numpy as np

import config

KERNEL = np.ones((5, 5), np.uint8)
NOMBRES = ["H_min", "H_max", "S_min", "S_max", "V_min", "V_max"]
MAXIMOS = [179, 179, 255, 255, 255, 255]


def _sin_accion(_):
    pass


def main():
    clase = (sys.argv[1] if len(sys.argv) > 1 else "H").upper()
    if clase not in config.RANGOS_HSV:
        raise SystemExit("Uso: python -m logica.calibrar_color [H|S]")

    (hmin, smin, vmin), (hmax, smax, vmax) = config.RANGOS_HSV[clase]
    valores = [hmin, hmax, smin, smax, vmin, vmax]

    cap = cv2.VideoCapture(config.FUENTE_VIDEO)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir: {config.FUENTE_VIDEO}")
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # reduce el retraso

    ventana = f"Calibrar {clase}  |  q = salir, p = imprimir"
    cv2.namedWindow(ventana)
    for nombre, valor, maximo in zip(NOMBRES, valores, MAXIMOS):
        cv2.createTrackbar(nombre, ventana, valor, maximo, _sin_accion)

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Se perdió el stream.")
            break

        frame = cv2.resize(frame, (640, 480))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        v = [cv2.getTrackbarPos(n, ventana) for n in NOMBRES]
        bajo = np.array([v[0], v[2], v[4]])   # H_min, S_min, V_min
        alto = np.array([v[1], v[3], v[5]])   # H_max, S_max, V_max

        mascara = cv2.inRange(hsv, bajo, alto)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, KERNEL)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, KERNEL)

        contornos, _ = cv2.findContours(
            mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contorno in contornos:
            if cv2.contourArea(contorno) < config.AREA_MIN:
                continue
            x, y, w, h = cv2.boundingRect(contorno)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imshow(ventana, frame)
        cv2.imshow("mascara", mascara)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord("p"):
            print(f'    "{clase}": (({v[0]}, {v[2]}, {v[4]}), ({v[1]}, {v[3]}, {v[5]})),')

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()