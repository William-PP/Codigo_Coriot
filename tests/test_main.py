"""T7/T9: pruebas del orquestador main.py (sin cámara, broker ni red)."""

import io
import json
import os
import tempfile
import unittest
from unittest import mock

import config
import main


class CamaraFalsa:
    def __init__(self, frames=None):
        self._frames = list(frames) if frames is not None else [object()]
        self._indice = 0
        self.cerrada = False

    def leer(self):
        if self._indice < len(self._frames):
            frame = self._frames[self._indice]
            self._indice += 1
            return frame
        return None

    def cerrar(self):
        self.cerrada = True


class FrameFalso:
    shape = (100, 200, 3)


class EnlaceFalso:
    def __init__(self):
        self.visiones = []
        self.conectado_valor = True
        self.ultima_secuencia = None
        self.ultimo_reporte = None
        self.cerrado = False
        self.envio_final = False

    def enviar_vision(self, linea):
        self.visiones.append(linea)
        return True

    def conectado(self):
        return self.conectado_valor

    def enviar_final(self):
        self.envio_final = True
        return True

    def cerrar(self, descartar=True, timeout=10):
        self.cerrado = True
        self.descartar = descartar


class TestMain(unittest.TestCase):
    def test_equipo_e_intento_obligatorios_no_arrancan_enlace(self):
        with mock.patch.object(main, "EnlaceRobot") as enlace_cls:
            enlace_cls.side_effect = AssertionError("no debe crearse sin identidad")
            salida = io.StringIO()
            with mock.patch("sys.stdout", salida):
                main.ejecutar(
                    camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
                    detector=lambda frame: [],
                    mostrar=False,
                    max_iteraciones=1,
                    equipo=None,
                    intento=None,
                )
            enlace_cls.assert_not_called()
            self.assertIn("no se inicia el enlace", salida.getvalue())

    def test_con_identidad_crea_enlace(self):
        with mock.patch.object(main, "EnlaceRobot") as enlace_cls:
            instancia = EnlaceFalso()
            enlace_cls.return_value = instancia
            main.ejecutar(
                camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
                detector=lambda frame: [],
                mostrar=False,
                max_iteraciones=1,
                equipo="E01",
                intento="1",
            )
            enlace_cls.assert_called_once()
            self.assertTrue(instancia.cerrado)

    def test_enlace_inyectado_no_se_cierra_por_ejecutar(self):
        enlace = EnlaceFalso()
        main.ejecutar(
            camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
            detector=lambda frame: [],
            enlace=enlace,
            mostrar=False,
            max_iteraciones=1,
        )
        self.assertFalse(enlace.cerrado)

    def test_registro_de_inferencias(self):
        registros = []

        def detector(frame):
            return [("H", 0.9, (10, 20, 30, 40))]

        main.ejecutar(
            camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
            detector=detector,
            enlace=EnlaceFalso(),
            mostrar=False,
            max_iteraciones=1,
            registrar_inferencias=registros.append,
        )
        self.assertEqual(len(registros), 1)
        r = registros[0]
        self.assertEqual(r["clase"], "H")
        self.assertAlmostEqual(r["confianza"], 0.9)
        self.assertEqual(r["caja"], [10, 20, 30, 40])
        self.assertIn("timestamp", r)
        self.assertIn("frame", r)
        self.assertEqual(r["frame"], 1)

    def test_registro_en_archivo_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "inferencias.jsonl")
            main.ejecutar(
                camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
                detector=lambda frame: [("S", 0.5, (1, 2, 3, 4))],
                enlace=EnlaceFalso(),
                mostrar=False,
                max_iteraciones=1,
                archivo_inferencias=path,
            )
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                lineas = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lineas), 1)
            self.assertEqual(lineas[0]["clase"], "S")

    def test_envio_de_vision_con_enlace(self):
        enlace = EnlaceFalso()
        main.ejecutar(
            camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
            detector=lambda frame: [("H", 0.9, (0, 0, 10, 20))],
            enlace=enlace,
            mostrar=False,
            max_iteraciones=1,
        )
        self.assertTrue(any(l.startswith("D,1,H,") for l in enlace.visiones))

    def test_sin_enlace_no_envia_vision(self):
        main.ejecutar(
            camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
            detector=lambda frame: [("H", 0.9, (0, 0, 10, 10))],
            mostrar=False,
            max_iteraciones=1,
            equipo=None,
            intento=None,
        )
        # no enlace -> no AttributeError; simplemente no se envía.
        self.assertTrue(True)

    def test_envio_final_al_cerrar(self):
        enlace = EnlaceFalso()
        enlace.ultimo_reporte = {"secuencia": 7, "estado": "en_curso", "cuadrantes": []}
        enlace.ultima_secuencia = 7
        main.ejecutar(
            camara_fabrica=lambda: CamaraFalsa([FrameFalso()]),
            detector=lambda frame: [],
            enlace=enlace,
            mostrar=False,
            max_iteraciones=1,
        )
        self.assertTrue(enlace.envio_final)
        # El enlace inyectado no se cierra aquí (lo gestiona quien lo inyecta).

    def test_cargar_detector_usa_yolo(self):
        with mock.patch("logica.deteccion_yolo.detectar") as detectar:
            detectar.return_value = []
            fn = main.cargar_detector()
            self.assertIs(fn, detectar)


if __name__ == "__main__":
    unittest.main()
