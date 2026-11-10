"""Entrena YOLO11n con el dataset propio y guarda modelo/pesos/rescate.pt."""

import argparse
import csv
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import config

MIN_IMAGENES_VAL = getattr(config, "MIN_IMAGENES_VAL", 30)
MIN_INSTANCIAS_POR_CLASE = getattr(config, "MIN_INSTANCIAS_POR_CLASE", 10)
EPOCAS_PROYECCION = 30
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _leer_yaml_simple(ruta):
    """Lector mínimo de las claves path/train/val si PyYAML no está instalado."""
    datos = {}
    texto = Path(ruta).read_text(encoding="utf-8-sig", errors="replace")
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or ":" not in limpia:
            continue
        clave, valor = limpia.split(":", 1)
        clave = clave.strip()
        valor = valor.split("#", 1)[0].strip().strip('"').strip("'")
        if clave in ("path", "train", "val") and valor:
            datos[clave] = valor
    return datos


def _leer_yaml(ruta):
    try:
        import yaml
    except ImportError:
        return _leer_yaml_simple(ruta)

    with open(ruta, "r", encoding="utf-8") as archivo:
        return yaml.safe_load(archivo) or {}


def _ruta_split(dataset_yaml, split):
    """Resuelve la carpeta de imágenes de train/val desde el YAML."""
    datos = _leer_yaml(dataset_yaml)
    base = Path(datos.get("path") or Path(dataset_yaml).parent)
    valor = datos.get(split)
    if isinstance(valor, (list, tuple)):
        valor = valor[0] if valor else ""
    ruta = Path(str(valor))
    if not ruta.is_absolute():
        ruta = base / ruta
    return ruta


def contar_imagenes(split, dataset_yaml=config.DATASET_YAML):
    """Cuenta las imágenes de train o val."""
    carpeta = _ruta_split(dataset_yaml, split)
    if not carpeta.exists():
        return 0
    return sum(1 for p in carpeta.iterdir() if p.suffix.lower() in EXTENSIONES_IMAGEN)


def contar_instancias_por_clase(split, dataset_yaml=config.DATASET_YAML):
    """Cuenta las cajas etiquetadas por clase en labels/<split>."""
    imagenes = _ruta_split(dataset_yaml, split)
    etiquetas = imagenes.parent.parent / "labels" / imagenes.name
    conteo = {clase: 0 for clase in config.CLASES}
    if not etiquetas.exists():
        return conteo
    for archivo in etiquetas.glob("*.txt"):
        try:
            lineas = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for linea in lineas:
            partes = linea.split()
            if len(partes) < 5:
                continue
            try:
                clase = int(float(partes[0]))
            except (TypeError, ValueError):
                continue
            conteo[clase] = conteo.get(clase, 0) + 1
    return conteo


def _tiempos_por_epoca(csv_path, respaldo):
    """Lee la columna 'time' (acumulada) de results.csv; si falla, usa respaldo."""
    if not csv_path.exists():
        return list(respaldo)
    try:
        acumulados = []
        with open(csv_path, "r", encoding="utf-8", newline="") as archivo:
            for fila in csv.DictReader(archivo):
                valor = fila.get("time")
                if valor not in (None, ""):
                    acumulados.append(float(valor))
        if not acumulados:
            return list(respaldo)
        tiempos = []
        previo = 0.0
        for acumulado in acumulados:
            tiempos.append(max(0.0, acumulado - previo))
            previo = acumulado
        return tiempos
    except (OSError, TypeError, ValueError):
        return list(respaldo)


