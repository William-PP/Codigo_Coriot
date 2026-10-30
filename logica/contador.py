"""Conteo de víctimas por cuadrante sin contar la misma figura dos veces."""

import config

PERDIDA_MAX = 15   # frames sin ver una pista antes de descartarla
SALTO_MAX = 90     # píxeles máximos entre centros para seguir la misma figura


class Contador:
    """Sigue las detecciones frame a frame y cuenta cada víctima una sola vez.

    Una figura se cuenta cuando se ha visto en `confirma` frames seguidos.
    Si desaparece de la vista más de PERDIDA_MAX frames, se olvida (y si vuelve
    a aparecer podría contarse otra vez; el derribo es la confirmación real).
    """

    def __init__(self, confirma=None):
        self.confirma = config.CONFIRMA_FRAMES if confirma is None else confirma
        self.conteo = {}    # (cuadrante, clase) -> total
        self._pistas = []   # figuras en seguimiento

    def actualizar(self, detecciones, cuadrante=None):
        """Procesa las detecciones del frame y devuelve el conteo acumulado."""
        for pista in self._pistas:
            pista["perdida"] += 1

        for clase, _, (x, y, w, h) in detecciones:
            cx, cy = x + w / 2, y + h / 2
            pista = self._buscar(clase, cx, cy, cuadrante)
            if pista is None:
                self._pistas.append(
                    {
                        "clase": clase,
                        "cx": cx,
                        "cy": cy,
                        "cuadrante": cuadrante,
                        "visto": 1,
                        "contada": False,
                        "perdida": 0,
                    }
                )
            else:
                pista.update(cx=cx, cy=cy, visto=pista["visto"] + 1, perdida=0)

        for pista in self._pistas:
            if pista["contada"] or pista["visto"] < self.confirma:
                continue
            pista["contada"] = True
            clave = (int(pista["cuadrante"] or 0), pista["clase"])
            self.conteo[clave] = self.conteo.get(clave, 0) + 1

        self._pistas = [p for p in self._pistas if p["perdida"] <= PERDIDA_MAX]
        return self.conteo

    def _buscar(self, clase, cx, cy, cuadrante):
        """Devuelve la pista más cercana del mismo tipo, o None si es nueva."""
        mejor = None
        mejor_dist = SALTO_MAX
        for pista in self._pistas:
            if pista["clase"] != clase or pista["cuadrante"] != cuadrante:
                continue
            dist = ((pista["cx"] - cx) ** 2 + (pista["cy"] - cy) ** 2) ** 0.5
            if dist < mejor_dist:
                mejor, mejor_dist = pista, dist
        return mejor

    def reporte(self):
        """Conteo en formato {cuadrante: {"H": n, "S": n}} (0 = sin cuadrante)."""
        salida = {}
        for (cuadrante, clase), total in self.conteo.items():
            salida.setdefault(cuadrante, {"H": 0, "S": 0})[clase] = total
        return salida


if __name__ == "__main__":
    # Prueba sin cámara: la misma figura 6 frames seguidos debe contar 1 vez.
    contador = Contador(confirma=5)
    for i in range(6):
        caja = (300 + i, 200, 80, 120)  # se mueve 1 px por frame
        contador.actualizar([("H", 0.9, caja)], cuadrante=2)
    print("una figura vista 6 frames:", contador.reporte())

    # Dos figuras separadas en el mismo frame deben contar 2.
    contador = Contador(confirma=3)
    for _ in range(3):
        contador.actualizar(
            [("H", 0.9, (100, 100, 80, 120)), ("S", 0.8, (500, 250, 80, 120))],
            cuadrante=1,
        )
    print("H y S separadas:", contador.reporte())
