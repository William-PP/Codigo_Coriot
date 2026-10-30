"""Prueba el detector de color en vivo con cajas y conteo."""

import cv2

from logica.deteccion_color import detectar
from stream.recibir import Camara


def main():
    cam = Camara()
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue

            detecciones = detectar(frame)
            conteo = {"H": 0, "S": 0}

            for clase, confianza, (x, y, w, h) in detecciones:
                conteo[clase] += 1
                color = (0, 165, 255) if clase == "H" else (255, 0, 255)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(
                    frame,
                    f"{clase} {confianza:.2f}",
                    (x, max(y - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

            cv2.putText(
                frame,
                f"H={conteo['H']}  S={conteo['S']}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )
            cv2.imshow("Deteccion en vivo  |  q = salir", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()