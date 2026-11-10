"""T7: pruebas del simulador sin red (argumentos y latencias)."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import config
from tools import simular_robot as sim


class Info:
    rc = 0


class ClienteFalso:
    def __init__(self):
        self.publicaciones = []
        self.suscripciones = []

    def subscribe(self, tema, qos=0):
        self.suscripciones.append((tema, qos))
        return (0, 1)

    def publish(self, tema, texto, qos=0, retain=False):
        self.publicaciones.append((tema, texto, qos))
        return Info()


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanzar(self, segundos):
        self.t += segundos


class TestArgumentos(unittest.TestCase):
    def test_valores_por_defecto(self):
        args = sim._argumentos([])
        self.assertEqual(args.host, config.BROKER_HOST)
        self.assertEqual(args.puerto, config.BROKER_PORT)
        self.assertEqual(args.tema_servidor, config.SERVIDOR_TEMA)
        self.assertEqual(args.duracion, 30.0)
        self.assertEqual(args.periodo, 5.0)

    def test_valores_personalizados(self):
        args = sim._argumentos(
            [
                "--host", "10.0.0.5",
                "--puerto", "1884",
                "--tema-servidor", "sim/servidor",
                "--duracion", "12.5",
                "--periodo", "2.5",
            ]
        )
        self.assertEqual(args.host, "10.0.0.5")
        self.assertEqual(args.puerto, 1884)
        self.assertEqual(args.tema_servidor, "sim/servidor")
        self.assertEqual(args.duracion, 12.5)
        self.assertEqual(args.periodo, 2.5)

    def test_puerto_no_numerico_sale_con_codigo_2(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as contexto:
                sim._argumentos(["--puerto", "abc"])
        self.assertEqual(contexto.exception.code, 2)

    def test_duracion_cero_no_crea_cliente(self):
        with mock.patch.object(sim, "crear_cliente") as crear_cliente:
            with redirect_stdout(io.StringIO()) as salida:
                codigo = sim.main(["--duracion", "0"])
        self.assertEqual(codigo, 2)
        crear_cliente.assert_not_called()
        self.assertIn("duración", salida.getvalue())

    def test_periodo_cero_no_crea_cliente(self):
        with mock.patch.object(sim, "crear_cliente") as crear_cliente:
            with redirect_stdout(io.StringIO()) as salida:
                codigo = sim.main(["--duracion", "10", "--periodo", "0"])
        self.assertEqual(codigo, 2)
        crear_cliente.assert_not_called()
        self.assertIn("periodo", salida.getvalue())


class TestLatencias(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.cliente = ClienteFalso()
        self.simulador = sim.SimuladorRobot(
            self.cliente,
            tema_servidor="sim/servidor",
            periodo=5.0,
            reloj=self.reloj,
            dormir=lambda _segundos: None,
        )
        self.simulador.iniciar()

    def _paso(self):
        with redirect_stdout(io.StringIO()):
            self.simulador._paso(self.reloj())

    def _ack(self, texto):
        with redirect_stdout(io.StringIO()):
            self.simulador._al_ack(texto)

    def test_latencia_del_ack_sin_reintentos(self):
        self._paso()
        self.assertEqual(len(self.cliente.publicaciones), 1)

        self.reloj.avanzar(0.25)
        self._ack('{"secuencia": 1, "ok": true}')

        self.assertEqual(len(self.simulador.acks), 1)
        self.assertEqual(self.simulador.acks[0]["secuencia"], 1)
        self.assertEqual(self.simulador.acks[0]["latencia"], 0.25)
        self.assertEqual(self.simulador.acks[0]["reintentos"], 0)
        self.assertIsNone(self.simulador.pendiente)
        self.assertEqual(self.simulador.siguiente_reporte, 5.25)

    def test_latencia_del_ack_tras_dos_reintentos(self):
        self._paso()                      # t = 0
        self.reloj.avanzar(8.0)
        self._paso()                      # t = 8, reintento 1
        self.reloj.avanzar(8.0)
        self._paso()                      # t = 16, reintento 2
        self.assertEqual(len(self.cliente.publicaciones), 3)

        self.reloj.avanzar(0.5)
        self._ack('{"secuencia": 1, "ok": true}')   # t = 16.5

        self.assertEqual(len(self.simulador.acks), 1)
        self.assertEqual(self.simulador.acks[0]["latencia"], 16.5)
        self.assertEqual(self.simulador.acks[0]["reintentos"], 2)
        self.assertIsNone(self.simulador.pendiente)

    def test_ack_con_otra_secuencia_se_ignora(self):
        self._paso()
        self._ack('{"secuencia": 99, "ok": true}')

        self.assertEqual(self.simulador.acks, [])
        self.assertIsNotNone(self.simulador.pendiente)
        self.assertEqual(self.simulador.pendiente["secuencia"], 1)

    def test_ack_con_ok_falso_se_ignora(self):
        self._paso()
        self._ack('{"secuencia": 1, "ok": false}')

        self.assertEqual(self.simulador.acks, [])
        self.assertIsNotNone(self.simulador.pendiente)
        self.assertEqual(self.simulador.pendiente["secuencia"], 1)


if __name__ == "__main__":
    unittest.main()