def _imprimir_tiempos(tiempos, duracion):
    """Imprime época, total y proyección a 30 épocas. Devuelve la proyección."""
    print("\nTiempos de entrenamiento")
    print("-----------------------")
    for indice, valor in enumerate(tiempos, 1):
        print(f"Época {indice}: {valor:.1f} s")
    if not tiempos:
        print("No se pudieron medir las épocas.")
        return None

    total_epocas = sum(tiempos)
    promedio = total_epocas / len(tiempos)
    sobrecarga = max(0.0, duracion - total_epocas)
    proyeccion = sobrecarga + promedio * EPOCAS_PROYECCION

    print(f"Total {len(tiempos)} épocas: {duracion:.1f} s ({duracion / 60:.2f} min)")
    print(f"Promedio por época: {promedio:.1f} s")
    print(
        f"Proyección {EPOCAS_PROYECCION} épocas: "
        f"{proyeccion:.1f} s ({proyeccion / 60:.1f} min)"
    )
    if sobrecarga > 1.0:
        print(f"(Incluye ~{sobrecarga:.1f} s de arranque/validación final)")
    return proyeccion


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
        "--data",
        default=str(config.DATASET_YAML),
        help="YAML del dataset (por defecto modelo/rescate.yaml)",
    )
    parser.add_argument(
        "--proyecto",
        default=str(config.MODELO_DIR / "runs"),
        help="carpeta de salida de Ultralytics",
    )
    parser.add_argument("--nombre", default="entrenar", help="nombre de la corrida")
    parser.add_argument(
        "--guardar",
        default=str(config.PESOS_ENTRENADO),
        help="ruta destino de best.pt",
    )
    parser.add_argument("--sin-guardar", action="store_true", help="no copiar best.pt")
    parser.add_argument(
        "--registro", default="logs", help="carpeta para el JSON de registro"
    )
    parser.add_argument(
        "--sin-registro", action="store_true", help="no escribir el JSON de registro"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="procesos de carga de datos (0 recomendado en Windows/CPU)",
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

    train = contar_imagenes("train", args.data)
    val = contar_imagenes("val", args.data)
    instancias = contar_instancias_por_clase("val", args.data)
    print(f"Dataset: {train} imágenes en train, {val} en val")
    print(f"Instancias en val por clase: {instancias}")
    if train == 0:
        raise SystemExit("No hay imágenes en train: revisa --data y el dataset.")

    if val < MIN_IMAGENES_VAL:
        print(
            f"Aviso: validación insuficiente: {val} imágenes "
            f"< {MIN_IMAGENES_VAL}."
        )
    for clase, nombre in config.CLASES.items():
        cantidad = instancias.get(clase, 0)
        if cantidad < MIN_INSTANCIAS_POR_CLASE:
            print(
                f"Aviso: clase {nombre} tiene {cantidad} instancias en val "
                f"< {MIN_INSTANCIAS_POR_CLASE}."
            )
    val_confiable = val >= MIN_IMAGENES_VAL and all(
        instancias.get(clase, 0) >= MIN_INSTANCIAS_POR_CLASE
        for clase in config.CLASES
    )
    if val_confiable:
        print("Validación suficiente: el mAP se puede usar (umbral 0.70).")
    else:
        print("Validación INSUFICIENTE: el mAP se reportará como NO CONFIABLE.")

    from ultralytics import YOLO

    salida = Path(args.proyecto) / args.nombre
    mejor = salida / "weights" / "best.pt"
    # Borrar el mejor modelo de una corrida anterior: si el entrenamiento falla,
    # no debemos copiar un best.pt viejo como si fuera el nuevo.
    mejor.unlink(missing_ok=True)

    modelo = YOLO(args.desde)
    kwargs = dict(
        data=str(args.data),
        epochs=args.epocas,
        batch=args.lote,
        imgsz=args.imgsz,
        patience=config.PACIENCIA,
        project=str(args.proyecto),
        name=args.nombre,
        exist_ok=True,
        plots=False,
        device=args.dispositivo,
        workers=args.workers,
    )
    if args.tiempo and args.tiempo > 0:
        kwargs["time"] = args.tiempo / 60.0  # ultralytics espera horas

    inicio = time.time()
    tiempos_callback = []

    def _fin_epoca(trainer):
        tiempos_callback.append(time.time() - inicio)

    try:
        modelo.add_callback("on_train_epoch_end", _fin_epoca)
    except Exception:
        pass

    resultados = modelo.train(**kwargs)
    duracion = time.time() - inicio

    if not mejor.exists():
        raise SystemExit(f"No se generó el modelo: falta {mejor}")

    if not args.sin_guardar:
        destino = Path(args.guardar)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mejor, destino)
        print(f"\nPesos guardados en: {destino}")
        print("El modo 'yolo' es el valor por defecto en config.py.")
    else:
        print(f"\nPesos de la corrida en: {mejor} (no se copiaron)")

    tiempos = _tiempos_por_epoca(salida / "results.csv", tiempos_callback)
    proyeccion = _imprimir_tiempos(tiempos, duracion)

    # Reportar métricas: sin validación suficiente no se presenta un mAP válido.
    map50 = None
    map5095 = None
    try:
        m = resultados.results_dict if hasattr(resultados, "results_dict") else {}
        map50 = m.get("metrics/mAP50(B)", None)
        map5095 = m.get("metrics/mAP50-95(B)", None)
        if map50 is None:
            print("mAP50: no disponible")
        elif val_confiable:
            print(f"mAP50: {map50:.4f}")
            veredicto = "suficiente (>= 0.70)" if map50 >= 0.70 else "insuficiente (< 0.70)"
            print(f"Veredicto: {veredicto}")
        else:
            print("mAP50: NO CONFIABLE")
        if map5095 is not None:
            if val_confiable:
                print(f"mAP50-95: {map5095:.4f}")
            else:
                print("mAP50-95: NO CONFIABLE")
    except Exception as error:
        print(f"No se pudieron leer las métricas: {error}")

    # Registro en logs/
    if not args.sin_registro:
        try:
            logs = Path(args.registro)
            logs.mkdir(parents=True, exist_ok=True)
            registro = {
                "fecha": datetime.now().isoformat(),
                "epocas": args.epocas,
                "lote": args.lote,
                "imgsz": args.imgsz,
                "tiempo_max_min": args.tiempo,
                "dispositivo": args.dispositivo,
                "desde": args.desde,
                "data": str(args.data),
                "train": train,
                "val": val,
                "instancias_val": {str(k): v for k, v in instancias.items()},
                "validacion_confiable": val_confiable,
                "min_imagenes_val": MIN_IMAGENES_VAL,
                "min_instancias_por_clase": MIN_INSTANCIAS_POR_CLASE,
                "duracion_s": round(duracion, 1),
                "tiempos_epoca_s": [round(t, 1) for t in tiempos],
                "proyeccion_30_epocas_s": (
                    round(proyeccion, 1) if proyeccion is not None else None
                ),
                "mAP50": (
                    float(map50) if val_confiable and map50 is not None else None
                ),
                "mAP50_crudo": (float(map50) if map50 is not None else None),
                "mAP50-95": (
                    float(map5095) if val_confiable and map5095 is not None else None
                ),
                "mAP50-95_crudo": (
                    float(map5095) if map5095 is not None else None
                ),
                "pesos": (
                    str(Path(args.guardar)) if not args.sin_guardar else str(mejor)
                ),
            }
            nombre = datetime.now().strftime("entrenamiento_%Y%m%d_%H%M%S.json")
            (logs / nombre).write_text(
                json.dumps(registro, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Registro guardado en {logs / nombre}")
        except Exception as error:
            print(f"No se pudo guardar el registro: {error}")


if __name__ == "__main__":
    main()
