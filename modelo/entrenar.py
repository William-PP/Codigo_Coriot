"""Entrena YOLO11n con el dataset propio y guarda modelo/pesos/rescate.pt."""

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

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
    parser.add_argument(
        "--tiempo",
        type=int,
        default=0,
        help="tiempo máximo de entrenamiento en minutos (0 = sin límite)",
    )
    parser.add_argument(
        "--dispositivo",
        default="cpu",
        help="dispositivo: 'cpu' o índice de GPU (ej. '0')",
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
    kwargs = dict(
        data=str(config.DATASET_YAML),
        epochs=args.epocas,
        batch=args.lote,
        imgsz=args.imgsz,
        patience=config.PACIENCIA,
        project=str(config.MODELO_DIR / "runs"),
        name="entrenar",
        exist_ok=True,
        plots=False,
        device=args.dispositivo,
    )
    if args.tiempo and args.tiempo > 0:
        kwargs["time"] = args.tiempo / 60.0  # ultralytics espera horas

    inicio = time.time()
    resultados = modelo.train(**kwargs)
    duracion = time.time() - inicio

    if not mejor.exists():
        raise SystemExit(f"No se generó el modelo: falta {mejor}")

    config.PESOS_ENTRENADO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mejor, config.PESOS_ENTRENADO)
    print(f"\nPesos guardados en: {config.PESOS_ENTRENADO}")
    print('Para usarlos en el robot: MODO_DETECCION = "yolo" en config.py')

    # Reportar métricas
    try:
        m = resultados.results_dict if hasattr(resultados, "results_dict") else {}
        map50 = m.get("metrics/mAP50(B)", None)
        map5095 = m.get("metrics/mAP50-95(B)", None)
        print(f"Duración: {duracion:.1f} s")
        if map50 is not None:
            print(f"mAP50: {map50:.4f}")
        if map5095 is not None:
            print(f"mAP50-95: {map5095:.4f}")
    except Exception as error:
        print(f"No se pudieron leer las métricas: {error}")

    # Registro en logs/
    try:
        logs = Path("logs")
        logs.mkdir(parents=True, exist_ok=True)
        registro = {
            "fecha": datetime.now().isoformat(),
            "epocas": args.epocas,
            "lote": args.lote,
            "imgsz": args.imgsz,
            "tiempo_max_min": args.tiempo,
            "dispositivo": args.dispositivo,
            "desde": args.desde,
            "duracion_s": round(duracion, 1),
            "train": train,
            "val": val,
            "mAP50": (float(map50) if map50 is not None else None),
            "mAP50-95": (float(map5095) if map5095 is not None else None),
            "pesos": str(config.PESOS_ENTRENADO),
        }
        nombre = datetime.now().strftime("entrenamiento_%Y%m%d_%H%M%S.json")
        (logs / nombre).write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Registro guardado en logs/{nombre}")
    except Exception as error:
        print(f"No se pudo guardar el registro: {error}")


if __name__ == "__main__":
    main()