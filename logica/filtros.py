"""Filtros físicos que se aplican a las detecciones."""

import config


def es_vertical(caja):
    """True si la caja es claramente más alta que ancha (víctima de pie)."""
    _, _, ancho, alto = caja
    return ancho > 0 and alto >= config.ASPECTO_MIN * ancho


def solo_verticales(detecciones):
    """Descarta las cajas horizontales o cuadradas (figura derribada)."""
    return [d for d in detecciones if es_vertical(d[2])]
