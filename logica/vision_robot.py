"""Línea de visión que la laptop envía al robot (protocolo v2 §6.2).

Formato: ``D,v,c,x,w,h,conf``

| Campo | Rango | Significado |
|---|---|---|
| `D` | fijo | Cabecera |
| `v` | 0 o 1 | 1 = figura detectada, 0 = ninguna |
| `c` | `H` o `S` | Clase |
| `x` | 0-1000 | Centro horizontal de la caja (500 = centro del frame) |
| `w` | 0-1000 | Ancho de la caja |
| `h` | 0-1000 | Alto de la caja |
| `conf` | 0-100 | Confianza |

`x`, `w` y `h` usan la misma escala (``factor = 1000 / ancho_frame``) para
conservar la proporción: así el firmware puede comprobar ``h >= 1.2 * w`` y
descartar las figuras derribadas.
"""

import config

SIN_FIGURA = "D,0,H,500,0,0,0"   # línea obligatoria cuando no hay detecciones


def _escala(valor, factor):
    """Pasa de píxeles a la escala 0-1000 y redondea al entero más cercano."""
    return max(0, min(1000, int(valor * factor + 0.5)))


def linea_vision(detecciones, ancho_frame):
    """Convierte las detecciones en las líneas del protocolo de visión.

    ``detecciones`` es ``[(clase, confianza 0-1, (x, y, w, h)), ...]``, como lo
    devuelven ``deteccion_color`` y ``deteccion_yolo``.

    Devuelve una lista con una línea por clase presente (máximo dos: una H y
    una S). Si no hay detecciones devuelve ``[SIN_FIGURA]``.
    """
    if ancho_frame <= 0:
        return [SIN_FIGURA]

    factor = 1000.0 / ancho_frame

    # Por clase nos quedamos con la detección de mayor confianza.
    mejores = {}
    for clase, conf, caja in detecciones:
        if clase not in config.CLASES.values():
            continue
        if clase not in mejores or conf > mejores[clase][0]:
            mejores[clase] = (conf, caja)

    if not mejores:
        return [SIN_FIGURA]

    lineas = []
    for clase in config.CLASES.values():   # orden fijo: H, luego S
        if clase not in mejores:
            continue
        conf, (x, _y, w, h) = mejores[clase]
        centro = _escala(x + w / 2, factor)
        ancho = _escala(w, factor)
        alto = _escala(h, factor)
        confianza = max(0, min(100, int(conf * 100 + 0.5)))
        lineas.append(f"D,1,{clase},{centro},{ancho},{alto},{confianza}")
    return lineas


if __name__ == "__main__":
    # Prueba sin cámara: caja de 80x120 px en un frame de 640 px (aceptación T3).
    print(linea_vision([("H", 0.90, (280, 180, 80, 120))], 640))
    print(linea_vision([], 640))
