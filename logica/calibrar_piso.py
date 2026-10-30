"""Calibra el color del piso de cada cuadrante (teclas 1 a 4)."""

import cv2
import numpy as np

import config
from logica.cuadrante import FRANJA, cargar, guardar, leer_piso
from stream.recibir import Camara

TECLAS = {ord("1"): 1, ord("2"): 2, ord("3"): 3, ord("4"): 4}


def muestra(hsv):
    """Devuelve un color BGR visible para dibujar una muestra del piso."""
    pixel = np.array([[[hsv[0], hsv[1], hsv[2]]]], dtype=np.uint8)
    return tuple(int(c) for c in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0])


def leyenda(frame, colores):
    """Escribe en el frame la lista de cuadrantes ya calibrados."""
    for indice, numero in enumerate(range(1, 5)):
        y = 90 + indice * 30
        if numero in colores:
            hsv = colores[numero]
            cv2.rectangle(frame, (10, y - 14), (34, y + 6), muestra(hsv), -1)
            cv2.rectangle(frame, (10, y - 14), (34, y + 6), (255, 255, 255), 1)
            texto = f"{numero}: H={hsv[0]:.0f} S={hsv[1]:.0f} V={hsv[2]:.0f}"
            color = (0, 255, 0)
        else:
            texto = f"{numero}: sin calibrar"
            color = (0, 165, 255)
        cv2.putText(frame, texto, (42, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)


def main():
    colores = cargar()
    cam = Camara()
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue

            hsv = leer_piso(frame)
            alto, ancho = frame.shape[:2]
            cv2.rectangle(frame, (0, int(alto * FRANJA[0])), (ancho - 1, alto - 1), (0, 255, 0), 1)
            cv2.putText(
                frame,
                f"piso HSV: {hsv[0]:.0f} {hsv[1]:.0f} {hsv[2]:.0f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                1,
            )
            cv2.putText(
                frame,
                "1-4 = guardar cuadrante   r = borrar   q = salir",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                1,
            )
            leyenda(frame, colores)

            cv2.imshow("Calibrar piso por cuadrante", frame)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord("q"):
                break
            if tecla in TECLAS:
                numero = TECLAS[tecla]
                colores[numero] = leer_piso(frame)
                guardar(colores)
                print(f"Cuadrante {numero}: H={colores[numero][0]:.0f} "
                      f"S={colores[numero][1]:.0f} V={colores[numero][2]:.0f}")
            if tecla == ord("r"):
                colores.clear()
                config.PISO_JSON.unlink(missing_ok=True)
                print("Calibración de piso borrada")
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
