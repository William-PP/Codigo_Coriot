"""Evalúa el modelo entrenado sobre el conjunto de validación."""

import argparse
from pathlib import Path

import config


def contar_positivos(split):
    """Cuenta las etiquetas .txt con al menos una caja."""
    carpeta = config.MODELO_DIR / "dataset" / "labels" / split
    if not carpeta.exists():
        return 0
    return sum(1 for ruta in carpeta.glob("*.txt") if ruta.read_text().strip())


def main():
    parser = argparse.ArgumentParser(description="Evalúa rescate.pt sobre dataset/val")
    parser.add_argument("--pesos", default=str(config.PESOS_ENTRENADO))
    parser.add_argument("--imgsz", type=int, default=config.TAMANO_IMG)
    parser.add_argument("--conf", type=float, default=config.CONF_MIN)
    args = parser.parse_args()

    ruta = Path(args.pesos)
    if not ruta.exists():
        raise SystemExit(
            f"No existe {ruta}.\nEntrena primero: python -m modelo.entrenar"
        )

    positivos = contar_positivos("val")
    if positivos == 0:
        print("Aviso: ninguna imagen de val tiene cajas etiquetadas.")
        print("Las métricas medirán solo 'no detectar nada' y no sirven.")

    from ultralytics import YOLO

    modelo = YOLO(str(ruta))
    metricas = modelo.val(
        data=str(config.DATASET_YAML),
        imgsz=args.imgsz,
        conf=args.conf,
        project=str(config.MODELO_DIR / "runs"),
        name="evaluar",
        exist_ok=True,
        plots=False,
    )

    caja = metricas.box
    print()
    print("=== Resultado global ===")
    print(f"mAP50:       {caja.map50:.3f}")
    print(f"mAP50-95:    {caja.map:.3f}")
    print(f"precisión:   {caja.mp:.3f}")
    print(f"recall:      {caja.mr:.3f}")

    print("\n=== Por clase ===")
    for posicion, clase in enumerate(caja.ap_class_index):
        nombre = config.CLASES.get(int(clase), str(clase))
        print(
            f"{nombre}: precisión={caja.p[posicion]:.3f} "
            f"recall={caja.r[posicion]:.3f} "
            f"mAP50={caja.ap50[posicion]:.3f}"
        )

    print("\nInterpretación rápida:")
    print("  mAP50 > 0.70  -> usar YOLO en el robot")
    print("  mAP50 < 0.40  -> mejor quedarse con el detector de color")


if __name__ == "__main__":
    main()
