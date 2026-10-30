"""Punto de entrada: stream -> detección -> cuadrante -> conteo -> IoT."""

import json
import time

import cv2

import config
from logica.contador import Contador
from logica.filtros import solo_verticales
from stream.recibir import Camara

COLORES = {"H": (0, 165, 255), "S": (255, 0, 255)}


def cargar_detector():
    """Devuelve la función de detección según config.MODO_DETECCION."""
    if config.MODO_DETECCION == "yolo":
        from logica.deteccion_yolo import detectar
    else:
        from logica.deteccion_color import detectar
    return detectar


def cargar_cuadrante():
    """Devuelve una función frame -> cuadrante, o None si está deshabilitado.

    El cuadrante está en pausa hasta decidir si se usa sensor de color al piso
    o cámara de navegación (config.USAR_CUADRANTE).
    """
    if not config.USAR_CUADRANTE:
        return None

    from logica import cuadrante

    colores = cuadrante.cargar()
    if not colores:
        print("Aviso: USAR_CUADRANTE activo pero falta modelo/piso.json")
        return None

    return lambda frame: cuadrante.clasificar(cuadrante.leer_piso(frame), colores)[0]


def reporte_json(contador):
    """Arma el reporte que se envía al servidor de la competencia."""
    return {
        "robot": config.ROBOT_ID,
        "tiempo": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cuadrantes": contador.reporte(),
    }


def publicar(reporte):
    """Envía el reporte al servidor. Por ahora solo lo imprime.

    TODO: logica/iot.py (MQTT o HTTP) cuando se conozca el protocolo oficial.
    """
    print(json.dumps(reporte, ensure_ascii=False))


def dibujar(frame, detecciones, conteo, cuadrante_actual=None):
    """Dibuja cajas y contadores sobre el frame."""
    for clase, confianza, (x, y, w, h) in detecciones:
        color = COLORES.get(clase, (0, 255, 0))
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            frame,
            f"{clase} {confianza:.2f}",
            (x, max(y - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    y_texto = 25
    if cuadrante_actual is not None:
        cv2.putText(
            frame,
            f"cuadrante: {cuadrante_actual or '-'}",
            (10, y_texto),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
        )
        y_texto += 28

    for numero in sorted(conteo):
        valores = conteo[numero]
        etiqueta = f"C{numero}" if numero else "sin cuadrante"
        cv2.putText(
            frame,
            f"{etiqueta}: H={valores['H']} S={valores['S']}",
            (10, y_texto),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
        y_texto += 26


def main():
    detector = cargar_detector()
    leer_cuadrante = cargar_cuadrante()
    contador = Contador()
    cam = Camara()
    ultimo = {}
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue

            detecciones = solo_verticales(detector(frame))
            cuadrante_actual = leer_cuadrante(frame) if leer_cuadrante else None
            contador.actualizar(detecciones, cuadrante_actual)

            # Publicar solo cuando cambia el conteo (no en cada frame)
            if contador.reporte() != ultimo:
                ultimo = contador.reporte()
                publicar(reporte_json(contador))

            dibujar(frame, detecciones, ultimo, cuadrante_actual)
            cv2.imshow("Codigo Rescate  |  q = salir", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()
        print("Reporte final:")
        publicar(reporte_json(contador))


if __name__ == "__main__":
    main()
