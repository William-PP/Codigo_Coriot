"""Cámara en un hilo aparte: siempre entrega el frame más reciente."""

import threading
import time

import cv2

import config


FALLOS_MAX = 20   # ~1 s sin frames antes de dejar de entregar el frame viejo


class Camara:
    """Lee el stream en segundo plano y descarta los frames viejos."""

    def __init__(self, fuente=None, ancho=640):
        self.fuente = config.FUENTE_VIDEO if fuente is None else fuente
        self.ancho = ancho

        self.cap = cv2.VideoCapture(self.fuente)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente: {self.fuente}")

        # Intenta que el servidor entregue menos resolución y no acumule frames
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame = None
        self._lock = threading.Lock()
        self._activa = True
        self._hilo = threading.Thread(target=self._leer, daemon=True)
        self._hilo.start()

    def _leer(self):
        fallos = 0
        while self._activa:
            ok, frame = self.cap.read()
            if not ok:
                fallos += 1
                # Tras ~1 s sin frames, dejar de entregar el último frame:
                # así main.py sabe que la cámara se cayó y puede reabrirla.
                if fallos >= FALLOS_MAX:
                    with self._lock:
                        self._frame = None
                time.sleep(0.05)
                continue

            fallos = 0

            # Reducir antes de guardar: menos CPU y menos copias
            if self.ancho and frame.shape[1] > self.ancho:
                alto = int(frame.shape[0] * self.ancho / frame.shape[1])
                frame = cv2.resize(frame, (self.ancho, alto))

            with self._lock:
                self._frame = frame

    def leer(self):
        """Devuelve el último frame o None si todavía no hay."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def cerrar(self):
        self._activa = False
        if self._hilo.is_alive():
            self._hilo.join(timeout=2)
        self.cap.release()


if __name__ == "__main__":
    # Prueba rápida de fluidez: python -m stream.recibir
    cam = Camara()
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue
            cv2.imshow("stream", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()