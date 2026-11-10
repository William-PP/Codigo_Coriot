"""Enlace con el robot: recibe sus reportes, los reenvía y responde ACK (T2).

Flujo:
  hilo de red de paho -> `_al_recibir`: solo parsea y encola
  worker propio       -> publica al servidor, espera PUBACK y manda ACK

`_al_recibir` no toca la red: así el hilo de paho nunca se bloquea.
Sin PUBACK del servidor no sale ACK. Sin ACK el robot no derriba.
"""

import json
import queue
import threading
import time

import config
from logica import iot

COLA_MAX = 100       # reportes pendientes antes de descartar
PARADA_MS = 0.2      # espera máxima del worker para revisar la parada


def formatear_para_servidor(reporte):
    """Devuelve el JSON que se reenvía al servidor.

    TODO: cuando la organización confirme el formato oficial, convertirlo aquí.
    Por ahora se reenvía tal cual (v2 D2).
    """
    return reporte


def _clave_reporte(reporte):
    """Huella estable del reporte para reconocer un reintento idéntico."""
    return json.dumps(reporte, sort_keys=True, ensure_ascii=False)


def _parsear(texto):
    """Valida el reporte del robot.

    Devuelve ``(secuencia, reporte)`` o lanza ``ValueError`` si no sirve.
    """
    try:
        reporte = json.loads(texto)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON inválido: {error.msg}") from error

    if not isinstance(reporte, dict):
        raise ValueError("el reporte no es un objeto JSON")

    valor = reporte.get("secuencia")
    if isinstance(valor, bool):
        raise ValueError("la secuencia no puede ser booleana")
    if isinstance(valor, int):
        secuencia = valor
    elif isinstance(valor, str) and valor.strip().isdigit():
        secuencia = int(valor)
    else:
        raise ValueError("falta una 'secuencia' numérica")

    return secuencia, reporte


