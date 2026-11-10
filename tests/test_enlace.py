"""T7: pruebas de `EnlaceRobot` con un `iot` falso (sin broker ni red)."""

import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import config
import logica.robot_mqtt as rm


class IoTFalso:
    """Cliente compartido falso. Registra publicaciones y permite bloquearlas."""

    def __init__(self):
        self._cond = threading.Condition()
        self.suscripciones = {}
        self.publicaciones = []   # (reporte, tema) solo si hubo PUBACK
        self.textos = []          # (texto, tema, qos)
        self.publicar_ok = True
        self.liberar = threading.Event()
        self.liberar.set()
        self.publicar_iniciado = threading.Event()
        self.llamadas_publicar = 0

    def suscribir(self, tema, callback, qos=1):
        with self._cond:
            self.suscripciones[tema] = (callback, qos)
            self._cond.notify_all()
        return True

    def publicar(self, reporte, tema):
        with self._cond:
            self.llamadas_publicar += 1
            self._cond.notify_all()
        self.publicar_iniciado.set()
        self.liberar.wait(2)          # el test decide cuándo hay PUBACK
        if not self.publicar_ok:
            return False
        with self._cond:
            self.publicaciones.append((reporte, tema))
            self._cond.notify_all()
        return True

    def publicar_texto(self, texto, tema, qos=0):
        with self._cond:
            self.textos.append((texto, tema, qos))
            self._cond.notify_all()
        return True

    def conectado(self):
        return True

    def bloquear(self):
        self.liberar.clear()
        self.publicar_iniciado.clear()

    def desbloquear(self):
        self.liberar.set()

    def esperar(self, condicion, timeout=2.0):
        with self._cond:
            return self._cond.wait_for(lambda: condicion(self), timeout)


class BaseEnlace(unittest.TestCase):
    def setUp(self):
        self._iot_original = rm.iot
        self.iot = IoTFalso()
        rm.iot = self.iot
        self.enlaces = []

    def tearDown(self):
        self.iot.desbloquear()
        for enlace in self.enlaces:
            enlace.cerrar()
        rm.iot = self._iot_original

    def crear(self):
        enlace = rm.EnlaceRobot()
        self.enlaces.append(enlace)
        return enlace

    def reportar(self, texto):
        callback, _qos = self.iot.suscripciones[config.TEMA_REPORTE_ROBOT]
        callback(config.TEMA_REPORTE_ROBOT, texto)

    def reportar_json(self, datos):
        self.reportar(json.dumps(datos, ensure_ascii=False))

    def ack_textos(self):
        return [t for t in self.iot.textos if t[1] == config.TEMA_ACK_ROBOT]

    def _esperar(self, condicion, timeout=1.0):
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            if condicion():
                return True
            time.sleep(0.005)
        return False

    def esperar_cola(self, enlace, timeout=1.0):
        return self._esperar(
            lambda: enlace._cola.unfinished_tasks == 0, timeout
        )


