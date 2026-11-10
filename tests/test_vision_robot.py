"""T7: pruebas de `linea_vision`, escala y filtro vertical (sin cámara)."""

import unittest

from logica.filtros import solo_verticales
from logica.vision_robot import SIN_FIGURA, _escala, linea_vision


class TestEscala(unittest.TestCase):
    def test_escala_usa_1000_entre_ancho_frame(self):
        factor = 1000.0 / 640
        self.assertEqual(_escala(80, factor), 125)
        self.assertEqual(_escala(120, factor), 188)
        self.assertEqual(_escala(0, factor), 0)

    def test_escala_redondea_al_entero_mas_cercano(self):
        self.assertEqual(_escala(1.49, 1.0), 1)
        self.assertEqual(_escala(1.5, 1.0), 2)
        self.assertEqual(_escala(0.5, 1.0), 1)

    def test_escala_limita_entre_0_y_1000(self):
        self.assertEqual(_escala(-10, 1.0), 0)
        self.assertEqual(_escala(999.9, 1.0), 1000)
        self.assertEqual(_escala(1001, 1.0), 1000)


class TestLineaVision(unittest.TestCase):
    def test_sin_detecciones_devuelve_sin_figura(self):
        self.assertEqual(linea_vision([], 640), [SIN_FIGURA])
        self.assertEqual(
            linea_vision([], 640), ["D,0,H,500,0,0,0"]
        )

    def test_ancho_frame_invalido_devuelve_sin_figura(self):
        for ancho in (0, -1, -640):
            with self.subTest(ancho=ancho):
                self.assertEqual(linea_vision([], ancho), [SIN_FIGURA])

    def test_caja_h_80x120_escala_1000_640(self):
        # Caso de aceptación T3 y del pipeline T4.
        self.assertEqual(
            linea_vision([("H", 0.90, (280, 180, 80, 120))], 640),
            ["D,1,H,500,125,188,90"],
        )

    def test_caja_s_80x120_en_el_borde_izquierdo(self):
        # x=0, w=80 -> centro 40 px; factor 1000/640.
        self.assertEqual(
            linea_vision([("S", 0.80, (0, 0, 80, 120))], 640),
            ["D,1,S,63,125,188,80"],
        )

    def test_orden_fijo_h_luego_s(self):
        detecciones = [
            ("S", 0.80, (0, 0, 80, 120)),
            ("H", 0.90, (280, 180, 80, 120)),
        ]
        self.assertEqual(
            linea_vision(detecciones, 640),
            ["D,1,H,500,125,188,90", "D,1,S,63,125,188,80"],
        )

    def test_misma_clase_gana_mayor_confianza(self):
        detecciones = [
            ("H", 0.40, (0, 0, 80, 120)),
            ("H", 0.90, (280, 180, 80, 120)),
        ]
        self.assertEqual(
            linea_vision(detecciones, 640),
            ["D,1,H,500,125,188,90"],
        )

    def test_clase_desconocida_se_ignora(self):
        self.assertEqual(
            linea_vision([("X", 0.90, (280, 180, 80, 120))], 640),
            [SIN_FIGURA],
        )
        self.assertEqual(
            linea_vision(
                [
                    ("X", 0.90, (0, 0, 100, 200)),
                    ("S", 0.80, (0, 0, 80, 120)),
                ],
                640,
            ),
            ["D,1,S,63,125,188,80"],
        )

    def test_conf_se_convierte_a_0_100(self):
        casos = {
            0.0: 0,
            1.0: 100,
            0.904: 90,
            0.905: 91,
            1.5: 100,
            -0.2: 0,
        }
        for conf, esperado in casos.items():
            with self.subTest(conf=conf):
                linea = linea_vision(
                    [("H", conf, (280, 180, 80, 120))], 640
                )[0]
                self.assertEqual(int(linea.rsplit(",", 1)[1]), esperado)

    def test_centro_usa_x_mas_mitad_del_ancho(self):
        # x=100, w=80 -> centro 140 px; 140 * 1.5625 = 218.75 -> 219.
        self.assertEqual(
            linea_vision([("H", 0.90, (100, 50, 80, 120))], 640),
            ["D,1,H,219,125,188,90"],
        )

    def test_escala_con_ancho_frame_800(self):
        # factor 1000/800 = 1.25: centro 340 -> 425; w=100; h=150.
        self.assertEqual(
            linea_vision([("H", 0.90, (300, 100, 80, 120))], 800),
            ["D,1,H,425,100,150,90"],
        )

    def test_caja_fuera_del_frame_se_limita_a_1000(self):
        # x=620, w=100 -> centro 670 -> 1046.875, limitado a 1000.
        self.assertEqual(
            linea_vision([("H", 0.50, (620, 10, 100, 200))], 640),
            ["D,1,H,1000,156,313,50"],
        )


class TestSoloVerticales(unittest.TestCase):
    def test_filtra_cajas_no_verticales_y_conserva_orden(self):
        detecciones = [
            ("H", 0.9, (0, 0, 80, 120)),
            ("S", 0.8, (0, 0, 120, 80)),
            ("H", 0.7, (0, 0, 100, 100)),
            ("S", 0.6, (0, 0, 100, 120)),
        ]
        self.assertEqual(
            solo_verticales(detecciones),
            [detecciones[0], detecciones[3]],
        )

    def test_umbral_exacto_y_lista_vacia(self):
        self.assertEqual(solo_verticales([]), [])
        self.assertEqual(
            len(solo_verticales([("H", 0.9, (0, 0, 100, 120))])), 1
        )
        self.assertEqual(
            solo_verticales([("H", 0.9, (0, 0, 100, 119))]), []
        )
        self.assertEqual(
            solo_verticales([("H", 0.9, (0, 0, 0, 120))]), []
        )


if __name__ == "__main__":
    unittest.main()