class EnlaceRobot:
    """Reenvía los reportes del robot al servidor y responde el ACK.

    Usa el cliente MQTT compartido de `logica.iot` (id `laptop-E01`); nunca
    crea otro cliente. El worker es el único que publica al servidor y el
    único que responde el ACK.
    """

    def __init__(self, intervalo_servidor=None, reloj=None, dormir=None):
        self.ultimo_reporte = None
        self.ultima_secuencia = None
        self._cola = queue.Queue(maxsize=COLA_MAX)
        self._parar = threading.Event()
        # secuencia -> huellas ya publicadas con PUBACK. Se guarda la huella y
        # no solo el número porque el firmware reinicia `secuencia` a 0 al
        # arrancar: un número repetido con otro contenido es un reporte nuevo.
        self._reenviadas = {}
        self.intervalo_servidor = (
            config.INTERVALO_SERVIDOR if intervalo_servidor is None
            else intervalo_servidor
        )
        self._reloj = reloj if reloj is not None else time.monotonic
        self._dormir = dormir if dormir is not None else time.sleep
        self._ultimo_envio_servidor = None
        self._hilo = threading.Thread(
            target=self._trabajar, name="enlace-robot", daemon=True
        )
        self._hilo.start()

        if not iot.suscribir(config.TEMA_REPORTE_ROBOT, self._al_recibir):
            print("T2: no se pudo suscribir a los reportes del robot")

    # ------------------------------------------------------------------
    # Hilo de red de paho: rápido y sin bloqueos
    # ------------------------------------------------------------------
    def _al_recibir(self, tema, texto):
        """Parsea el reporte y lo encola. No publica ni espera nada."""
        try:
            secuencia, reporte = _parsear(texto)
        except ValueError as error:
            print(f"T2: reporte descartado ({error})")
            return

        self.ultima_secuencia = secuencia
        self.ultimo_reporte = reporte

        try:
            self._cola.put_nowait((secuencia, reporte))
        except queue.Full:
            # Sin ACK el robot reintenta, así que descartar es seguro.
            print(f"T2: cola llena, se descarta la secuencia {secuencia}")

    # ------------------------------------------------------------------
    # Worker: única parte que habla con el servidor y responde el ACK
    # ------------------------------------------------------------------
    def _trabajar(self):
        while not self._parar.is_set() or not self._cola.empty():
            try:
                secuencia, reporte = self._cola.get(timeout=PARADA_MS)
            except queue.Empty:
                continue
            try:
                self._procesar(secuencia, reporte)
            except Exception as error:
                print(f"T2: error al procesar la secuencia {secuencia}: {error}")
            finally:
                self._cola.task_done()

    def _procesar(self, secuencia, reporte):
        if not config.SERVIDOR_TEMA:
            print(
                f"T2: servidor no configurado (SERVIDOR_TEMA vacío); "
                f"no se envía ACK para la secuencia {secuencia}"
            )
            return

        destino = formatear_para_servidor(reporte)
        clave = _clave_reporte(destino)

        if clave in self._reenviadas.get(secuencia, ()):
            # Este mismo reporte ya se publicó con PUBACK (el ACK se perdió o
            # el robot reintentó): solo hay que confirmarlo otra vez.
            self._enviar_ack(secuencia)
            return

        # Límite de 1 mensaje por segundo al servidor: esperar si hace falta.
        ahora = self._reloj()
        if self._ultimo_envio_servidor is not None:
            espera = self.intervalo_servidor - (ahora - self._ultimo_envio_servidor)
            if espera > 0:
                self._dormir(espera)
        self._ultimo_envio_servidor = self._reloj()

        # iot.publicar() hace wait_for_publish(5 s) y comprueba is_published();
        # solo devuelve True cuando el broker confirmó el mensaje.
        confirmado = iot.publicar(destino, config.SERVIDOR_TEMA)
        if not confirmado:
            print(f"T2: sin PUBACK del servidor; no hay ACK para la secuencia {secuencia}")
            return

        self._reenviadas.setdefault(secuencia, set()).add(clave)
        self._enviar_ack(secuencia)

    def _enviar_ack(self, secuencia):
        """Avisa al robot. Si el ACK se pierde, su reintento lo vuelve a pedir."""
        ack = json.dumps({"secuencia": secuencia, "ok": True}, ensure_ascii=False)
        if iot.publicar_texto(ack, config.TEMA_ACK_ROBOT, qos=0):
            print(f"T2: ACK enviado para la secuencia {secuencia}")
        else:
            print(f"T2: no se pudo enviar el ACK de la secuencia {secuencia}")

    # ------------------------------------------------------------------
    # API para main.py (T4)
    # ------------------------------------------------------------------
    def enviar_vision(self, linea):
        """Envía una línea de visión al robot. qos 0: nunca espera la red."""
        return iot.publicar_texto(linea, config.TEMA_VISION, qos=0)

    def conectado(self):
        """True si el cliente MQTT compartido está conectado."""
        return iot.conectado()

    def cerrar(self, descartar=True, timeout=10):
        """Detiene el worker y, si `descartar`, descarta lo pendiente.

        Si `descartar` es False, el worker drena la cola pendiente (envía los
        reportes, incluido el final) antes de terminar.
        Lo pendiente se descarta a propósito cuando se descarta: sin ACK el
        robot no derriba, que es lo correcto al cerrar. No cierra el cliente
        MQTT compartido; eso lo hace `iot.cerrar()` desde `main.py`.
        """
        self._parar.set()
        if descartar:
            while True:
                try:
                    self._cola.get_nowait()
                except queue.Empty:
                    break
                else:
                    self._cola.task_done()

        if self._hilo.is_alive():
            self._hilo.join(timeout=timeout)

    def enviar_final(self):
        """Envía un último reporte con estado 'final' si hay enlace disponible.

        Usa el último reporte recibido del robot y le pone estado 'final'. Si el
        último ya era 'final', no duplica. Devuelve True si se intentó enviar.
        """
        reporte = self.ultimo_reporte
        secuencia = self.ultima_secuencia
        if not isinstance(reporte, dict) or secuencia is None:
            print("T2: no hay reporte previo para enviar como final")
            return False
        if reporte.get("estado") == "final":
            return True
        copia = dict(reporte)
        copia["estado"] = "final"
        try:
            self._procesar(secuencia, copia)
        except Exception as error:
            print(f"T2: error al enviar el reporte final: {error}")
            return False
        return True
