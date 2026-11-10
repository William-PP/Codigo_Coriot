"""Punto de entrada v2: cámara -> visión -> robot y robot -> servidor -> ACK.

`main.py` solo orquesta. La navegación, el conteo y el derribo son del robot.
La clasificación H/S usa únicamente YOLO (el detector de color queda para
pruebas y calibración, fuera del flujo de competencia).

- El bucle local captura, detecta y envía la línea de visión como máximo a
  15 Hz (§6.1). El video se refresca al ritmo de la cámara.
- `EnlaceRobot` atiende los reportes en su propio hilo: reenvía al servidor
  con un máximo de 1 mensaje por segundo, espera el PUBACK y solo entonces
  responde el ACK.
- `enviar_vision()` usa qos 0: si MQTT se cae, la visión sigue y la conexión
  se reintenta sola, sin bloquear este bucle.
- Cada inferencia de YOLO se registra en un archivo JSON-lines dentro de
  `logs/` para revisión del juez (reglamento §7.2).
"""

import argparse
import json
import os
import threading
import time

import cv2

import config
from logica import iot
from logica.filtros import solo_verticales
from logica.robot_mqtt import EnlaceRobot
from logica.vision_robot import linea_vision
from stream.recibir import Camara

VISION_HZ = 15
INTERVALO_VISION = 1.0 / VISION_HZ
ESPERA_CAMARA = 0.5    # segundos entre reintentos de apertura
SIN_FRAMES_MAX = 2.0   # segundos sin frame antes de reabrir la cámara
COLORES = {"H": (0, 165, 255), "S": (255, 0, 255)}
LOGS_DIR = "logs"


class EstadoPipeline:
    """Estado compartido del pipeline para la GUI o para pruebas."""

    def __init__(self, equipo=None, intento=None):
        self.equipo = equipo
        self.intento = intento
        self.parar = threading.Event()
        self.running = False
        self.camera_ok = False
        self.broker_ok = False
        self.server_link = "TODO" if not (equipo and intento) else "sin iniciar"
        self.last_seq = None
        self.last_report = None
        self.last_report_time = None
        self.vision_times = []
        self.avisos = []
        self._lock = threading.Lock()

    def log(self, msg, nivel="info"):
        with self._lock:
            self.avisos.append((time.time(), nivel, msg))
            if len(self.avisos) > 300:
                self.avisos = self.avisos[-300:]

    def vision_rate(self):
        now = time.time()
        with self._lock:
            self.vision_times = [t for t in self.vision_times if now - t <= 1.0]
            return len(self.vision_times)

    def snapshot_avisos(self):
        with self._lock:
            return list(self.avisos)


class ErrorDeModelo(RuntimeError):
    """El modo de detección pedido no tiene el modelo necesario."""


def _resolver_modo(modo=None):
    """Normaliza el modo de detección; por defecto usa config.MODO_DETECCION."""
    modo = (modo or config.MODO_DETECCION or "yolo").strip().lower()
    if modo not in ("yolo", "color"):
        raise ValueError(f"Modo de detección inválido: {modo!r}; usa 'yolo' o 'color'.")
    return modo


def validar_pesos_yolo():
    """Falla con un mensaje claro si el modo yolo no tiene rescate.pt."""
    if not config.PESOS_ENTRENADO.exists():
        raise ErrorDeModelo(
            "Modo 'yolo' activo pero falta el modelo entrenado: "
            f"{config.PESOS_ENTRENADO}\n"
            "Entrena primero con: python -m modelo.entrenar ...\n"
            "El modo 'color' es solo para pruebas: python main.py --modo color"
        )


def cargar_detector(modo=None):
    """Devuelve la función de detección según el modo (yolo por defecto)."""
    modo = _resolver_modo(modo)
    if modo == "yolo":
        from logica.deteccion_yolo import detectar
    else:
        from logica.deteccion_color import detectar
    return detectar


def _cerrar_camara(cam):
    """Cierra una cámara sin dejar que un error de cierre tumbe el programa."""
    try:
        cam.cerrar()
    except Exception as error:
        print(f"T4: error al cerrar la cámara ({error})")


