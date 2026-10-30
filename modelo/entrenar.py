"""Entrena YOLO11n con el dataset propio y guarda modelo/pesos/rescate.pt."""

import argparse
import shutil

import config


def contar_imagenes(split):
    """Cuenta las imágenes .jpg de train o val."""
    carpeta = config.MODELO_DIR / "dataset" / "images" / split
    return len(list(carpeta.glob("*.jpg"))) if carpeta.exists() else 0


def main():
    parser = argparse.ArgumentParser(description="Entrena YOLO11n para Código Rescate")
    parser.add_argument("--epocas", type=int, default=config.EPOCAS)
    parser.add_argument("--lote", type=int, default=config.LOTE)
    parser.add_argument("--imgsz", type=int, default=config.TAMANO_IMG)
    parser.add_argument(
        "--desde",
        default=str(config.MODELO_BASE),
        help="pesos iniciales (por defecto yolo11n.pt)",
    )
    args = parser.parse_args()

    train = contar_imagenes("train")
    val = contar_imagenes("val")
    print(f"Dataset: {train} imágenes en train, {val} en val")
    if train == 0:
        raise SystemExit("No hay imágenes en dataset/images/train: captura primero.")
    if val == 0:
        print("Aviso: no hay imágenes en val; las métricas no serán confiables.")

    from ultralytics import YOLO

    # Borrar el mejor modelo de una corrida anterior: si el entrenamiento falla,
    # no debemos copiar un best.pt viejo como si fuera el nuevo.
    mejor = config.MODELO_DIR / "runs" / "entrenar" / "weights" / "best.pt"
    mejor.unlink(missing_ok=True)

    modelo = YOLO(args.desde)
    modelo.train(
        data=str(config.DATASET_YAML),
        epochs=args.epocas,
        batch=args.lote,
        imgsz=args.imgsz,
        patience=config.PACIENCIA,
        project=str(config.MODELO_DIR / "runs"),
        name="entrenar",
        exist_ok=True,
        plots=False,
    )

    if not mejor.exists():
        raise SystemExit(f"No se generó el modelo: falta {mejor}")

    config.PESOS_ENTRENADO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mejor, config.PESOS_ENTRENADO)
    print(f"\nPesos guardados en: {config.PESOS_ENTRENADO}")
    print('Para usarlos en el robot: MODO_DETECCION = "yolo" en config.py')


if __name__ == "__main__":
    main()
