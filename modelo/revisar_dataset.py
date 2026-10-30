"""Revisa las etiquetas del dataset y quita las que no sirven para entrenar.

Criterios (una caja se descarta si cumple cualquiera):
  - horizontal: alto/ancho < 0.35. Una figura de pie nunca es tan plana;
    esas cajas suelen ser bordes, cintas o la figura derribada.
  - color disperso: menos del 45 % de píxeles del color dentro de la caja.
    La caja es el rectángulo que envuelve píxeles sueltos, no un objeto.
  - duplicada: dos cajas de la misma clase se solapan más de 0.50.
  - clase fuera de config.CLASES o línea con formato inválido.

Si una imagen se queda sin cajas buenas se borra entera: dejarla como
negativo enseñaría que ahí no hay víctima cuando sí la hay.
"""

import argparse

import cv2
import numpy as np

import config

NOMBRE = dict(config.CLASES)
HORIZONTAL_MAX = 0.35   # alto/ancho mínimo para que la caja pueda ser de pie
RELLENO_MIN = 0.45      # proporción mínima del color dentro de la caja
IOU_DUPLICADA = 0.50    # dos cajas iguales más solapadas son la misma


def iou(a, b):
    """Solapamiento entre dos cajas (x1, y1, x2, y2)."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    cruce = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - cruce
    return cruce / union if union > 0 else 0.0


def leer(texto, ancho, alto):
    """Convierte la etiqueta YOLO en [(clase, caja, línea original)]."""
    salida = []
    for linea in texto.splitlines():
        partes = linea.split()
        if len(partes) != 5:
            salida.append((None, None, linea))
            continue
        clase = int(float(partes[0]))
        cx, cy, bw, bh = (float(v) for v in partes[1:])
        caja = (
            max(int((cx - bw / 2) * ancho), 0),
            max(int((cy - bh / 2) * alto), 0),
            min(int((cx + bw / 2) * ancho), ancho - 1),
            min(int((cy + bh / 2) * alto), alto - 1),
        )
        salida.append((clase, caja, linea))
    return salida


def relleno(mascara, caja):
    """Proporción de píxeles del color dentro de la caja."""
    x1, y1, x2, y2 = caja
    zona = mascara[y1:y2, x1:x2]
    return float((zona > 0).mean()) if zona.size else 0.0


def revisar(imagen, ruta_lbl):
    """Devuelve (cajas buenas, [(línea, motivo)], aviso)."""
    frame = cv2.imread(str(imagen))
    if frame is None:
        return [], [], "no se pudo leer la imagen"
    alto, ancho = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mascaras = {
        nombre: cv2.inRange(hsv, np.array(bajo), np.array(alto_hsv))
        for nombre, (bajo, alto_hsv) in config.RANGOS_HSV.items()
    }

    buenas, malas = [], []
    for clase, caja, linea in leer(ruta_lbl.read_text(encoding="utf-8").strip(), ancho, alto):
        if clase not in NOMBRE or caja is None:
            malas.append((linea, "clase o formato inválido"))
            continue
        x1, y1, x2, y2 = caja
        aspecto = (y2 - y1) / (x2 - x1) if x2 > x1 else 0.0
        if aspecto < HORIZONTAL_MAX:
            malas.append((linea, f"horizontal (alto/ancho {aspecto:.2f})"))
        elif relleno(mascaras[NOMBRE[clase]], caja) < RELLENO_MIN:
            malas.append((linea, "color disperso en la caja"))
        else:
            buenas.append((clase, caja, linea))

    # Cajas repetidas: misma clase y muy solapadas.
    unicas = []
    for item in buenas:
        repetida = any(
            item[0] == otro[0] and iou(item[1], otro[1]) > IOU_DUPLICADA
            for otro in unicas
        )
        if repetida:
            malas.append((item[2], "duplicada de otra caja igual"))
        else:
            unicas.append(item)
    return unicas, malas, ""


def main():
    parser = argparse.ArgumentParser(description="Revisa las etiquetas del dataset")
    parser.add_argument(
        "--borrar",
        action="store_true",
        help="aplica las correcciones (sin esto solo informa)",
    )
    args = parser.parse_args()

    base = config.MODELO_DIR / "dataset"
    problemas = 0
    for split in ("train", "val"):
        img_dir = base / "images" / split
        lbl_dir = base / "labels" / split
        print(f"\n=== {split} ===")

        for ruta_lbl in sorted(lbl_dir.glob("*.txt")):
            imagen = img_dir / (ruta_lbl.stem + ".jpg")
            if not imagen.exists():
                print(f"  {ruta_lbl.name}: etiqueta sin imagen")
                problemas += 1
                if args.borrar:
                    ruta_lbl.unlink()
                continue

            buenas, malas, aviso = revisar(imagen, ruta_lbl)
            if aviso:
                print(f"  {imagen.name}: {aviso}")
                continue
            if not malas:
                continue

            print(f"  {imagen.name}")
            for linea, motivo in malas:
                print(f"     quitar: {motivo}  [{linea}]")
            problemas += len(malas)

            if not args.borrar:
                continue
            if buenas:
                ruta_lbl.write_text("\n".join(i[2] for i in buenas), encoding="utf-8")
            else:
                ruta_lbl.unlink()
                imagen.unlink()
                print("     imagen borrada: no le quedaba ninguna caja buena")

        for imagen in sorted(img_dir.glob("*.jpg")):
            if not (lbl_dir / (imagen.stem + ".txt")).exists():
                print(f"  {imagen.name}: imagen sin etiqueta")

    print(f"\n{problemas} etiquetas problemáticas")
    if problemas and not args.borrar:
        print("Para aplicarlo: python -m modelo.revisar_dataset --borrar")


if __name__ == "__main__":
    main()