class TestEnlaceRobot(BaseEnlace):
    def test_publica_reporte_y_usa_un_solo_cliente(self):
        enlace = self.crear()

        self.assertEqual(list(self.iot.suscripciones), [config.TEMA_REPORTE_ROBOT])
        _callback, qos = self.iot.suscripciones[config.TEMA_REPORTE_ROBOT]
        self.assertEqual(qos, 1)
        self.assertIs(rm.iot, self.iot)
        self.assertFalse(hasattr(rm, "mqtt"), "robot_mqtt no debe crear otro cliente")
        fuente = Path(rm.__file__).read_text(encoding="utf-8")
        self.assertNotIn("mqtt.Client", fuente)

        reporte = {"secuencia": 1, "estado": "en_curso", "cuadrantes": []}
        self.reportar_json(reporte)
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))

        self.assertEqual(
            self.iot.publicaciones, [(reporte, config.SERVIDOR_TEMA)]
        )
        self.assertEqual(enlace.ultima_secuencia, 1)
        self.assertEqual(enlace.ultimo_reporte, reporte)
        self.assertEqual(len(self.ack_textos()), 1)

    def test_ack_solo_despues_del_puback(self):
        enlace = self.crear()
        self.iot.bloquear()

        inicio = time.monotonic()
        self.reportar_json({"secuencia": 2, "estado": "en_curso"})
        duracion = time.monotonic() - inicio
        self.assertLess(duracion, 0.25, "on_message bloqueó el hilo de red")

        self.assertTrue(self.iot.publicar_iniciado.wait(1), "el worker no publicó")
        self.assertEqual(self.ack_textos(), [], "hubo ACK antes del PUBACK")
        self.assertEqual(self.iot.publicaciones, [])

        self.iot.desbloquear()
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))
        self.assertEqual(len(self.iot.publicaciones), 1)
        self.assertEqual(len(self.ack_textos()), 1)

    def test_sin_puback_no_hay_ack(self):
        enlace = self.crear()
        self.iot.publicar_ok = False

        self.reportar_json({"secuencia": 3, "estado": "en_curso"})
        self.assertTrue(self.iot.esperar(lambda i: i.llamadas_publicar == 1))
        self.assertTrue(self.esperar_cola(enlace))

        self.assertEqual(self.iot.publicaciones, [])
        self.assertEqual(self.ack_textos(), [])
        self.assertEqual(enlace._reenviadas, {})
        self.assertEqual(enlace.ultima_secuencia, 3)

    def test_reintento_tras_fallo_de_puback_vuelve_a_publicar(self):
        enlace = self.crear()
        self.iot.publicar_ok = False
        texto = json.dumps({"secuencia": 4, "estado": "en_curso"})

        self.reportar(texto)
        self.assertTrue(self.iot.esperar(lambda i: i.llamadas_publicar == 1))
        self.assertTrue(self.esperar_cola(enlace))
        self.assertEqual(self.ack_textos(), [])

        self.iot.publicar_ok = True
        self.reportar(texto)          # reintento idéntico del robot
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))

        self.assertEqual(self.iot.llamadas_publicar, 2)
        self.assertEqual(len(self.iot.publicaciones), 1)
        self.assertEqual(len(self.ack_textos()), 1)

    def test_reintento_identico_solo_recibe_ack_sin_republicar(self):
        enlace = self.crear()
        texto = json.dumps({"secuencia": 5, "estado": "en_curso"})

        self.reportar(texto)
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))
        self.reportar(texto)
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 2))

        self.assertEqual(self.iot.llamadas_publicar, 1)
        self.assertEqual(len(self.iot.publicaciones), 1)
        self.assertEqual(len(self.ack_textos()), 2)

    def test_misma_secuencia_con_otro_contenido_se_reenvia(self):
        enlace = self.crear()
        primero = {"secuencia": 6, "estado": "en_curso"}
        segundo = {"secuencia": 6, "estado": "final"}

        self.reportar_json(primero)
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))
        self.reportar_json(segundo)
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 2))

        self.assertEqual(self.iot.llamadas_publicar, 2)
        self.assertEqual(
            [p[0]["estado"] for p in self.iot.publicaciones],
            ["en_curso", "final"],
        )
        self.assertEqual(len(self.ack_textos()), 2)

    def test_json_invalido_descartado(self):
        enlace = self.crear()

        self.reportar("esto no es json")
        self.assertTrue(self.esperar_cola(enlace))

        self.assertEqual(self.iot.publicaciones, [])
        self.assertEqual(self.iot.textos, [])
        self.assertIsNone(enlace.ultima_secuencia)
        self.assertIsNone(enlace.ultimo_reporte)

    def test_json_no_objeto_descartado(self):
        enlace = self.crear()

        for texto in ("[]", "42", "null", '"texto"', "true"):
            with self.subTest(texto=texto):
                self.reportar(texto)

        self.assertTrue(self.esperar_cola(enlace))
        self.assertEqual(self.iot.publicaciones, [])
        self.assertEqual(self.iot.textos, [])
        self.assertIsNone(enlace.ultima_secuencia)

    def test_secuencia_invalida_descartada(self):
        enlace = self.crear()
        casos = [
            {},
            {"secuencia": True},
            {"secuencia": None},
            {"secuencia": "abc"},
            {"secuencia": 1.5},
            {"secuencia": []},
        ]

        for datos in casos:
            with self.subTest(datos=datos):
                self.reportar_json(datos)

        self.assertTrue(self.esperar_cola(enlace))
        self.assertEqual(self.iot.publicaciones, [])
        self.assertEqual(self.iot.textos, [])
        self.assertIsNone(enlace.ultima_secuencia)

    def test_secuencia_numerica_en_texto_aceptada(self):
        enlace = self.crear()

        self.reportar_json({"secuencia": "7", "estado": "en_curso"})
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))

        self.assertEqual(enlace.ultima_secuencia, 7)
        self.assertEqual(
            json.loads(self.ack_textos()[0][0]),
            {"secuencia": 7, "ok": True},
        )
        # El reporte se reenvía tal cual: la secuencia textual no se reescribe.
        self.assertEqual(self.iot.publicaciones[0][0]["secuencia"], "7")

    def test_vision_usa_qos_0_y_el_tema_del_robot(self):
        enlace = self.crear()
        linea = "D,1,H,500,125,188,90"

        self.assertTrue(enlace.enviar_vision(linea))
        self.assertEqual(
            self.iot.textos,
            [(linea, config.TEMA_VISION, 0)],
        )
        self.assertEqual(config.TEMA_VISION, f"coriot/vision/{config.ROBOT_ID}")

    def test_ack_usa_qos_0_y_el_formato_esperado(self):
        enlace = self.crear()

        self.reportar_json({"secuencia": 13, "estado": "en_curso"})
        self.assertTrue(self.iot.esperar(lambda i: len(i.textos) == 1))

        texto, tema, qos = self.ack_textos()[0]
        self.assertEqual(tema, config.TEMA_ACK_ROBOT)
        self.assertEqual(qos, 0)
        self.assertEqual(json.loads(texto), {"secuencia": 13, "ok": True})

    def test_cola_llena_descarta_sin_bloquear(self):
        self.iot.bloquear()
        with mock.patch.object(rm, "COLA_MAX", 2):
            enlace = self.crear()
            self.reportar_json({"secuencia": 1})
            self.assertTrue(self.iot.publicar_iniciado.wait(1))
            self.reportar_json({"secuencia": 2})
            self.reportar_json({"secuencia": 3})
            self.assertEqual(enlace._cola.qsize(), 2)

            salida = io.StringIO()
            with redirect_stdout(salida):
                self.reportar_json({"secuencia": 4})

            self.assertEqual(enlace._cola.qsize(), 2)
            self.assertIn("cola llena", salida.getvalue())

    def test_reporte_con_null_se_reenvia_tal_cual(self):
        enlace = self.crear()
        reporte = {
            "equipo": "E01",
            "intento": "1",
            "secuencia": 21,
            "estado": "en_curso",
            "cuadrantes": [
                {"color": "rojo", "explorado": True, "heridos": 2, "necesitan_suministros": 1},
                {"color": "azul", "explorado": False, "heridos": None, "necesitan_suministros": None},
                {"color": "verde", "explorado": False, "heridos": None, "necesitan_suministros": None},
                {"color": "amarillo", "explorado": False, "heridos": None, "necesitan_suministros": None},
            ],
        }
        self.reportar_json(reporte)
        self.assertTrue(self.iot.esperar(lambda i: len(i.publicaciones) == 1))

        self.assertEqual(self.iot.publicaciones[0][0], reporte)
        self.assertEqual(self.iot.publicaciones[0][1], config.SERVIDOR_TEMA)

    def test_limite_1_msg_por_segundo_sin_perdida(self):
        # Intervalo pequeño para no alargar la suite, pero > 0.
        enlace = rm.EnlaceRobot(intervalo_servidor=0.05, dormir=lambda _s: None)
        self.enlaces.append(enlace)
        textos = [
            json.dumps({"secuencia": i, "estado": "en_curso"}, ensure_ascii=False)
            for i in (31, 32, 33)
        ]
        for texto in textos:
            self.reportar(texto)
        # Esperar a que los tres salgan (con intervalo 0.05 -> ~0.1 s).
        self.assertTrue(self._esperar(lambda: len(self.iot.publicaciones) == 3, 3.0))

        enviadas = [p[0]["secuencia"] for p in self.iot.publicaciones]
        self.assertEqual(enviadas, [31, 32, 33])
        self.assertEqual(len(self.iot.textos), 3)  # 3 ACKs

    def test_servidor_no_configurado_no_envia_ack(self):
        original = config.SERVIDOR_TEMA
        try:
            config.SERVIDOR_TEMA = ""
            enlace = self.crear()
            self.reportar_json({"secuencia": 41, "estado": "en_curso"})
            self.assertTrue(self.esperar_cola(enlace))
            self.assertEqual(self.iot.publicaciones, [])
            self.assertEqual(self.ack_textos(), [])
        finally:
            config.SERVIDOR_TEMA = original
        self.iot.bloquear()
        enlace = self.crear()

        self.reportar_json({"secuencia": 8})
        self.assertTrue(self.iot.publicar_iniciado.wait(1))
        self.reportar_json({"secuencia": 9})
        self.reportar_json({"secuencia": 10})

        cerrador = threading.Thread(target=enlace.cerrar)
        cerrador.start()
        try:
            self.assertTrue(self._esperar(lambda: enlace._parar.is_set()))
            self.assertTrue(self._esperar(lambda: enlace._cola.empty()))
            self.iot.desbloquear()
            cerrador.join(2)
        finally:
            self.iot.desbloquear()
            cerrador.join(2)

        self.assertFalse(cerrador.is_alive())
        self.assertFalse(enlace._hilo.is_alive())
        self.assertEqual(
            [p[0]["secuencia"] for p in self.iot.publicaciones], [8]
        )
        self.assertEqual(self.iot.llamadas_publicar, 1)
        self.assertIs(rm.iot, self.iot)


if __name__ == "__main__":
    unittest.main()
