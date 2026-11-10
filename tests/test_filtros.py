"""T7: pruebas del filtro de figura de pie (alto >= 1.2 * ancho)."""

import unittest

from logica.filtros import es_vertical, solo_verticales


class TestEsVertical(unittest.TestCase):
    def test_80x120_si_es_vertical(self):
        self.assertTrue(es_vertical((0, 0, 80, 120)))

    def test_120x80_no_es_vertical(self):
        self.assertFalse(es_vertical((0, 0, 120, 80)))

    def test_100x100_no_es_vertical(self):
        self.assertFalse(es_vertical((0, 0, 100, 100)))

    def test_umbral_exacto_100x120_si(self):
        # 120 >= 1.2 * 100
        self.assertTrue(es_vertical((0, 0, 100, 120)))

    def test_justo_debajo_del_umbral_no(self):
        # 119 < 1.2 * 100
        self.assertFalse(es_vertical((0, 0, 100, 119)))

    def test_ancho_cero_no_es_vertical(self):
        self.assertFalse(es_vertical((0, 0, 0, 120)))
        self.assertFalse(es_vertical((0, 0, 0, 0)))


class TestSoloVerticales(unittest.TestCase):
    def test_conserva_orden_y_descarta_horizontales(self):
        detecciones = [
            ("H", 0.9, (10, 20, 80, 120)),
            ("S", 0.8, (0, 0, 120, 80)),
            ("H", 0.7, (5, 5, 100, 100)),
            ("S", 0.6, (0, 0, 100, 120)),
        ]
        self.assertEqual(
            solo_verticales(detecciones),
            [detecciones[0], detecciones[3]],
        )

    def test_lista_vacia(self):
        self.assertEqual(solo_verticales([]), [])


if __name__ == "__main__":
    unittest.main()
