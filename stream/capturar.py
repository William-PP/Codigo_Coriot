"""Captura frames y genera etiquetas YOLO con el detector de color."""

from datetime import datetime

import cv2

import config
from logica.deteccion_color import detectar
from logica.filtros import solo_verticales
from stream.recibir import Camara

IDS = {nombre: numero for numero, nombre in config.CLASES.items()}


def contar(carpeta):
    """Cuenta las imágenes ya guardadas en una carpeta."""
    return len(list(carpeta.glob("*.jpg")))


def a_yolo(clase, caja, ancho, alto):
    """Convierte (x, y, w, h) a la línea YOLO normalizada."""
    x, y, w, h = caja
    cx = min(max((x + w / 2) / ancho, 0.0), 1.0)
    cy = min(max((y + h / 2) / alto, 0.0), 1.0)
    bw = min(max(w / ancho, 0.0), 1.0)
    bh = min(max(h / alto, 0.0), 1.0)
    return f"{IDS[clase]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def guardar(frame, detecciones, split, forzar_vacio=False):
    """Guarda el frame y su etiqueta .txt. Devuelve la ruta de la imagen."""
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    img_dir = config.MODELO_DIR / "dataset" / "images" / split
    lbl_dir = config.MODELO_DIR / "dataset" / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    ruta_img = img_dir / f"{nombre}.jpg"
    ruta_lbl = lbl_dir / f"{nombre}.txt"

    if not cv2.imwrite(str(ruta_img), frame):
        raise RuntimeError(f"No se pudo guardar la imagen: {ruta_img}")

    alto, ancho = frame.shape[:2]
    lineas = []
    if not forzar_vacio:
        for clase, _, caja in detecciones:
            lineas.append(a_yolo(clase, caja, ancho, alto))
    ruta_lbl.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_img


def dibujar(frame, detecciones):
    """Dibuja las cajas sobre una copia del frame."""
    vista = frame.copy()
    for clase, confianza, (x, y, w, h) in detecciones:
        color = (0, 165, 255) if clase == "H" else (255, 0, 255)
        cv2.rectangle(vista, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            vista,
            f"{clase} {confianza:.2f}",
            (x, max(y - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )
    return vista


def main():
    cam = Camara()
    base = config.MODELO_DIR / "dataset" / "images"
    conteo = {"train": contar(base / "train"), "val": contar(base / "val")}
    ultimo = ""

    ventana = "Capturar dataset | s=train  v=val  n=negativo  q=salir"
    try:
        while True:
            frame = cam.leer()
            if frame is None:
                continue

            detecciones = solo_verticales(detectar(frame))
            vista = dibujar(frame, detecciones)

            cv2.putText(
                vista,
                f"train={conteo['train']}  val={conteo['val']}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            if ultimo:
                cv2.putText(
                    vista,
                    ultimo,
                    (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )

            cv2.imshow(ventana, vista)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla == ord("q"):
                break
            if tecla in (ord("s"), ord("v"), ord("n")):
                split = "val" if tecla == ord("v") else "train"
                forzar_vacio = tecla == ord("n")
                ruta = guardar(frame, detecciones, split, forzar_vacio)
                conteo[split] += 1
                ultimo = f"{split}: {ruta.name}"
                print(f"Guardado {split}: {ruta}")
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()