"""Simulador del robot por MQTT para probar la laptop sin hardware (T6).

Imita al robot, no calcula nada:
  - escucha la línea de visión que envía la laptop;
  - publica reportes con secuencia creciente;
  - espera el ACK del laptop y reintenta con la misma secuencia;
  - escucha el tema del servidor para comprobar el reenvío de la laptop.

Uso:
    python tools/simular_robot.py --duracion 30

No forma parte del flujo de `main.py`; es una herramienta de pruebas.
"""

import argparse
import json
import os
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import config

TIMEOUT_ACK = 8.0
MAX_REINTENTOS = 2
PAUSA_BUCLE = 0.05


class SimuladorRobot:
    """Publica reportes y espera el ACK de la laptop.

    `reloj` y `dormir` se pueden inyectar para probar la máquina de estados
    sin esperar 8 segundos reales.
    """

    def __init__(
        self,
        cliente,
        tema_servidor=None,
        periodo=5.0,
        reloj=time.monotonic,
        dormir=time.sleep,
    ):
        self.cliente = cliente
        self.tema_servidor = tema_servidor or config.SERVIDOR_TEMA
        self.periodo = float(periodo)
        self.reloj = reloj
        self.dormir = dormir

        self._lock = threading.Lock()
        self._activo = False
        self.secuencia = 0
        self.pendiente = None
        self.siguiente_reporte = 0.0
        self.inicio = 0.0

        self.reportes_generados = 0
        self.publicaciones = 0
        self.acks = []
        self.fallos = []
        self.vision_lineas = []
        self.vision_invalidas = 0
        self.servidor_reportes = []

    # ------------------------------------------------------------------
    # Conexión y suscripciones
    # ------------------------------------------------------------------
    def preparar(self):
        """Instala los callbacks. Se llama antes de conectar."""
        self.cliente.on_message = self._al_mensaje
        self.cliente.on_connect = self._al_conectar

    def _al_conectar(self, cliente, usuario, flags, razon, propiedades):
        valor = getattr(razon, "value", razon)
        if valor == 0:
            print("Simulador: MQTT conectado")
            self._suscribir()
        else:
            print(f"Simulador: error de conexión ({razon})")

    def iniciar(self):
        """Prepara callbacks y se suscribe (para pruebas o conexión ya hecha)."""
        self.preparar()
        self._suscribir()

    def _suscribir(self):
        self.cliente.subscribe(config.TEMA_VISION, qos=0)
        self.cliente.subscribe(config.TEMA_ACK_ROBOT, qos=1)
        self.cliente.subscribe(self.tema_servidor, qos=1)

    # ------------------------------------------------------------------
    # Callbacks de mensajes
    # ------------------------------------------------------------------
    def _al_mensaje(self, cliente, usuario, mensaje):
        tema = mensaje.topic
        texto = mensaje.payload.decode("utf-8", errors="replace")
        if tema == config.TEMA_VISION:
            self._al_vision(texto)
        elif tema == config.TEMA_ACK_ROBOT:
            self._al_ack(texto)
        elif tema == self.tema_servidor:
            self._al_servidor(texto)

    def _al_vision(self, texto):
        campos = texto.split(",")
        valida = len(campos) == 7 and campos[0] == "D"
        with self._lock:
            self.vision_lineas.append(texto)
            if not valida:
                self.vision_invalidas += 1
            total = len(self.vision_lineas)

        if valida:
            print(
                f"VISION {total}: v={campos[1]} clase={campos[2]} "
                f"x={campos[3]} w={campos[4]} h={campos[5]} conf={campos[6]}"
            )
        else:
            print(f"VISION inválida {total}: {texto}")

    def _al_ack(self, texto):
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            print(f"ACK inválido (JSON): {texto}")
            return

        if not isinstance(datos, dict):
            print(f"ACK inválido (no es objeto): {texto}")
            return

        with self._lock:
            pendiente = self.pendiente
            secuencia = datos.get("secuencia")
            if pendiente is None:
                print(f"ACK ignorado: no hay reporte pendiente (seq {secuencia})")
                return
            if secuencia != pendiente["secuencia"]:
                print(
                    f"ACK ignorado: llegó seq {secuencia} y se esperaba "
                    f"{pendiente['secuencia']}"
                )
                return
            if datos.get("ok") is not True:
                print(f"ACK ignorado: ok={datos.get('ok')!r}")
                return

            latencia = self.reloj() - pendiente["inicio"]
            registro = {
                "secuencia": secuencia,
                "latencia": latencia,
                "reintentos": pendiente["reintentos"],
            }
            self.acks.append(registro)
            self.pendiente = None
            self.siguiente_reporte = self.reloj() + self.periodo

        print(
            f"ACK seq {secuencia} en {latencia:.3f}s "
            f"(intento {registro['reintentos'] + 1})"
        )

    def _al_servidor(self, texto):
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            print(f"SERVIDOR inválido (JSON): {texto}")
            return

        secuencia = datos.get("secuencia") if isinstance(datos, dict) else None
        with self._lock:
            self.servidor_reportes.append((secuencia, self.reloj()))

        estado = datos.get("estado") if isinstance(datos, dict) else None
        print(f"SERVIDOR seq {secuencia} estado {estado}")

    # ------------------------------------------------------------------
    # Reportes y reintentos
    # ------------------------------------------------------------------
    def _reporte(self, secuencia):
        """Plantilla fija: el simulador no calcula cuadrantes ni figuras."""
        cuadrantes = []
        for indice, color in enumerate(config.CUADRANTES):
            explorado = indice == 0
            cuadrantes.append(
                {
                    "color": color,
                    "explorado": explorado,
                    "heridos": 0 if explorado else None,
                    "necesitan_suministros": 0 if explorado else None,
                }
            )

        return {
            "equipo": config.ROBOT_ID,
            "intento": "SIM",
            "secuencia": secuencia,
            "estado": "en_curso",
            "cuadrantes": cuadrantes,
        }

    def _publicar_reporte(self, secuencia):
        texto = json.dumps(self._reporte(secuencia), ensure_ascii=False)
        try:
            info = self.cliente.publish(config.TEMA_REPORTE_ROBOT, texto, qos=1)
        except Exception as error:
            print(f"Simulador: no se pudo publicar el reporte ({error})")
            return False
        return info is not None and getattr(info, "rc", 0) == 0

    def _paso(self, ahora):
        """Avanza la máquina de estados: publica, reintenta o falla."""
        with self._lock:
            pendiente = self.pendiente

            if pendiente is not None:
                if ahora < pendiente["limite"]:
                    return
                if pendiente["reintentos"] < MAX_REINTENTOS:
                    pendiente["reintentos"] += 1
                    pendiente["limite"] = ahora + TIMEOUT_ACK
                    secuencia = pendiente["secuencia"]
                    intento = pendiente["reintentos"] + 1
                else:
                    secuencia = pendiente["secuencia"]
                    self.fallos.append(
                        {
                            "secuencia": secuencia,
                            "reintentos": pendiente["reintentos"],
                        }
                    )
                    self.pendiente = None
                    self.siguiente_reporte = ahora + self.periodo
                    print(f"Sin ACK seq {secuencia} tras {MAX_REINTENTOS} reintentos")
                    return
            elif ahora < self.siguiente_reporte:
                return
            else:
                self.secuencia += 1
                secuencia = self.secuencia
                self.pendiente = {
                    "secuencia": secuencia,
                    "inicio": ahora,
                    "reintentos": 0,
                    "limite": ahora + TIMEOUT_ACK,
                }
                self.reportes_generados += 1
                intento = 1

            self.publicaciones += 1
            publicada = self._publicar_reporte(secuencia)

        sufijo = "" if publicada else " (fallo de publicación)"
        print(f"REPORTE seq {secuencia} intento {intento}{sufijo}")

    # ------------------------------------------------------------------
    # Bucle y cierre
    # ------------------------------------------------------------------
    def ejecutar(self, duracion):
        """Corre durante `duracion` segundos y devuelve el resumen."""
        self.inicio = self.reloj()
        fin = self.inicio + max(0.0, float(duracion))
        self.siguiente_reporte = self.inicio
        self._activo = True

        while self._activo and self.reloj() < fin:
            self._paso(self.reloj())
            self.dormir(PAUSA_BUCLE)

        self._activo = False
        transcurrido = max(0.0, self.reloj() - self.inicio)
        self._imprimir_resumen(transcurrido)
        return transcurrido

    def cerrar(self):
        """Marca el simulador como detenido; el cliente lo cierra `main`."""
        self._activo = False

    def _imprimir_resumen(self, transcurrido):
        with self._lock:
            vision = list(self.vision_lineas)
            acks = list(self.acks)
            fallos = list(self.fallos)
            servidor = list(self.servidor_reportes)
            pendiente = self.pendiente

        print("\n--- Resumen del simulador ---")
        print(
            f"Reportes generados: {self.reportes_generados}; "
            f"publicaciones: {self.publicaciones}"
        )
        print(f"ACK recibidos: {len(acks)}")
        for ack in acks:
            print(
                f"  seq {ack['secuencia']}: {ack['latencia']:.3f}s "
                f"({ack['reintentos']} reintentos)"
            )
        if acks:
            latencias = [ack["latencia"] for ack in acks]
            print(
                f"  latencia media: {sum(latencias) / len(latencias):.3f}s; "
                f"máxima: {max(latencias):.3f}s"
            )

        print(f"Reportes sin ACK: {len(fallos)}")
        for fallo in fallos:
            print(
                f"  seq {fallo['secuencia']}: "
                f"{fallo['reintentos']} reintentos"
            )
        if pendiente is not None:
            print(f"  pendiente al terminar: seq {pendiente['secuencia']}")

        tasa = len(vision) / transcurrido if transcurrido > 0 else 0.0
        print(
            f"Visión: {len(vision)} líneas en {transcurrido:.2f}s = "
            f"{tasa:.2f} líneas/s "
            f"(inválidas: {self.vision_invalidas})"
        )
        print(f"Reportes vistos en el servidor: {len(servidor)}")


