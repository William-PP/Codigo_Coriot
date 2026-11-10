"""Conexión MQTT única de la laptop (visión, reportes, servidor y ACK).

Todo usa el mismo cliente (`config.BROKER_CLIENTE`) para no abrir dos
conexiones con el mismo ID.

`publicar()` es bloqueante a propósito: espera el PUBACK del broker y devuelve
True solo si el mensaje quedó confirmado. Se llama desde el hilo de trabajo de
T2, nunca desde `on_message` ni desde el bucle de visión. Para la línea de
visión se usa `publicar_texto(..., qos=0)`, que no bloquea.
"""

import json
import threading
import time

import config

TIMEOUT_PUBACK = 5.0   # segundos máximos esperando la confirmación del broker

_cliente = None
_lock = threading.Lock()
_suscripciones = {}    # tema -> (callback, qos)
_ultimo = None


def _al_conectar(cliente, usuario, flags, razon, propiedades):
    """Avisa de la conexión y vuelve a suscribirse tras cada reconexión."""
    # En paho 2.x `razon` es un ReasonCode; su valor numérico está en .value.
    valor = getattr(razon, "value", razon)
    if valor != 0:
        print(f"MQTT: no se pudo conectar ({razon})")
        return

    print(f"MQTT: conectado a {config.BROKER_HOST}:{config.BROKER_PORT}")
    with _lock:
        temas = list(_suscripciones.items())
    for tema, (callback, qos) in temas:
        cliente.subscribe(tema, qos=qos)
        print(f"MQTT: suscrito a {tema}")


def _al_mensaje(cliente, usuario, mensaje):
    """Reparte el mensaje al callback registrado para su tema."""
    with _lock:
        entrada = _suscripciones.get(mensaje.topic)
    if entrada is None:
        return

    callback = entrada[0]
    try:
        texto = mensaje.payload.decode("utf-8", errors="replace")
        callback(mensaje.topic, texto)
    except Exception as error:
        # Un callback roto no debe tumbar el hilo de red de paho.
        print(f"MQTT: error al procesar {mensaje.topic}: {error}")


def _conectar():
    """Crea el cliente una vez y lo deja conectando en segundo plano."""
    global _cliente
    with _lock:
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
        cliente.on_message = _al_mensaje
        cliente.reconnect_delay_set(min_delay=1, max_delay=15)
        # connect_async + loop_start: conectar nunca bloquea el bucle de visión.
        cliente.connect_async(config.BROKER_HOST, config.BROKER_PORT, keepalive=30)
        cliente.loop_start()
        _cliente = cliente
        return cliente


def conectado():
    """True si el cliente existe y está conectado al broker."""
    cliente = _cliente
    return cliente is not None and cliente.is_connected()


def suscribir(tema, callback, qos=1):
    """Suscribe `callback(tema, texto)` y la renueva en cada reconexión.

    Devuelve False si falta paho-mqtt.
    """
    with _lock:
        _suscripciones[tema] = (callback, qos)

    try:
        cliente = _conectar()
    except ImportError:
        print("MQTT: falta paho-mqtt (pip install -r Requirements.txt)")
        return False

    if cliente.is_connected():
        cliente.subscribe(tema, qos=qos)
    return True


def publicar(reporte, tema):
    """Publica un JSON en `tema` y espera el PUBACK (qos 1).

    Devuelve True solo si el broker confirmó el mensaje.
    """
    if not tema:
        raise ValueError("publicar() necesita un tema")
    return publicar_texto(json.dumps(reporte, ensure_ascii=False), tema, qos=1)


def publicar_texto(texto, tema, qos=0):
    """Publica texto plano. Con qos 1 espera el PUBACK; con qos 0 no bloquea.

    Devuelve True si el mensaje salió (qos 0) o fue confirmado (qos 1).
    """
    global _ultimo
    if not tema:
        raise ValueError("publicar_texto() necesita un tema")

    try:
        cliente = _conectar()
    except ImportError:
        print("MQTT: falta paho-mqtt (pip install -r Requirements.txt)")
        return False

    if not cliente.is_connected():
        # No encolar con qos > 0: un mensaje viejo podría salir más tarde,
        # cuando ya se decidió no enviar ACK.
        if qos > 0:
            print(f"MQTT: sin conexión, no se publica en {tema}")
        return False

    try:
        info = cliente.publish(tema, texto, qos=qos, retain=False)
    except Exception as error:
        print(f"MQTT: no se pudo publicar en {tema} ({error})")
        return False

    _ultimo = info

    if qos == 0:
        return info.rc == 0   # encolado; qos 0 no tiene PUBACK

    try:
        info.wait_for_publish(timeout=TIMEOUT_PUBACK)
    except (ValueError, RuntimeError) as error:
        print(f"MQTT: sin PUBACK en {tema} ({error})")
        return False

    # En paho 2.1 wait_for_publish() no lanza al agotar el tiempo: hay que mirar.
    if not info.is_published():
        print(f"MQTT: sin PUBACK en {tema} (tiempo agotado)")
        return False
    return True


def cerrar():
    """Cierra el cliente dando un margen al último mensaje."""
    global _cliente, _ultimo
    with _lock:
        cliente = _cliente
        _cliente = None
    if cliente is None:
        return

    # Si el último mensaje se encoló antes de conectar, esperar un poco.
    limite = time.monotonic() + 3
    while _ultimo is not None and not cliente.is_connected() and time.monotonic() < limite:
        time.sleep(0.1)

    if _ultimo is not None:
        try:
            _ultimo.wait_for_publish(timeout=3)
        except (ValueError, RuntimeError):
            pass    # el último mensaje no llegó a salir; no se puede hacer más
        _ultimo = None

    cliente.loop_stop()
    cliente.disconnect()
