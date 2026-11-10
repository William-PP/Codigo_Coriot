"""Pruebas de la lógica de la GUI: sesiones, capturas y validación mínima.

No abren la cámara real ni la ventana de Tkinter.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import app_gui
import config


class BaseTemporal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestSesiones(BaseTemporal):
    def test_crear_sesion_usa_fecha_y_hora(self):
        sesion = app_gui.crear_sesion(
            self.base, datetime(2026, 11, 12, 9, 30, 15)
        )
        self.assertEqual(sesion.name, "20261112_093015")
        self.assertTrue(sesion.is_dir())

    def test_crear_sesion_no_reutiliza_una_existente(self):
        primera = app_gui.crear_sesion(
            self.base, datetime(2026, 11, 12, 9, 30, 15)
        )
        segunda = app_gui.crear_sesion(
            self.base, datetime(2026, 11, 12, 9, 30, 15)
        )
        self.assertNotEqual(primera, segunda)
        self.assertTrue(segunda.name.startswith("20261112_093015_"))

    def test_sesion_mas_reciente(self):
        (self.base / "20260101_000000").mkdir()
        (self.base / "20260202_000000").mkdir()
        self.assertEqual(
            app_gui.sesion_mas_reciente(self.base).name, "20260202_000000"
        )

    def test_sin_sesiones_devuelve_none(self):
        self.assertIsNone(app_gui.sesion_mas_reciente(self.base))


class TestCapturas(BaseTemporal):
    def test_contar_capturas_por_prefijo(self):
        sesion = self.base / "sesion"
        sesion.mkdir()
        for nombre in (
            "H_1.jpg",
            "H_2.png",
            "S_1.jpg",
            "sin_figura_1.jpg",
            "nota.txt",
        ):
            (sesion / nombre).write_bytes(b"x")
        self.assertEqual(
            app_gui.contar_capturas(sesion),
            {"H": 2, "S": 1, "sin": 1},
        )

    def test_guardar_captura_pone_la_clase_en_el_nombre(self):
        sesion = self.base / "sesion"
        sesion.mkdir()
        frame = np.zeros((40, 40, 3), dtype=np.uint8)
        ruta = app_gui.guardar_captura(sesion, frame, "H")
        self.assertTrue(ruta.exists())
        self.assertTrue(ruta.name.startswith("H_"))
        self.assertEqual(app_gui.contar_capturas(sesion)["H"], 1)

    def test_guardar_sin_figura(self):
        sesion = self.base / "sesion"
        sesion.mkdir()
        frame = np.zeros((40, 40, 3), dtype=np.uint8)
        ruta = app_gui.guardar_captura(sesion, frame, "sin")
        self.assertTrue(ruta.name.startswith("sin_figura_"))
        self.assertEqual(app_gui.contar_capturas(sesion)["sin"], 1)

    def test_no_guarda_sin_imagen(self):
        sesion = self.base / "sesion"
        sesion.mkdir()
        with self.assertRaises(ValueError):
            app_gui.guardar_captura(sesion, None, "S")


class TestValidacionMinima(unittest.TestCase):
    def test_validacion_suficiente(self):
        confiable, faltantes = app_gui.analizar_validacion(30, {0: 10, 1: 10})
        self.assertTrue(confiable)
        self.assertEqual(faltantes, [])

    def test_validacion_con_pocas_imagenes(self):
        confiable, faltantes = app_gui.analizar_validacion(10, {0: 12, 1: 12})
        self.assertFalse(confiable)
        self.assertTrue(any("20" in texto for texto in faltantes))
        self.assertTrue(any("validación" in texto for texto in faltantes))

    def test_validacion_con_pocas_instancias_de_una_clase(self):
        confiable, faltantes = app_gui.analizar_validacion(30, {0: 5, 1: 12})
        self.assertFalse(confiable)
        self.assertTrue(any("clase H" in texto for texto in faltantes))
        self.assertTrue(any("5" in texto for texto in faltantes))


class TestPrepararDataset(BaseTemporal):
    def _crear_capturas(self, cantidad_h=30, cantidad_s=30):
        carpeta = self.base / "capturas"
        carpeta.mkdir()
        colores = {"H": (0, 140, 255), "S": (128, 0, 128)}
        for clase, cantidad in (("H", cantidad_h), ("S", cantidad_s)):
            for indice in range(cantidad):
                frame = np.full((80, 80, 3), 60, dtype=np.uint8)
                cv2.rectangle(frame, (20, 10), (60, 70), colores[clase], -1)
                cv2.imwrite(str(carpeta / f"{clase}_{indice:03d}.jpg"), frame)
        return carpeta

    def test_genera_dataset_yaml_con_validacion_suficiente(self):
        carpeta = self._crear_capturas()
        datos = app_gui.preparar_dataset(carpeta, self.base / "destino")

        self.assertTrue(datos["yaml"].exists())
        self.assertEqual(datos["train"] + datos["val"], 60)
        self.assertGreaterEqual(datos["val"], config.MIN_IMAGENES_VAL)
        self.assertGreaterEqual(datos["instancias"][0], config.MIN_INSTANCIAS_POR_CLASE)
        self.assertGreaterEqual(datos["instancias"][1], config.MIN_INSTANCIAS_POR_CLASE)
        self.assertTrue(datos["confiable"])
        self.assertEqual(datos["faltantes"], [])

        etiquetas_val = list((self.base / "destino" / "labels" / "val").glob("*.txt"))
        self.assertTrue(etiquetas_val)
        for etiqueta in etiquetas_val:
            partes = etiqueta.read_text(encoding="utf-8").split()
            self.assertIn(partes[0], ("0", "1"))
            self.assertEqual(len(partes), 5)

    def test_genera_dataset_con_validacion_insuficiente(self):
        carpeta = self._crear_capturas(cantidad_h=5, cantidad_s=5)
        datos = app_gui.preparar_dataset(carpeta, self.base / "destino")
        self.assertFalse(datos["confiable"])
        self.assertLess(datos["val"], config.MIN_IMAGENES_VAL)
        self.assertTrue(any("validación" in texto for texto in datos["faltantes"]))

    def test_rechaza_carpeta_sin_fotos_reconocibles(self):
        carpeta = self.base / "vacia"
        carpeta.mkdir()
        (carpeta / "foto.jpg").write_bytes(b"x")
        with self.assertRaises(ValueError):
            app_gui.preparar_dataset(carpeta, self.base / "destino")


class TestResultadoEntrenamiento(unittest.TestCase):
    def test_lee_resultado_no_confiable(self):
        texto = (
            "Dataset: 10 imágenes en train, 10 en val\n"
            "Aviso: validación insuficiente: 10 imágenes < 30.\n"
            "Validación INSUFICIENTE: el mAP se reportará como NO CONFIABLE.\n"
            "mAP50: NO CONFIABLE\n"
            "mAP50-95: NO CONFIABLE\n"
            "Pesos de la corrida en: C:/tmp/runs/x/weights/best.pt "
            "(no se copiaron)\n"
        )
        resultado = app_gui.parsear_resultado(texto)
        self.assertFalse(resultado["confiable"])
        self.assertTrue(resultado["no_confiable"])
        self.assertIsNone(resultado["map50"])
        self.assertIsNone(resultado["map50_95"])
        self.assertEqual(
            resultado["best"], Path("C:/tmp/runs/x/weights/best.pt")
        )

    def test_lee_resultado_confiable(self):
        texto = (
            "Validación suficiente: el mAP se puede usar (umbral 0.70).\n"
            "mAP50: 0.8123\n"
            "mAP50-95: 0.6543\n"
            "Pesos de la corrida en: C:/tmp/best.pt (no se copiaron)\n"
        )
        resultado = app_gui.parsear_resultado(texto)
        self.assertTrue(resultado["confiable"])
        self.assertFalse(resultado["no_confiable"])
        self.assertAlmostEqual(resultado["map50"], 0.8123)
        self.assertAlmostEqual(resultado["map50_95"], 0.6543)


class TestComandoEntrenamiento(unittest.TestCase):
    def test_incluye_parametros_y_no_copia_el_modelo(self):
        comando = app_gui.construir_comando_entrenamiento(
            "C:/datos/dataset.yaml",
            20,
            30,
            "cpu",
            "C:/datos/entrenamiento",
            nombre="prueba",
        )
        self.assertIn("modelo.entrenar", comando)
        self.assertIn("--data", comando)
        self.assertIn("--tiempo", comando)
        self.assertIn("20", comando)
        self.assertIn("--epocas", comando)
        self.assertIn("30", comando)
        self.assertIn("--sin-guardar", comando)
        self.assertNotIn("--guardar", comando)


class TestSinOrdenesAlRobot(unittest.TestCase):
    def test_app_gui_solo_publica_la_configuracion_retenida(self):
        fuente = (config.RAIZ / "app_gui.py").read_text(encoding="utf-8")
        for prohibido in (
            "TEMA_VISION",
            "TEMA_ACK_ROBOT",
            "coriot/vision",
            "coriot/robot/E01/ack",
            "publicar_orden",
            "enviar_vision",
            "enviar_final",
        ):
            self.assertNotIn(prohibido, fuente)
        self.assertIn("client.publish(TEMA_CONFIG", fuente)


if __name__ == "__main__":
    unittest.main()
