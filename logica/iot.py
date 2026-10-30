"""Envío del reporte JSON al broker MQTT de la competencia."""

import json
import time

import config

_cliente = None
_ultimo = None


def _al_conectar(cliente, usuario, flags, razon, propiedades):
    """Avisa una sola vez si la conexión funcionó."""
    # En paho 2.x `razon` es un ReasonCode, no un int: su valor está en .value
    valor = getattr(razon, "value", razon)
    if valor == 0:
        print(f"MQTT: conectado a {config.BROKER_HOST}:{config.BROKER_PORT} "
              f"tema={config.BROKER_TEMA}")
    else:
        print(f"MQTT: no se pudo conectar ({razon})")


def _conectar():
    """Crea el cliente una vez y lo deja conectando en segundo plano."""
    global _cliente
    if _cliente is not None:
        return _cliente

    from paho.mqtt import client as mqtt

    cliente = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=config.BROKER_CLIENTE,
    )
    if config.BROKER_USUARIO:
        cliente.username_pw_set(config.BROKER_USUARIO, config.BROKER_PASSWORD)

    cliente.on_connect = _al_conectar
    cliente.reconnect_delay_set(min_delay=1, max_delay=15)
    # connect_async + loop_start: el envío nunca bloquea el bucle de visión.
    cliente.connect_async(config.BROKER_HOST, config.BROKER_PORT, keepalive=30)
    cliente.loop_start()
    _cliente = cliente
    return cliente


def publicar(reporte, tema=None):
    """Publica el reporte. Devuelve True si se encoló (no espera al broker)."""
    global _ultimo
    try:
        cliente = _conectar()
        tema = config.BROKER_TEMA if tema is None else tema
        datos = json.dumps(reporte, ensure_ascii=False)
        _ultimo = cliente.publish(tema, datos, qos=1, retain=False)
        return True
    except ImportError:
        print("MQTT: falta paho-mqtt (pip install -r Requirements.txt)")
    except Exception as error:
        print(f"MQTT: no se pudo publicar ({error})")
    return False


def cerrar():
    """Cierra el cliente, dando tiempo a que salga el último mensaje."""
    global _cliente, _ultimo
    if _cliente is None:
        return

    # Si el mensaje se encoló antes de conectar, esperar un poco la conexión.
    limite = time.monotonic() + 3
    while _ultimo is not None and not _cliente.is_connected() and time.monotonic() < limite:
        time.sleep(0.1)

    if _ultimo is not None:
        try:
            _ultimo.wait_for_publish(timeout=3)
        except (RuntimeError, ValueError):
            pass    # el último mensaje no llegó a salir; no se puede hacer más
        _ultimo = None

    _cliente.loop_stop()
    _cliente.disconnect()
    _cliente = None