def _resumen_reporte(reporte):
    """Texto corto del último reporte para la consola."""
    if not isinstance(reporte, dict):
        return "sin reporte"

    cuadrantes = reporte.get("cuadrantes", [])
    if not isinstance(cuadrantes, list):
        cuadrantes = []

    partes = [str(reporte.get("estado", "?"))]
    for cuadrante in cuadrantes:
        if not isinstance(cuadrante, dict):
            continue
        color = cuadrante.get("color", "?")
        if cuadrante.get("explorado"):
            partes.append(
                f"{color}: H={cuadrante.get('heridos')} "
                f"S={cuadrante.get('necesitan_suministros')}"
            )
        else:
            partes.append(f"{color}: --")
    return " | ".join(partes)


def dibujar(frame, detecciones, enlace):
    """Dibuja las cajas y el estado del enlace y del último reporte."""
    for clase, confianza, (x, y, ancho, alto) in detecciones:
        color = COLORES.get(clase, (0, 255, 0))
        cv2.rectangle(frame, (x, y), (x + ancho, y + alto), color, 2)
        cv2.putText(
            frame,
            f"{clase} {confianza:.2f}",
            (x, max(y - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    try:
        conectado = bool(enlace.conectado()) if enlace is not None else False
    except Exception:
        conectado = False

    secuencia = getattr(enlace, "ultima_secuencia", None) if enlace is not None else None
    reporte = getattr(enlace, "ultimo_reporte", None) if enlace is not None else None

    textos = [
        f"MQTT: {'ok' if conectado else 'sin conexion'}   "
        f"robot seq: {secuencia if secuencia is not None else '-'}"
    ]
    if isinstance(reporte, dict):
        textos.append(f"reporte: {reporte.get('estado', '?')}")
        cuadrantes = reporte.get("cuadrantes", [])
        if not isinstance(cuadrantes, list):
            cuadrantes = []
        for cuadrante in cuadrantes:
            if not isinstance(cuadrante, dict):
                continue
            color = cuadrante.get("color", "?")
            if cuadrante.get("explorado"):
                textos.append(
                    f"{color}: H={cuadrante.get('heridos')} "
                    f"S={cuadrante.get('necesitan_suministros')}"
                )
            else:
                textos.append(f"{color}: --")
    else:
        textos.append("sin reporte del robot")

    for indice, texto in enumerate(textos):
        cv2.putText(
            frame,
            texto,
            (10, 24 + 22 * indice),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
        )


def _registrar_inferencia_por_defecto(path):
    """Devuelve una función que añade una línea JSON al archivo indicado."""
    def registrar(registro):
        try:
            directorio = os.path.dirname(path)
            if directorio:
                os.makedirs(directorio, exist_ok=True)
            with open(path, "a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        except Exception as error:
            print(f"T4: no se pudo registrar la inferencia ({error})")
    return registrar


def ejecutar(
    camara_fabrica=Camara,
    detector=None,
    enlace=None,
    mostrar=True,
    max_iteraciones=None,
    intervalo_vision=INTERVALO_VISION,
    sin_frames_max=SIN_FRAMES_MAX,
    dormir=time.sleep,
    equipo=None,
    intento=None,
    archivo_inferencias=None,
    registrar_inferencias=None,
    estado=None,
    modo=None,
):
    """Bucle principal. Los parámetros extra permiten probarlo sin hardware."""
    if detector is None:
        modo = _resolver_modo(modo)
        if modo == "yolo":
            validar_pesos_yolo()
        detector = cargar_detector(modo)

    if enlace is None:
        if equipo and intento:
            enlace = EnlaceRobot()
            enlace_propio = True
        else:
            print(
                "T4: equipo/intento no configurados: no se inicia el enlace al "
                "servidor; no habrá ACK (configura --equipo y --intento)."
            )
            enlace = None
            enlace_propio = False
    else:
        enlace_propio = False

    if registrar_inferencias is None and archivo_inferencias:
        registrar_inferencias = _registrar_inferencia_por_defecto(archivo_inferencias)

    if estado is not None:
        estado.running = True
        if equipo and intento:
            estado.server_link = "sin iniciar"
        else:
            estado.server_link = "TODO"

    cam = None
    ultimo_frame = 0.0
    ultimo_envio = None
    detecciones = []
    secuencia_mostrada = None
    iteraciones = 0
    numero_frame = 0

    try:
        while True:
            if estado is not None and estado.parar.is_set():
                break
            if max_iteraciones is not None and iteraciones >= max_iteraciones:
                break
            iteraciones += 1

            # --- estado del broker / enlace (siempre, aunque la cámara falle) ---
            if estado is not None:
                try:
                    estado.broker_ok = bool(iot.conectado())
                except Exception:
                    estado.broker_ok = False
                if enlace is not None:
                    try:
                        estado.server_link = "conectado" if enlace.conectado() else "sin conexión"
                    except Exception:
                        estado.server_link = "sin conexión"
                else:
                    estado.server_link = "TODO" if not (equipo and intento) else "sin iniciar"

            # --- cámara: abrir o reabrir sin tumbar el programa -----------
            if cam is None:
                try:
                    cam = camara_fabrica()
                    ultimo_frame = time.monotonic()
                    ultimo_envio = None
                    if estado is not None:
                        estado.camera_ok = True
                        estado.log("cámara abierta")
                except Exception as error:
                    print(
                        f"T4: no se pudo abrir la cámara ({error}); "
                        f"reintento en {ESPERA_CAMARA:g}s"
                    )
                    if estado is not None:
                        estado.camera_ok = False
                        estado.log(f"no se pudo abrir la cámara: {error}", "error")
                    dormir(ESPERA_CAMARA)
                    continue

            try:
                frame = cam.leer()
            except Exception as error:
                print(f"T4: error al leer la cámara ({error}); se reabre")
                _cerrar_camara(cam)
                cam = None
                if estado is not None:
                    estado.camera_ok = False
                    estado.log(f"error al leer la cámara: {error}", "error")
                dormir(ESPERA_CAMARA)
                continue

            if frame is None:
                if time.monotonic() - ultimo_frame >= sin_frames_max:
                    print("T4: la cámara no entrega frames; se reabre")
                    _cerrar_camara(cam)
                    cam = None
                    if estado is not None:
                        estado.camera_ok = False
                        estado.log("la cámara no entrega frames; se reabre", "warn")
                    dormir(ESPERA_CAMARA)
                else:
                    dormir(0.05)
                continue

            ultimo_frame = time.monotonic()
            if estado is not None:
                estado.camera_ok = True

            # --- visión: detector -> filtro -> línea -> robot (máx. 15 Hz) -
            ahora = time.monotonic()
            if ultimo_envio is None or ahora - ultimo_envio >= intervalo_vision:
                try:
                    detecciones = solo_verticales(detector(frame))
                except Exception as error:
                    print(f"T4: error del detector ({error}); se envía sin figura")
                    detecciones = []
                    if estado is not None:
                        estado.log(f"error del detector: {error}", "error")

                numero_frame += 1
                if registrar_inferencias is not None:
                    for clase, confianza, (x, y, ancho, alto) in detecciones:
                        registrar_inferencias({
                            "timestamp": time.time(),
                            "frame": numero_frame,
                            "clase": clase,
                            "confianza": confianza,
                            "caja": [int(x), int(y), int(ancho), int(alto)],
                        })

                try:
                    lineas = linea_vision(detecciones, frame.shape[1])
                except Exception as error:
                    print(f"T4: error al armar la línea de visión ({error})")
                    lineas = []
                    if estado is not None:
                        estado.log(f"error al armar la línea de visión: {error}", "error")

                for linea in lineas:
                    try:
                        if enlace is not None:
                            enlace.enviar_vision(linea)
                            if estado is not None:
                                estado.vision_times.append(time.time())
                    except Exception as error:
                        print(f"T4: no se pudo enviar la visión ({error})")
                        if estado is not None:
                            estado.log(f"no se pudo enviar la visión: {error}", "warn")
                ultimo_envio = ahora

            # --- último reporte del robot --------------------------------
            secuencia = getattr(enlace, "ultima_secuencia", None) if enlace is not None else None
            if secuencia is not None and secuencia != secuencia_mostrada:
                secuencia_mostrada = secuencia
                reporte = getattr(enlace, "ultimo_reporte", None)
                print(f"T4: reporte del robot, secuencia {secuencia}: "
                      f"{_resumen_reporte(reporte)}")
                if estado is not None:
                    estado.last_seq = secuencia
                    estado.last_report = reporte
                    estado.last_report_time = time.time()

            # --- video al ritmo de la cámara -----------------------------
            if mostrar:
                try:
                    dibujar(frame, detecciones, enlace)
                    cv2.imshow("Codigo Rescate v2  |  q = salir", frame)
                    if cv2.waitKey(16) & 0xFF == ord("q"):
                        break
                except Exception as error:
                    print(f"T4: no se pudo mostrar el video ({error})")
                    mostrar = False
            else:
                dormir(0.005)

    finally:
        if cam is not None:
            _cerrar_camara(cam)
        if mostrar:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        if enlace is not None:
            try:
                enlace.enviar_final()
            except Exception as error:
                print(f"T4: error al enviar el reporte final ({error})")
                if estado is not None:
                    estado.log(f"error al enviar el reporte final: {error}", "error")
            if enlace_propio:
                try:
                    enlace.cerrar(descartar=False)
                except Exception as error:
                    print(f"T4: error al cerrar el enlace ({error})")
                    if estado is not None:
                        estado.log(f"error al cerrar el enlace: {error}", "error")
        if estado is not None:
            estado.running = False


def iniciar_pipeline(equipo=None, intento=None, archivo_inferencias=None, mostrar=False, fuente_video=None, modo=None):
    """Inicia el pipeline en un hilo y devuelve el EstadoPipeline."""
    modo = _resolver_modo(modo)
    if modo == "yolo":
        validar_pesos_yolo()
    estado = EstadoPipeline(equipo=equipo, intento=intento)
    if archivo_inferencias is None:
        archivo_inferencias = os.path.join(LOGS_DIR, "inferencias.jsonl")

    if fuente_video is None:
        camara_fabrica = Camara
    else:
        if isinstance(fuente_video, str) and fuente_video.isdigit():
            fuente = int(fuente_video)
        else:
            fuente = fuente_video

        def camara_fabrica():
            return Camara(fuente=fuente)

    def run():
        try:
            ejecutar(
                camara_fabrica=camara_fabrica,
                mostrar=mostrar,
                equipo=equipo,
                intento=intento,
                archivo_inferencias=archivo_inferencias,
                estado=estado,
                modo=modo,
            )
        except Exception as error:
            estado.log(f"pipeline caído: {error}", "error")
            estado.running = False

    hilo = threading.Thread(target=run, name="pipeline", daemon=True)
    hilo.start()
    estado._hilo = hilo
    return estado


def detener_pipeline(estado):
    """Detiene el pipeline de forma limpia."""
    if estado is None:
        return
    try:
        estado.parar.set()
    except Exception:
        pass
    hilo = getattr(estado, "_hilo", None)
    if hilo is not None and hilo.is_alive():
        hilo.join(timeout=10)
    estado.running = False


def main():
    """Arranca el flujo v2 y cierra el cliente MQTT compartido al salir."""
    parser = argparse.ArgumentParser(description="Código Rescate - laptop")
    parser.add_argument("--equipo", default=None, help="Identificador del equipo registrado")
    parser.add_argument("--intento", default=None, help="Identificador de intento habilitado por el juez")
    parser.add_argument(
        "--modo",
        choices=("yolo", "color"),
        default=None,
        help="Modo de detección; por defecto yolo. 'color' es solo para pruebas.",
    )
    args = parser.parse_args()

    equipo = (args.equipo or "").strip() or None
    intento = (args.intento or "").strip() or None
    if equipo is None:
        try:
            equipo = input("Equipo (identificador registrado): ").strip() or None
        except EOFError:
            equipo = None
    if intento is None:
        try:
            intento = input("Intento (habilitado por el juez): ").strip() or None
        except EOFError:
            intento = None

    archivo_inferencias = os.path.join(LOGS_DIR, "inferencias.jsonl")

    try:
        ejecutar(
            equipo=equipo,
            intento=intento,
            archivo_inferencias=archivo_inferencias,
            modo=args.modo,
        )
    except ErrorDeModelo as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nT4: interrumpido por el usuario")
    finally:
        iot.cerrar()


if __name__ == "__main__":
    main()