def crear_cliente():
    """Crea el único cliente del simulador, con ID distinto de la laptop."""
    from paho.mqtt import client as mqtt

    cliente = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"robot-sim-{config.ROBOT_ID}",
    )
    if config.BROKER_USUARIO:
        cliente.username_pw_set(config.BROKER_USUARIO, config.BROKER_PASSWORD)
    return cliente


def _argumentos(argv=None):
    parser = argparse.ArgumentParser(
        description="Simula al robot E01 por MQTT para probar la laptop."
    )
    parser.add_argument("--host", default=config.BROKER_HOST, help="broker MQTT")
    parser.add_argument("--puerto", type=int, default=config.BROKER_PORT)
    parser.add_argument(
        "--tema-servidor",
        default=config.SERVIDOR_TEMA,
        help="tema donde la laptop reenvía al servidor simulado",
    )
    parser.add_argument(
        "--duracion",
        type=float,
        default=30.0,
        help="segundos que corre el simulador",
    )
    parser.add_argument(
        "--periodo",
        type=float,
        default=5.0,
        help="segundos entre reportes nuevos",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _argumentos(argv)
    if args.duracion <= 0:
        print("Simulador: la duración debe ser mayor que cero")
        return 2
    if args.periodo <= 0:
        print("Simulador: el periodo debe ser mayor que cero")
        return 2

    cliente = crear_cliente()
    simulador = SimuladorRobot(
        cliente,
        tema_servidor=args.tema_servidor,
        periodo=args.periodo,
    )
    simulador.preparar()

    print(f"Simulador robot {config.ROBOT_ID} -> {args.host}:{args.puerto}")
    print(f"  publica en {config.TEMA_REPORTE_ROBOT}")
    print(
        f"  escucha {config.TEMA_VISION}, {config.TEMA_ACK_ROBOT} "
        f"y {args.tema_servidor}"
    )

    try:
        cliente.connect(args.host, args.puerto, keepalive=30)
        cliente.loop_start()
        simulador.ejecutar(args.duracion)
    except KeyboardInterrupt:
        print("\nSimulador: interrumpido por el usuario")
    except Exception as error:
        print(f"Simulador: error ({error})")
        return 1
    finally:
        simulador.cerrar()
        try:
            cliente.disconnect()
        except Exception:
            pass
        try:
            cliente.loop_stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
