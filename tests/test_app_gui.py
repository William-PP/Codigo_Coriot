"""Pruebas de app_gui.py (sin GUI real)."""

import unittest

import config
import app_gui


class TestServidorConfigurado(unittest.TestCase):
    def test_con_tema_definido_es_true_aunque_broker_local(self):
        original_host = config.BROKER_HOST
        original_tema = config.SERVIDOR_TEMA
        try:
            config.BROKER_HOST = "127.0.0.1"
            config.SERVIDOR_TEMA = "coriot/reporte"
            self.assertTrue(app_gui._servidor_configurado())
        finally:
            config.BROKER_HOST = original_host
            config.SERVIDOR_TEMA = original_tema

    def test_sin_tema_es_false(self):
        original = config.SERVIDOR_TEMA
        try:
            config.SERVIDOR_TEMA = ""
            self.assertFalse(app_gui._servidor_configurado())
        finally:
            config.SERVIDOR_TEMA = original


if __name__ == "__main__":
    unittest.main()
