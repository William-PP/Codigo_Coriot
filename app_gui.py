"""GUI de operación de la laptop (CORIOT GAMES 2026 - Código Rescate).

Solo controla procesos de la laptop y publica la configuración retenida.
Nunca envía órdenes de movimiento, arranque ni parada al robot.

La ventana tiene tres pestañas:
1. Operación: prepara la laptop y muestra los indicadores en vivo.
2. Captura de figuras: guarda fotos de H, S y fondos sin figura.
3. Entrenamiento: entrena el modelo con las fotos guardadas y permite
   copiar el resultado a modelo/pesos/rescate.pt.
"""

import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

import config
import main

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    TK_OK = True
except Exception:  # pragma: no cover - solo si falta tkinter
    tk = None
    filedialog = None
    messagebox = None
    ttk = None
    TK_OK = False

try:
    from PIL import Image, ImageTk

    PIL_OK = True
except Exception:  # pragma: no cover - se usa el respaldo con PNG
    Image = None
    ImageTk = None
    PIL_OK = False

try:
    from paho.mqtt import client as mqtt

    PAHO_OK = True
except Exception:
    mqtt = None
    PAHO_OK = False


TEMA_CONFIG = "coriot/robot/E01/config"

BASE_DATOS = config.RAIZ / "datos"
CAPTURAS_DIR = BASE_DATOS / "capturas"
ENTRENAMIENTO_DIR = BASE_DATOS / "entrenamiento"
LOGS_DIR = config.RAIZ / "logs"

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PREFIJOS_CAPTURA = {"H": "H", "S": "S", "sin": "sin_figura"}
RECOMENDADO_POR_CLASE = 30

COLOR_OK = "#1a7f37"
COLOR_AVISO = "#b58900"
COLOR_ERROR = "#c62828"
COLOR_NEUTRO = "#555555"
COLORES_INDICADOR = {
    "verde": COLOR_OK,
    "amarillo": COLOR_AVISO,
    "rojo": COLOR_ERROR,
    "gris": COLOR_NEUTRO,
}

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# ---------------------------------------------------------------------------
# Publicación de configuración (única salida MQTT de la GUI)
# ---------------------------------------------------------------------------
def publicar_config(equipo, intento, host=None, port=None, usuario=None, password=None, timeout=5.0):
    """Publica {"equipo","intento"} retenido (qos 1) en TEMA_CONFIG.

    Devuelve (ok, mensaje). No envía ninguna orden de movimiento/arranque/parada.
    """
    equipo = (equipo or "").strip()
    intento = (intento or "").strip()
    if not equipo or not intento:
        return False, "equipo e intento son obligatorios"

    if not PAHO_OK:
        return False, "falta paho-mqtt (pip install -r Requirements.txt)"

    host = host or config.BROKER_HOST
    port = port if port is not None else config.BROKER_PORT
    usuario = usuario if usuario is not None else config.BROKER_USUARIO
    password = password if password is not None else config.BROKER_PASSWORD

    payload = json.dumps({"equipo": equipo, "intento": intento}, ensure_ascii=False)

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="laptop-gui-E01")
    if usuario:
        cliente.username_pw_set(usuario, password)

    resultado = {"ok": False, "msg": "sin respuesta", "conectado": False, "publicado": False, "info": None}

    def on_connect(client, userdata, flags, reason, props):
        valor = getattr(reason, "value", reason)
        if valor != 0:
            resultado["msg"] = "no se pudo conectar ({})".format(reason)
            resultado["conectado"] = True
            return
        resultado["conectado"] = True
        info = client.publish(TEMA_CONFIG, payload, qos=1, retain=True)
        resultado["info"] = info

    cliente.on_connect = on_connect
    try:
        cliente.loop_start()
        cliente.connect_async(host, port, keepalive=30)
        fin = time.monotonic() + timeout + 2
        while time.monotonic() < fin and not resultado["conectado"]:
            time.sleep(0.05)
        fin2 = time.monotonic() + timeout + 2
        while time.monotonic() < fin2:
            info = resultado.get("info")
            if info is not None and info.is_published():
                resultado["ok"] = True
                resultado["publicado"] = True
                resultado["msg"] = "publicado retenido en {}: {}".format(TEMA_CONFIG, payload)
                break
            if "conectar" in resultado["msg"] or "publicado" in resultado["msg"]:
                break
            time.sleep(0.05)
        if not resultado["ok"] and resultado["msg"] == "sin respuesta":
            resultado["msg"] = "sin PUBACK (tiempo agotado)"
        cliente.loop_stop()
        cliente.disconnect()
    except Exception as error:
        resultado["msg"] = "error de conexión: {}".format(error)
        try:
            cliente.loop_stop()
            cliente.disconnect()
        except Exception:
            pass
    return resultado["ok"], resultado["msg"]


def _servidor_configurado():
    """Indica si el endpoint del servidor de la organización está configurado.

    Solo se revisa la constante del servidor (SERVIDOR_TEMA). El broker local
    127.0.0.1 NO cuenta como 'no configurado': es el broker de pruebas.
    """
    tema = (config.SERVIDOR_TEMA or "").strip()
    if not tema:
        return False
    return True


# ---------------------------------------------------------------------------
# Lógica de sesiones y capturas (sin cámara, fácil de probar)
# ---------------------------------------------------------------------------
def crear_sesion(base=None, momento=None):
    """Crea una carpeta de sesión con la fecha y hora indicadas."""
    base = Path(base) if base is not None else CAPTURAS_DIR
    base.mkdir(parents=True, exist_ok=True)
    sello = (momento or datetime.now()).strftime("%Y%m%d_%H%M%S")
    ruta = base / sello
    sufijo = 1
    while ruta.exists():
        ruta = base / "{}_{}".format(sello, sufijo)
        sufijo += 1
    ruta.mkdir(parents=True, exist_ok=False)
    return ruta


def sesion_mas_reciente(base=None):
    """Devuelve la sesión más reciente de datos/capturas/ o None."""
    base = Path(base) if base is not None else CAPTURAS_DIR
    if not base.exists():
        return None
    carpetas = [p for p in base.iterdir() if p.is_dir()]
    if not carpetas:
        return None
    return max(carpetas, key=lambda p: p.name)


def clase_de_archivo(nombre):
    """Deduce la clase a partir del prefijo del nombre del archivo."""
    base = Path(nombre).name.lower()
    if base.startswith("sin_figura") or base.startswith("sin-") or base.startswith("sin_"):
        return "sin"
    if base.startswith("h_") or base.startswith("h-"):
        return "H"
    if base.startswith("s_") or base.startswith("s-"):
        return "S"
    return None


def contar_capturas(sesion):
    """Cuenta las fotos H, S y sin figura de una sesión."""
    conteo = {"H": 0, "S": 0, "sin": 0}
    carpeta = Path(sesion)
    if not carpeta.exists():
        return conteo
    for archivo in carpeta.iterdir():
        if archivo.suffix.lower() not in EXTENSIONES_IMAGEN:
            continue
        clase = clase_de_archivo(archivo.name)
        if clase in conteo:
            conteo[clase] += 1
    return conteo


def guardar_captura(sesion, frame, clase, momento=None):
    """Guarda una imagen con la clase en el nombre. Devuelve su ruta."""
    if clase not in PREFIJOS_CAPTURA:
        raise ValueError("Clase de captura inválida: {!r}".format(clase))
    if frame is None:
        raise ValueError("La cámara todavía no entrega una imagen.")

    carpeta = Path(sesion)
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = (momento or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    ruta = carpeta / "{}_{}.jpg".format(PREFIJOS_CAPTURA[clase], sello)
    sufijo = 1
    while ruta.exists():
        ruta = carpeta / "{}_{}_{}.jpg".format(PREFIJOS_CAPTURA[clase], sello, sufijo)
        sufijo += 1

    if not cv2.imwrite(str(ruta), frame):
        raise RuntimeError("No se pudo guardar la imagen: {}".format(ruta))
    return ruta


def analizar_validacion(val, instancias, min_imagenes=None, min_instancias=None):
    """Devuelve (confiable, lista de faltantes) según los mínimos del proyecto."""
    min_imagenes = config.MIN_IMAGENES_VAL if min_imagenes is None else min_imagenes
    min_instancias = (
        config.MIN_INSTANCIAS_POR_CLASE if min_instancias is None else min_instancias
    )
    faltantes = []

    if val < min_imagenes:
        faltantes.append(
            "Faltan {} imágenes de validación (hay {}; se necesitan al menos {}).".format(
                min_imagenes - val, val, min_imagenes
            )
        )

    for clase, nombre in config.CLASES.items():
        cantidad = int(instancias.get(clase, instancias.get(str(clase), 0)))
        if cantidad < min_instancias:
            faltantes.append(
                "Faltan {} figuras de la clase {} en validación "
                "(hay {}; se necesitan al menos {}).".format(
                    min_instancias - cantidad, nombre, cantidad, min_instancias
                )
            )

    return (not faltantes), faltantes


def _contar_instancias_etiquetas(carpeta):
    """Cuenta las cajas por clase en una carpeta de etiquetas YOLO."""
    conteo = {clase: 0 for clase in config.CLASES}
    carpeta = Path(carpeta)
    if not carpeta.exists():
        return conteo
    for archivo in carpeta.glob("*.txt"):
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


def _etiqueta_para_imagen(ruta, clase):
    """Genera la etiqueta YOLO de una foto de figura (caja del color)."""
    if clase == "sin":
        return ""

    indice = 0 if clase == "H" else 1
    frame = cv2.imread(str(ruta))
    if frame is None:
        return ""

    alto, ancho = frame.shape[:2]
    lineas = []
    try:
        from logica.deteccion_color import detectar

        detecciones = detectar(frame)
    except Exception:
        detecciones = []

    for nombre_clase, _, caja in detecciones:
        if nombre_clase != clase:
            continue
        x, y, w, h = caja
        if w <= 0 or h <= 0:
            continue
        cx = min(max((x + w / 2) / ancho, 0.0), 1.0)
        cy = min(max((y + h / 2) / alto, 0.0), 1.0)
        bw = min(max(w / ancho, 0.0), 1.0)
        bh = min(max(h / alto, 0.0), 1.0)
        lineas.append(
            "{} {:.6f} {:.6f} {:.6f} {:.6f}".format(indice, cx, cy, bw, bh)
        )

    if not lineas:
        # Respaldo: la figura ocupa casi toda la foto.
        lineas.append("{} 0.500000 0.500000 0.980000 0.980000".format(indice))
    return "\n".join(lineas)


def _reparto_validacion(grupos, val_total):
    """Reparte las fotos de validación entre las clases, proporcionalmente."""
    total = sum(len(lista) for lista in grupos.values())
    if total == 0:
        return {clave: 0 for clave in grupos}

    val_total = max(0, min(val_total, total))
    asignado = {
        clave: int(round(len(lista) * val_total / total))
        for clave, lista in grupos.items()
    }

    diferencia = val_total - sum(asignado.values())
    claves = sorted(grupos, key=lambda clave: len(grupos[clave]), reverse=True)
    while diferencia != 0:
        cambio = False
        for clave in claves:
            if diferencia == 0:
                break
            if diferencia > 0 and asignado[clave] < len(grupos[clave]):
                asignado[clave] += 1
                diferencia -= 1
                cambio = True
            elif diferencia < 0 and asignado[clave] > 0:
                asignado[clave] -= 1
                diferencia += 1
                cambio = True
        if not cambio:
            break
    return asignado


def preparar_dataset(carpeta_capturas, destino, min_val=None):
    """Convierte una carpeta de capturas en un dataset YOLO train/val."""
    carpeta = Path(carpeta_capturas)
    if not carpeta.exists() or not carpeta.is_dir():
        raise ValueError("La carpeta del dataset no existe: {}".format(carpeta))

    grupos = {"H": [], "S": [], "sin": []}
    desconocidas = []
    for archivo in sorted(carpeta.iterdir()):
        if archivo.suffix.lower() not in EXTENSIONES_IMAGEN:
            continue
        clase = clase_de_archivo(archivo.name)
        if clase is None:
            desconocidas.append(archivo.name)
            continue
        grupos[clase].append(archivo)

    total = sum(len(lista) for lista in grupos.values())
    if total == 0:
        raise ValueError(
            "No encontré fotos con nombres H_, S_ o sin_figura_ en {}. "
            "Usa la pestaña Captura de figuras.".format(carpeta)
        )

    min_val = config.MIN_IMAGENES_VAL if min_val is None else min_val
    if total >= 2 * min_val:
        val_total = max(min_val, int(round(total * 0.2)))
    else:
        val_total = max(1, int(round(total * 0.2)))

    # Dejar al menos una foto de entrenamiento por clase cuando sea posible.
    clases_con_dos = sum(1 for lista in grupos.values() if len(lista) >= 2)
    val_total = min(val_total, max(1, total - max(1, clases_con_dos)))
    reparto = _reparto_validacion(grupos, val_total)

    generador = random.Random(20261112)
    train = []
    val = []
    for clase, lista in grupos.items():
        copia = list(lista)
        generador.shuffle(copia)
        cantidad_val = reparto.get(clase, 0)
        val.extend((clase, ruta) for ruta in copia[:cantidad_val])
        train.extend((clase, ruta) for ruta in copia[cantidad_val:])

    destino = Path(destino)
    for split in ("train", "val"):
        (destino / "images" / split).mkdir(parents=True, exist_ok=True)
        (destino / "labels" / split).mkdir(parents=True, exist_ok=True)

    for split, lista in (("train", train), ("val", val)):
        for clase, origen in lista:
            shutil.copy2(origen, destino / "images" / split / origen.name)
            etiqueta = _etiqueta_para_imagen(origen, clase)
            (destino / "labels" / split / (origen.stem + ".txt")).write_text(
                etiqueta, encoding="utf-8"
            )

    yaml_path = destino / "dataset.yaml"
    yaml_path.write_text(
        "path: {}\n".format(destino.as_posix())
        + "train: images/train\n"
        + "val: images/val\n"
        + "names:\n  0: H\n  1: S\n",
        encoding="utf-8",
    )

    instancias = _contar_instancias_etiquetas(destino / "labels" / "val")
    confiable, faltantes = analizar_validacion(len(val), instancias, min_val)
    return {
        "yaml": yaml_path,
        "destino": destino,
        "train": len(train),
        "val": len(val),
        "instancias": instancias,
        "confiable": confiable,
        "faltantes": faltantes,
        "generado": True,
        "ignoradas": desconocidas,
    }


def analizar_yaml(yaml_path):
    """Analiza un dataset YOLO que ya existe (sin copiar archivos)."""
    from modelo import entrenar as entrenador

    yaml_path = Path(yaml_path)
    val = entrenador.contar_imagenes("val", str(yaml_path))
    instancias = entrenador.contar_instancias_por_clase("val", str(yaml_path))
    confiable, faltantes = analizar_validacion(val, instancias)
    return {
        "yaml": yaml_path,
        "destino": yaml_path.parent,
        "train": entrenador.contar_imagenes("train", str(yaml_path)),
        "val": val,
        "instancias": instancias,
        "confiable": confiable,
        "faltantes": faltantes,
        "generado": False,
        "ignoradas": [],
    }


def preparar_para_entrenamiento(carpeta, base_salida=None):
    """Devuelve el YAML y el estado de validación para la carpeta elegida."""
    carpeta = Path(carpeta)

    if carpeta.is_file() and carpeta.suffix.lower() in (".yaml", ".yml"):
        return analizar_yaml(carpeta)

    if carpeta.is_dir():
        for nombre in ("data.yaml", "dataset.yaml", "rescate.yaml"):
            candidato = carpeta / nombre
            if candidato.exists():
                return analizar_yaml(candidato)

    base_salida = Path(base_salida) if base_salida is not None else ENTRENAMIENTO_DIR
    base_salida.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = base_salida / "dataset_{}".format(sello)
    sufijo = 1
    while destino.exists():
        destino = base_salida / "dataset_{}_{}".format(sello, sufijo)
        sufijo += 1
    return preparar_dataset(carpeta, destino)


def construir_comando_entrenamiento(yaml_path, minutos, epocas, dispositivo, proyecto, nombre=None):
    """Arma el comando de modelo/entrenar.py para ejecutarlo en segundo plano."""
    nombre = nombre or "gui_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    return [
        sys.executable,
        "-m",
        "modelo.entrenar",
        "--data",
        str(yaml_path),
        "--epocas",
        str(int(epocas)),
        "--tiempo",
        str(int(minutos)),
        "--dispositivo",
        str(dispositivo),
        "--proyecto",
        str(Path(proyecto) / "runs"),
        "--nombre",
        str(nombre),
        "--sin-guardar",
    ]


def limpiar_linea(linea):
    """Quita colores y retornos de carro del texto de Ultralytics."""
    texto = ANSI_RE.sub("", linea or "")
    texto = texto.replace("\r", "").replace("\b", "")
    texto = texto.replace("[K", "")
    return texto.strip()


def parsear_resultado(texto):
    """Lee del texto de entrenar.py el mAP, la confiabilidad y el best.pt."""
    texto = texto or ""
    resultado = {
        "confiable": False,
        "no_confiable": False,
        "map50": None,
        "map50_95": None,
        "best": None,
    }

    if "Validación suficiente" in texto and "mAP50: NO CONFIABLE" not in texto:
        resultado["confiable"] = True
    if "mAP50: NO CONFIABLE" in texto or "Validación INSUFICIENTE" in texto:
        resultado["no_confiable"] = True

    coincidencia = re.search(r"mAP50:\s*(NO CONFIABLE|[0-9]*\.?[0-9]+)", texto)
    if coincidencia and coincidencia.group(1) != "NO CONFIABLE":
        try:
            resultado["map50"] = float(coincidencia.group(1))
        except ValueError:
            pass

    coincidencia = re.search(r"mAP50-95:\s*(NO CONFIABLE|[0-9]*\.?[0-9]+)", texto)
    if coincidencia and coincidencia.group(1) != "NO CONFIABLE":
        try:
            resultado["map50_95"] = float(coincidencia.group(1))
        except ValueError:
            pass

    coincidencia = re.search(r"Pesos(?: guardados en| de la corrida en):\s*(.+)", texto)
    if coincidencia:
        ruta = coincidencia.group(1)
        ruta = ruta.split("(no se copiaron)")[0].strip()
        if ruta:
            resultado["best"] = Path(ruta)

    return resultado


def copiar_modelo(best, destino=None):
    """Copia el mejor modelo a modelo/pesos/rescate.pt (sin tocar config.py)."""
    origen = Path(best)
    if not origen.exists():
        raise FileNotFoundError("No existe el modelo entrenado: {}".format(origen))
    destino = Path(destino) if destino is not None else config.PESOS_ENTRENADO
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    return destino


def abrir_carpeta(ruta):
    """Abre una carpeta en el explorador de archivos del sistema."""
    ruta = Path(ruta)
    ruta.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(ruta))
    else:  # pragma: no cover - el evento se usa en Windows
        subprocess.Popen(["xdg-open", str(ruta)])


# ---------------------------------------------------------------------------
# Interfaz gráfica
# ---------------------------------------------------------------------------
class Aplicacion:
    def __init__(self, root):
        self.root = root
        self.root.title("Código Rescate - Laptop")
        self.root.geometry("1000x780")
        self.root.minsize(900, 700)

        self.estado = None
        self.pipeline_corriendo = False
        self.entrenando = False
        self._cerrando = False
        self._gpu_disponible = False
        self._proceso_entrenamiento = None
        self._avisos_vistos = 0
        self._salida_entrenamiento = []

        self._sesion_captura = None
        self._cam_captura = None
        self._cam_abriendo = False
        self._ultimo_intento_camara = 0.0
        self._ultimo_frame = None
        self._imagen_tk = None
        self._tab_captura_activa = False

        self._ultimo_best = None
        self._ultimo_confiable = None
        self._ultimo_faltantes = []
        self._datos_entrenamiento = None

        self._construir_barra_superior()
        self._construir_pestanas()
        self._construir_pie()
        self._actualizar_botones()

        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.root.after(500, self._actualizar)
        self.root.after(80, self._bucle_captura)
        self._detectar_gpu_en_hilo()

    # ------------------------------------------------------------------
    # Construcción de la ventana
    # ------------------------------------------------------------------
    def _construir_barra_superior(self):
        barra = ttk.Frame(self.root, padding=(12, 8, 12, 2))
        barra.pack(fill="x")

        self.lbl_estado = ttk.Label(
            barra,
            text="Estado de la laptop: detenida",
            font=("Segoe UI", 12, "bold"),
            foreground=COLOR_NEUTRO,
        )
        self.lbl_estado.pack(side="left")

        ttk.Label(
            barra,
            text=(
                "Solo controla la laptop. Nunca envía órdenes de movimiento, "
                "arranque ni parada al robot."
            ),
            foreground=COLOR_NEUTRO,
        ).pack(side="left", padx=16)

    def _construir_pestanas(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=6)

        self.tab_operacion = ttk.Frame(self.notebook, padding=8)
        self.tab_captura = ttk.Frame(self.notebook, padding=8)
        self.tab_entrenamiento = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.tab_operacion, text="1. Operación")
        self.notebook.add(self.tab_captura, text="2. Captura de figuras")
        self.notebook.add(self.tab_entrenamiento, text="3. Entrenamiento")

        self.notebook.bind("<<NotebookTabChanged>>", self._al_cambiar_pestana)

        self._construir_tab_operacion()
        self._construir_tab_captura()
        self._construir_tab_entrenamiento()

    def _construir_pie(self):
        pie = ttk.Frame(self.root, padding=(12, 2, 12, 8))
        pie.pack(fill="x")
        ttk.Button(
            pie,
            text="Abrir carpeta de registros (logs/)",
            command=lambda: self._abrir_carpeta(LOGS_DIR, "registros"),
        ).pack(side="left")
        ttk.Label(
            pie,
            text="Allí quedan las inferencias y el registro de cada entrenamiento.",
            foreground=COLOR_NEUTRO,
        ).pack(side="left", padx=8)

    def _campo_con_ayuda(self, padre, fila, etiqueta, ayuda, valor="", ancho=38):
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=0, sticky="w", padx=6, pady=(8, 0)
        )
        entrada = ttk.Entry(padre, width=ancho)
        if valor:
            entrada.insert(0, valor)
        entrada.grid(row=fila, column=1, sticky="we", padx=6, pady=(8, 0))
        ttk.Label(
            padre,
            text=ayuda,
            foreground=COLOR_NEUTRO,
            wraplength=560,
            justify="left",
        ).grid(row=fila + 1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 2))
        padre.columnconfigure(1, weight=1)
        return entrada

    def _construir_tab_operacion(self):
        self.tab_operacion.columnconfigure(0, weight=1)
        self.tab_operacion.columnconfigure(1, weight=1)
        self.tab_operacion.rowconfigure(3, weight=1)

        # Identidad del intento
        frm_id = ttk.LabelFrame(self.tab_operacion, text="Identidad del intento")
        frm_id.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self.entry_equipo = self._campo_con_ayuda(
            frm_id,
            0,
            "Equipo:",
            "Código registrado del equipo. Lo da la organización.",
        )
        self.entry_intento = self._campo_con_ayuda(
            frm_id,
            2,
            "Intento:",
            "Número del intento que te da el juez. Cámbialo en cada ronda.",
        )
        self.entry_fuente = self._campo_con_ayuda(
            frm_id,
            4,
            "Fuente de video:",
            "Dirección del celular (http://IP:8080/video) o 0 para la cámara de la laptop.",
            valor="0",
        )

        # Botones
        frm_btn = ttk.Frame(self.tab_operacion)
        frm_btn.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        self.btn_preparar = ttk.Button(frm_btn, text="Preparar", command=self.preparar)
        self.btn_preparar.pack(side="left", padx=(4, 8), pady=4)
        self.btn_detener = ttk.Button(
            frm_btn, text="Detener", command=self.detener, state="disabled"
        )
        self.btn_detener.pack(side="left", padx=4, pady=4)

        ttk.Label(
            self.tab_operacion,
            text=(
                "Preparar publica la configuración del robot y abre la cámara, la detección "
                "y el enlace de la laptop. No arranca el robot. Detener cierra esos procesos "
                "de la laptop y tampoco envía nada al robot."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=470,
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=10, pady=4)

        # Indicadores
        frm_ind = ttk.LabelFrame(self.tab_operacion, text="Indicadores en vivo")
        frm_ind.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=4, pady=4)
        frm_ind.columnconfigure(1, weight=1)

        self.ind_camara = self._fila_indicador(
            frm_ind, 0, "Cámara",
            "La laptop está recibiendo video de la fuente indicada.",
        )
        self.ind_broker = self._fila_indicador(
            frm_ind, 1, "Broker local",
            "Programa que reparte mensajes entre la laptop y el robot en la red local.",
        )
        self.ind_servidor = self._fila_indicador(
            frm_ind, 2, "Enlace al servidor",
            "Canal por el que se reenvían los reportes del robot al servidor oficial.",
        )
        self.ind_robot = self._fila_indicador(
            frm_ind, 3, "Robot",
            "Último reporte recibido del robot. La laptop no le ordena moverse.",
        )
        self.ind_vision = self._fila_indicador(
            frm_ind, 4, "Visión",
            "Detecciones por segundo que la laptop está enviando al robot.",
        )

        if not _servidor_configurado():
            ttk.Label(
                frm_ind,
                text=(
                    "AVISO: la dirección del servidor (endpoint) no está configurada. "
                    "No se enviarán reportes y el robot no recibirá confirmación. "
                    "Pide los datos oficiales a la organización."
                ),
                foreground=COLOR_ERROR,
                wraplength=440,
                justify="left",
            ).grid(row=10, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 8))
        else:
            ttk.Label(
                frm_ind,
                text="La dirección del servidor está configurada.",
                foreground=COLOR_OK,
            ).grid(row=10, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 8))

        # Reporte y avisos
        frm_rep = ttk.LabelFrame(
            self.tab_operacion, text="Último reporte del robot (solo lectura)"
        )
        frm_rep.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        self.txt_reporte = tk.Text(frm_rep, height=7, state="disabled", wrap="word")
        self.txt_reporte.pack(fill="both", expand=True, padx=5, pady=5)

        frm_av = ttk.LabelFrame(self.tab_operacion, text="Avisos de la laptop")
        frm_av.grid(row=3, column=1, sticky="nsew", padx=4, pady=4)
        self.txt_avisos = tk.Text(frm_av, height=7, state="disabled", wrap="word")
        self.txt_avisos.pack(fill="both", expand=True, padx=5, pady=5)

    def _fila_indicador(self, padre, indice, nombre, explicacion):
        punto = ttk.Label(
            padre, text="●", foreground=COLOR_NEUTRO, font=("Segoe UI", 14)
        )
        punto.grid(row=indice * 2, column=0, sticky="nw", padx=(6, 2))
        texto = ttk.Label(
            padre, text="{}: -".format(nombre), font=("Segoe UI", 10, "bold")
        )
        texto.grid(row=indice * 2, column=1, sticky="w")
        ttk.Label(
            padre,
            text=explicacion,
            foreground=COLOR_NEUTRO,
            wraplength=430,
            justify="left",
        ).grid(row=indice * 2 + 1, column=1, sticky="w", pady=(0, 6))
        return punto, texto

    def _construir_tab_captura(self):
        self.tab_captura.columnconfigure(0, weight=1)
        self.tab_captura.rowconfigure(1, weight=1)

        frm_sesion = ttk.Frame(self.tab_captura)
        frm_sesion.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.lbl_sesion = ttk.Label(
            frm_sesion,
            text="Sesión actual: se crea al entrar a esta pestaña.",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_sesion.pack(side="left")
        ttk.Button(
            frm_sesion,
            text="Abrir carpeta de esta sesión",
            command=self._abrir_sesion,
        ).pack(side="right")
        ttk.Button(
            frm_sesion,
            text="Empezar una sesión nueva",
            command=self._nueva_sesion,
        ).pack(side="right", padx=6)

        frm_video = ttk.LabelFrame(self.tab_captura, text="Vista de la cámara")
        frm_video.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.lbl_video = tk.Label(
            frm_video,
            text="La cámara se abre al entrar a esta pestaña.",
            bg="black",
            fg="white",
            width=80,
            height=22,
        )
        self.lbl_video.pack(fill="both", expand=True, padx=5, pady=5)

        ttk.Label(
            self.tab_captura,
            text=(
                "Toma varias fotos de cada figura, desde distintos ángulos y distancias, "
                "para que el modelo aprenda."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=900,
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(4, 6))

        frm_botones = ttk.Frame(self.tab_captura)
        frm_botones.grid(row=3, column=0, sticky="ew", padx=4, pady=4)
        self.btn_captura_h = tk.Button(
            frm_botones,
            text="Guardar como H (herida)",
            command=lambda: self._guardar_captura("H"),
            font=("Segoe UI", 12, "bold"),
            height=2,
            width=24,
            bg="#f4b183",
            activebackground="#f8cbad",
        )
        self.btn_captura_h.pack(side="left", padx=6)
        self.btn_captura_s = tk.Button(
            frm_botones,
            text="Guardar como S (suministros)",
            command=lambda: self._guardar_captura("S"),
            font=("Segoe UI", 12, "bold"),
            height=2,
            width=24,
            bg="#c5a3d9",
            activebackground="#d9c2e8",
        )
        self.btn_captura_s.pack(side="left", padx=6)
        self.btn_captura_sin = tk.Button(
            frm_botones,
            text="Guardar sin figura",
            command=lambda: self._guardar_captura("sin"),
            font=("Segoe UI", 12, "bold"),
            height=2,
            width=20,
            bg="#d9d9d9",
            activebackground="#eeeeee",
        )
        self.btn_captura_sin.pack(side="left", padx=6)

        frm_conteo = ttk.LabelFrame(self.tab_captura, text="Conteo de la sesión")
        frm_conteo.grid(row=4, column=0, sticky="ew", padx=4, pady=6)
        self.lbl_conteo_h = ttk.Label(
            frm_conteo, text="H (herida): 0", font=("Segoe UI", 12, "bold")
        )
        self.lbl_conteo_h.pack(side="left", padx=12, pady=6)
        self.lbl_conteo_s = ttk.Label(
            frm_conteo, text="S (suministros): 0", font=("Segoe UI", 12, "bold")
        )
        self.lbl_conteo_s.pack(side="left", padx=12, pady=6)
        self.lbl_conteo_sin = ttk.Label(
            frm_conteo, text="Sin figura: 0", font=("Segoe UI", 12, "bold")
        )
        self.lbl_conteo_sin.pack(side="left", padx=12, pady=6)

        self.lbl_recomendacion = ttk.Label(
            self.tab_captura,
            text=(
                "Recomendado antes de entrenar: 30 imágenes de H y 30 de S. "
                "Llevas 0 de H y 0 de S."
            ),
            foreground=COLOR_AVISO,
            wraplength=900,
            justify="left",
        )
        self.lbl_recomendacion.grid(row=5, column=0, sticky="w", padx=8, pady=(0, 4))

    def _construir_tab_entrenamiento(self):
        self.tab_entrenamiento.columnconfigure(1, weight=1)

        ttk.Label(
            self.tab_entrenamiento,
            text=(
                "Entrena el modelo con las fotos guardadas. El entrenamiento usa la laptop "
                "y puede tardar varios minutos."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=900,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        # Dataset
        ttk.Label(self.tab_entrenamiento, text="Carpeta del dataset:").grid(
            row=1, column=0, sticky="w", padx=6, pady=(8, 0)
        )
        frm_dataset = ttk.Frame(self.tab_entrenamiento)
        frm_dataset.grid(row=1, column=1, sticky="we", padx=6, pady=(8, 0))
        frm_dataset.columnconfigure(0, weight=1)
        self.var_dataset = tk.StringVar(value="")
        ultima = sesion_mas_reciente()
        if ultima is not None:
            self.var_dataset.set(str(ultima))
        self.entry_dataset = ttk.Entry(frm_dataset, textvariable=self.var_dataset)
        self.entry_dataset.grid(row=0, column=0, sticky="we")
        ttk.Button(
            frm_dataset, text="Elegir otra...", command=self._elegir_carpeta
        ).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(
            self.tab_entrenamiento,
            text=(
                "Carpeta con las fotos de una sesión de captura. Por defecto se usa la "
                "última sesión de datos/capturas/."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=860,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6)

        # Parámetros
        ttk.Label(self.tab_entrenamiento, text="Tiempo máximo (minutos):").grid(
            row=3, column=0, sticky="w", padx=6, pady=(10, 0)
        )
        self.var_tiempo = tk.StringVar(value="20")
        ttk.Spinbox(
            self.tab_entrenamiento,
            from_=1,
            to=180,
            textvariable=self.var_tiempo,
            width=8,
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(10, 0))
        ttk.Label(
            self.tab_entrenamiento,
            text="Si se acaba el tiempo, el entrenamiento se detiene y guarda lo que tenga.",
            foreground=COLOR_NEUTRO,
            wraplength=860,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=6)

        ttk.Label(self.tab_entrenamiento, text="Épocas (máximo):").grid(
            row=5, column=0, sticky="w", padx=6, pady=(6, 0)
        )
        self.var_epocas = tk.StringVar(value=str(config.EPOCAS))
        ttk.Spinbox(
            self.tab_entrenamiento,
            from_=1,
            to=500,
            textvariable=self.var_epocas,
            width=8,
        ).grid(row=5, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(
            self.tab_entrenamiento,
            text=(
                "Cada época es una pasada por todas las fotos. El tiempo máximo manda: "
                "si se cumple antes, el entrenamiento termina."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=860,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=6)

        ttk.Label(self.tab_entrenamiento, text="Dispositivo:").grid(
            row=7, column=0, sticky="w", padx=6, pady=(6, 0)
        )
        self.var_dispositivo = tk.StringVar(value="CPU")
        self.cmb_dispositivo = ttk.Combobox(
            self.tab_entrenamiento,
            textvariable=self.var_dispositivo,
            values=("CPU",),
            state="readonly",
            width=10,
        )
        self.cmb_dispositivo.grid(row=7, column=1, sticky="w", padx=6, pady=(6, 0))
        self.lbl_gpu = ttk.Label(
            self.tab_entrenamiento,
            text="Detectando si hay GPU...",
            foreground=COLOR_NEUTRO,
            wraplength=860,
            justify="left",
        )
        self.lbl_gpu.grid(row=8, column=0, columnspan=2, sticky="w", padx=6)

        # Entrenar
        frm_entrenar = ttk.Frame(self.tab_entrenamiento)
        frm_entrenar.grid(row=9, column=0, columnspan=2, sticky="ew", padx=4, pady=10)
        self.btn_entrenar = tk.Button(
            frm_entrenar,
            text="Entrenar",
            command=self.entrenar,
            font=("Segoe UI", 12, "bold"),
            height=2,
            width=18,
            bg="#b6d7a8",
            activebackground="#cfe2c3",
        )
        self.btn_entrenar.pack(side="left", padx=6)
        self.lbl_motivo_entrenar = ttk.Label(
            frm_entrenar,
            text="",
            foreground=COLOR_NEUTRO,
            wraplength=620,
            justify="left",
        )
        self.lbl_motivo_entrenar.pack(side="left", padx=10)

        # Progreso
        frm_prog = ttk.LabelFrame(
            self.tab_entrenamiento, text="Progreso del entrenamiento"
        )
        frm_prog.grid(row=10, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self.progreso = ttk.Progressbar(frm_prog, mode="indeterminate", length=700)
        self.progreso.pack(fill="x", padx=8, pady=(6, 2))
        self.txt_progreso = tk.Text(frm_prog, height=5, state="disabled", wrap="word")
        self.txt_progreso.pack(fill="x", padx=8, pady=(2, 6))

        # Resultado
        frm_res = ttk.LabelFrame(
            self.tab_entrenamiento, text="Resultado del entrenamiento"
        )
        frm_res.grid(row=11, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self.lbl_resultado = ttk.Label(
            frm_res,
            text="Todavía no hay un entrenamiento.",
            font=("Segoe UI", 11, "bold"),
            foreground=COLOR_NEUTRO,
            wraplength=880,
            justify="left",
        )
        self.lbl_resultado.pack(anchor="w", padx=8, pady=(6, 2))
        self.lbl_metricas = ttk.Label(
            frm_res,
            text="",
            foreground=COLOR_NEUTRO,
            wraplength=880,
            justify="left",
        )
        self.lbl_metricas.pack(anchor="w", padx=8, pady=2)
        ttk.Label(
            frm_res,
            text=(
                "mAP (precisión promedio): qué tan bien encuentra y ubica las figuras. "
                "1.00 es perfecto; 0.70 es el mínimo recomendado. "
                "Solo se muestra cuando hay suficientes imágenes de validación."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=880,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 4))

        self.btn_usar_modelo = ttk.Button(
            frm_res,
            text="Usar este modelo en la competencia",
            command=self._usar_modelo,
            state="disabled",
        )
        self.btn_usar_modelo.pack(anchor="w", padx=8, pady=(2, 2))
        ttk.Label(
            frm_res,
            text=(
                "Copia el mejor resultado a modelo/pesos/rescate.pt. "
                "No cambia config.py."
            ),
            foreground=COLOR_NEUTRO,
            wraplength=880,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 6))

    # ------------------------------------------------------------------
    # Utilidades de interfaz e hilos
    # ------------------------------------------------------------------
    def _en_ui(self, funcion, *args):
        if self._cerrando:
            return
        try:
            self.root.after(0, funcion, *args)
        except Exception:
            pass

    def _log(self, mensaje):
        if not hasattr(self, "txt_avisos") or self.txt_avisos is None:
            return
        try:
            self.txt_avisos.config(state="normal")
            self.txt_avisos.insert(
                "end", "{} {}\n".format(time.strftime("%H:%M:%S"), mensaje)
            )
            self.txt_avisos.see("end")
            self.txt_avisos.config(state="disabled")
        except Exception:
            pass

    def _abrir_carpeta(self, ruta, nombre):
        try:
            abrir_carpeta(ruta)
        except Exception as error:
            messagebox.showerror(
                "No se pudo abrir la carpeta",
                "No se pudo abrir la carpeta de {}:\n{}".format(nombre, error),
            )

    def _abrir_logs(self):
        self._abrir_carpeta(LOGS_DIR, "registros")

    def _abrir_sesion(self):
        if self._sesion_captura is None:
            messagebox.showinfo(
                "Sin sesión",
                "Todavía no hay una sesión de captura. Entra a la pestaña "
                "Captura de figuras.",
            )
            return
        self._abrir_carpeta(self._sesion_captura, "capturas")

    # ------------------------------------------------------------------
    # Pestaña 1: Operación
    # ------------------------------------------------------------------
    def preparar(self):
        if self.entrenando:
            messagebox.showwarning(
                "Entrenamiento en marcha",
                "La laptop está entrenando. Espera a que termine antes de preparar "
                "la operación.",
            )
            return
        if self.pipeline_corriendo:
            self._log("La operación ya está en marcha.")
            return

        equipo = self.entry_equipo.get().strip()
        intento = self.entry_intento.get().strip()
        fuente = self.entry_fuente.get().strip() or "0"
        if not equipo or not intento:
            messagebox.showwarning(
                "Faltan datos", "Equipo e intento son obligatorios."
            )
            self._log("Aviso: equipo e intento son obligatorios.")
            return

        self.btn_preparar.config(state="disabled")
        self._log("Publicando la configuración del robot y abriendo la laptop...")

        def tarea():
            ok, mensaje = publicar_config(equipo, intento)
            self._en_ui(self._log, ("OK: " if ok else "ERROR: ") + mensaje)
            if not ok:
                self._en_ui(self._preparar_fallo, mensaje)
                return

            try:
                estado = main.iniciar_pipeline(
                    equipo=equipo,
                    intento=intento,
                    mostrar=False,
                    fuente_video=fuente,
                )
            except Exception as error:
                self._en_ui(self._preparar_fallo, str(error))
                return

            self.estado = estado
            self.pipeline_corriendo = True
            self._avisos_vistos = 0
            self._en_ui(self._on_pipeline_iniciado)

        threading.Thread(target=tarea, daemon=True).start()

    def _preparar_fallo(self, mensaje):
        self.btn_preparar.config(state="normal")
        self._log("No se pudo preparar la operación: {}".format(mensaje))
        messagebox.showerror(
            "No se pudo preparar la operación",
            "{}\n\nRevisa el modelo entrenado y la fuente de video.".format(mensaje),
        )
        self._actualizar_botones()

    def _on_pipeline_iniciado(self):
        self.btn_detener.config(state="normal")
        self.txt_reporte.config(state="normal")
        self.txt_reporte.delete("1.0", "end")
        self.txt_reporte.config(state="disabled")
        self._log("Operación iniciada. La laptop está lista.")
        self._actualizar_botones()

    def detener(self):
        self._log("Deteniendo los procesos de la laptop...")
        self.btn_detener.config(state="disabled")

        def tarea():
            try:
                main.detener_pipeline(self.estado)
            except Exception as error:
                self._en_ui(self._log, "Aviso al detener: {}".format(error))
            self._en_ui(self._on_pipeline_detenido)

        threading.Thread(target=tarea, daemon=True).start()

    def _on_pipeline_detenido(self):
        self.pipeline_corriendo = False
        self.btn_detener.config(state="disabled")
        self.btn_preparar.config(state="normal")
        self._log("Operación detenida. No se envió nada al robot.")
        self._actualizar_botones()

    def _actualizar(self):
        if self._cerrando:
            return

        # Si el pipeline se cayó solo, reflejarlo en la interfaz.
        if self.pipeline_corriendo and self.estado is not None:
            hilo = getattr(self.estado, "_hilo", None)
            if hilo is not None and not hilo.is_alive():
                self._log("La operación se detuvo sola. Revisa los avisos.")
                self._on_pipeline_detenido()

        self._actualizar_estado_laptop()
        self._actualizar_indicadores()
        self._actualizar_reporte()
        self._actualizar_avisos()
        self._actualizar_botones()
        self.root.after(500, self._actualizar)

    def _actualizar_estado_laptop(self):
        if self.entrenando:
            texto = "entrenando"
            color = COLOR_AVISO
        elif self.pipeline_corriendo:
            texto = "en operación"
            color = COLOR_OK
        else:
            texto = "detenida"
            color = COLOR_NEUTRO
        self.lbl_estado.config(
            text="Estado de la laptop: {}".format(texto), foreground=color
        )

    def _poner_indicador(self, indicador, valor, color):
        punto, texto = indicador
        punto.config(foreground=COLORES_INDICADOR.get(color, COLOR_NEUTRO))
        nombre = texto.cget("text").split(":", 1)[0]
        texto.config(text="{}: {}".format(nombre, valor))

    def _actualizar_indicadores(self):
        if not self.pipeline_corriendo or self.estado is None:
            self._poner_indicador(self.ind_camara, "sin iniciar", "amarillo")
            self._poner_indicador(self.ind_broker, "sin iniciar", "amarillo")
            if not _servidor_configurado():
                self._poner_indicador(
                    self.ind_servidor, "dirección no configurada", "rojo"
                )
            else:
                self._poner_indicador(self.ind_servidor, "sin iniciar", "amarillo")
            self._poner_indicador(self.ind_robot, "sin reporte", "amarillo")
            self._poner_indicador(self.ind_vision, "0 por segundo", "amarillo")
            return

        est = self.estado
        self._poner_indicador(
            self.ind_camara,
            "conectada" if est.camera_ok else "sin señal",
            "verde" if est.camera_ok else "rojo",
        )
        self._poner_indicador(
            self.ind_broker,
            "conectado" if est.broker_ok else "no conectado",
            "verde" if est.broker_ok else "rojo",
        )

        if not _servidor_configurado():
            self._poner_indicador(
                self.ind_servidor, "dirección no configurada", "rojo"
            )
        elif est.server_link == "conectado":
            self._poner_indicador(self.ind_servidor, "conectado", "verde")
        elif est.server_link in ("sin conexión", "TODO"):
            self._poner_indicador(self.ind_servidor, est.server_link, "rojo")
        else:
            self._poner_indicador(self.ind_servidor, "sin iniciar", "amarillo")

        if est.last_seq is None:
            self._poner_indicador(self.ind_robot, "sin reporte", "amarillo")
        else:
            edad = (
                time.time() - est.last_report_time
                if est.last_report_time is not None
                else 999.0
            )
            if edad <= 5.0:
                self._poner_indicador(
                    self.ind_robot, "reporte reciente", "verde"
                )
            else:
                hora = (
                    time.strftime("%H:%M:%S", time.localtime(est.last_report_time))
                    if est.last_report_time
                    else "-"
                )
                self._poner_indicador(
                    self.ind_robot, "último reporte a las {}".format(hora), "amarillo"
                )

        tasa = est.vision_rate()
        self._poner_indicador(
            self.ind_vision,
            "{} por segundo".format(tasa),
            "verde" if tasa > 0 else "amarillo",
        )

    def _actualizar_reporte(self):
        est = self.estado
        if est is None or est.last_report is None:
            return
        try:
            texto = json.dumps(est.last_report, ensure_ascii=False, indent=2)
        except Exception:
            texto = str(est.last_report)
        if self.txt_reporte.get("1.0", "end-1c") == texto:
            return
        self.txt_reporte.config(state="normal")
        self.txt_reporte.delete("1.0", "end")
        self.txt_reporte.insert("end", texto)
        self.txt_reporte.config(state="disabled")

    def _actualizar_avisos(self):
        est = self.estado
        if est is None:
            return
        avisos = est.snapshot_avisos()
        if len(avisos) > self._avisos_vistos:
            for _, nivel, mensaje in avisos[self._avisos_vistos:]:
                self._log("[{}] {}".format(nivel, mensaje))
            self._avisos_vistos = len(avisos)

    def _actualizar_botones(self):
        if not hasattr(self, "btn_entrenar"):
            return
        if self.pipeline_corriendo:
            self.btn_entrenar.config(state="disabled")
            self.lbl_motivo_entrenar.config(
                text=(
                    "No puedes entrenar mientras la laptop está en operación. "
                    "Pulsa Detener en la pestaña Operación."
                ),
                foreground=COLOR_ERROR,
            )
        elif self.entrenando:
            self.btn_entrenar.config(state="disabled")
            self.lbl_motivo_entrenar.config(
                text="Entrenamiento en marcha. Espera a que termine.",
                foreground=COLOR_AVISO,
            )
        else:
            self.btn_entrenar.config(state="normal")
            self.lbl_motivo_entrenar.config(
                text="Disponible cuando la laptop no esté en operación.",
                foreground=COLOR_NEUTRO,
            )

    # ------------------------------------------------------------------
    # Pestaña 2: Captura de figuras
    # ------------------------------------------------------------------
    def _al_cambiar_pestana(self, _evento=None):
        try:
            indice = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if indice == 1:
            self._tab_captura_activa = True
            self._entrar_captura()
        else:
            if self._tab_captura_activa:
                self._tab_captura_activa = False
                self._salir_captura()

    def _entrar_captura(self):
        if self._sesion_captura is None:
            self._nueva_sesion()
        self._abrir_camara_captura()

    def _nueva_sesion(self):
        """Crea una sesión con la fecha y hora actual y la pone como activa."""
        anterior = self._sesion_captura
        previa_mas_reciente = sesion_mas_reciente()
        self._sesion_captura = crear_sesion()
        self.lbl_sesion.config(
            text="Sesión actual: {}".format(self._sesion_captura)
        )
        ruta_previa = str(anterior) if anterior is not None else ""
        ruta_dataset = self.var_dataset.get().strip() if hasattr(self, "var_dataset") else ""
        if not ruta_dataset or ruta_dataset == ruta_previa:
            self.var_dataset.set(str(self._sesion_captura))
        elif previa_mas_reciente is not None and ruta_dataset == str(previa_mas_reciente):
            self.var_dataset.set(str(self._sesion_captura))
        self._log("Sesión de captura creada: {}".format(self._sesion_captura))
        self._actualizar_conteo()

    def _salir_captura(self):
        cam = self._cam_captura
        self._cam_captura = None
        self._ultimo_frame = None
        self._imagen_tk = None
        if cam is not None:
            threading.Thread(target=cam.cerrar, daemon=True).start()
        try:
            self.lbl_video.config(image="", text="La cámara se abre al entrar a esta pestaña.")
        except Exception:
            pass

    def _abrir_camara_captura(self):
        if self._cam_captura is not None or self._cam_abriendo:
            return
        ahora = time.monotonic()
        if ahora - self._ultimo_intento_camara < 2.0:
            return
        self._ultimo_intento_camara = ahora
        self._cam_abriendo = True

        fuente_texto = self.entry_fuente.get().strip() or "0"
        fuente = int(fuente_texto) if fuente_texto.isdigit() else fuente_texto

        def tarea():
            try:
                from stream.recibir import Camara

                camara = Camara(fuente=fuente)
            except Exception as error:
                self._en_ui(self._camara_fallo, str(error))
                return
            self._cam_captura = camara
            self._en_ui(self._camara_lista, fuente_texto)

        threading.Thread(target=tarea, daemon=True).start()

    def _camara_lista(self, fuente):
        self._cam_abriendo = False
        self._log("Cámara de captura abierta: {}".format(fuente))

    def _camara_fallo(self, mensaje):
        self._cam_abriendo = False
        self._log("No se pudo abrir la cámara de captura: {}".format(mensaje))
        try:
            self.lbl_video.config(
                image="", text="No se pudo abrir la cámara.\n{}".format(mensaje)
            )
        except Exception:
            pass

    def _bucle_captura(self):
        if self._cerrando:
            return
        if self._tab_captura_activa:
            if self._sesion_captura is None:
                self._entrar_captura()
            if self._cam_captura is not None:
                frame = self._cam_captura.leer()
                if frame is not None:
                    self._ultimo_frame = frame
                    self._mostrar_frame(frame)
            elif not self._cam_abriendo:
                self._abrir_camara_captura()
            self._actualizar_conteo()
        self.root.after(80, self._bucle_captura)

    def _mostrar_frame(self, frame):
        try:
            if PIL_OK:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                imagen = Image.fromarray(rgb)
                imagen.thumbnail((880, 480))
                self._imagen_tk = ImageTk.PhotoImage(imagen)
            else:  # pragma: no cover - Pillow está instalado en el proyecto
                ok, bufer = cv2.imencode(".png", frame)
                if not ok:
                    return
                datos = base64.b64encode(bufer.tobytes()).decode("ascii")
                self._imagen_tk = tk.PhotoImage(data=datos)
            self.lbl_video.config(image=self._imagen_tk, text="")
        except Exception as error:
            self._log("No se pudo mostrar la imagen de la cámara: {}".format(error))

    def _guardar_captura(self, clase):
        if self._sesion_captura is None:
            self._entrar_captura()
        if self._ultimo_frame is None:
            messagebox.showwarning(
                "Sin imagen",
                "La cámara todavía no muestra una imagen. Espera un momento e intenta de nuevo.",
            )
            return
        try:
            ruta = guardar_captura(self._sesion_captura, self._ultimo_frame, clase)
        except Exception as error:
            messagebox.showerror("No se pudo guardar la foto", str(error))
            self._log("No se pudo guardar la foto: {}".format(error))
            return
        self._log("Foto guardada: {}".format(ruta))
        self._actualizar_conteo()

    def _actualizar_conteo(self):
        if self._sesion_captura is None:
            return
        conteo = contar_capturas(self._sesion_captura)
        self.lbl_conteo_h.config(text="H (herida): {}".format(conteo["H"]))
        self.lbl_conteo_s.config(text="S (suministros): {}".format(conteo["S"]))
        self.lbl_conteo_sin.config(text="Sin figura: {}".format(conteo["sin"]))

        listo = (
            conteo["H"] >= RECOMENDADO_POR_CLASE
            and conteo["S"] >= RECOMENDADO_POR_CLASE
        )
        if listo:
            self.lbl_recomendacion.config(
                text=(
                    "Listo: tienes al menos {} imágenes de H y {} de S. "
                    "Puedes entrenar en la pestaña Entrenamiento."
                ).format(RECOMENDADO_POR_CLASE, RECOMENDADO_POR_CLASE),
                foreground=COLOR_OK,
            )
        else:
            self.lbl_recomendacion.config(
                text=(
                    "Recomendado antes de entrenar: {} imágenes de H y {} de S. "
                    "Llevas {} de H y {} de S."
                ).format(
                    RECOMENDADO_POR_CLASE,
                    RECOMENDADO_POR_CLASE,
                    conteo["H"],
                    conteo["S"],
                ),
                foreground=COLOR_AVISO,
            )

    # ------------------------------------------------------------------
    # Pestaña 3: Entrenamiento
    # ------------------------------------------------------------------
    def _detectar_gpu_en_hilo(self):
        def tarea():
            disponible = False
            try:
                import torch

                disponible = bool(
                    torch.cuda.is_available() and torch.cuda.device_count() > 0
                )
            except Exception:
                disponible = False
            self._en_ui(self._gpu_detectada, disponible)

        threading.Thread(target=tarea, daemon=True).start()

    def _gpu_detectada(self, disponible):
        self._gpu_disponible = disponible
        if disponible:
            self.cmb_dispositivo.config(values=("CPU", "GPU"))
            self.lbl_gpu.config(
                text=(
                    "GPU detectada: sí. Se usa CPU por defecto; elige GPU si quieres "
                    "entrenar más rápido."
                ),
                foreground=COLOR_OK,
            )
        else:
            self.cmb_dispositivo.config(values=("CPU",))
            self.var_dispositivo.set("CPU")
            self.lbl_gpu.config(
                text="GPU detectada: no. Se usará CPU.", foreground=COLOR_NEUTRO
            )

    def _elegir_carpeta(self):
        inicial = self.var_dataset.get().strip()
        if not inicial or not Path(inicial).exists():
            ultima = sesion_mas_reciente()
            inicial = str(ultima) if ultima is not None else str(CAPTURAS_DIR)
        elegida = filedialog.askdirectory(
            title="Elegir carpeta del dataset", initialdir=inicial
        )
        if elegida:
            self.var_dataset.set(elegida)

    def entrenar(self):
        if self.pipeline_corriendo:
            messagebox.showwarning(
                "Operación en marcha",
                "No puedes entrenar mientras la laptop está en operación. "
                "Pulsa Detener en la pestaña Operación.",
            )
            return
        if self.entrenando:
            return

        carpeta = Path(self.var_dataset.get().strip())
        if not self.var_dataset.get().strip() or not carpeta.exists():
            messagebox.showerror(
                "Falta la carpeta",
                "Elige una carpeta con fotos de captura antes de entrenar.",
            )
            return

        try:
            minutos = int(self.var_tiempo.get())
            epocas = int(self.var_epocas.get())
        except ValueError:
            messagebox.showerror(
                "Datos inválidos", "El tiempo y las épocas deben ser números enteros."
            )
            return
        if minutos < 1 or epocas < 1:
            messagebox.showerror(
                "Datos inválidos", "El tiempo y las épocas deben ser mayores que cero."
            )
            return

        dispositivo = (
            "0" if self.var_dispositivo.get().strip().upper().startswith("GPU") else "cpu"
        )
        if dispositivo == "0" and not self._gpu_disponible:
            messagebox.showerror(
                "GPU no disponible",
                "No se detectó una GPU compatible. Elige CPU para entrenar.",
            )
            return

        self.entrenando = True
        self._actualizar_estado_laptop()
        self._actualizar_botones()
        self.btn_usar_modelo.config(state="disabled")
        self.lbl_resultado.config(
            text="Entrenamiento en marcha...", foreground=COLOR_AVISO
        )
        self.lbl_metricas.config(text="")
        self._salida_entrenamiento = []
        self._datos_entrenamiento = None
        self._ultimo_best = None
        self._limpiar_progreso()
        self.progreso.start(12)
        self._log(
            "Entrenamiento iniciado: {} épocas, {} minutos, {}.".format(
                epocas, minutos, "GPU" if dispositivo == "0" else "CPU"
            )
        )

        def tarea():
            try:
                self._en_ui(self._log, "Preparando las fotos para entrenar...")
                datos = preparar_para_entrenamiento(carpeta)
                self._datos_entrenamiento = datos
                self._en_ui(self._preparacion_lista, datos)
                comando = construir_comando_entrenamiento(
                    datos["yaml"], minutos, epocas, dispositivo, ENTRENAMIENTO_DIR
                )
                self._en_ui(self._log, "Comando: {}".format(" ".join(comando)))
                self._ejecutar_entrenamiento(comando, datos)
            except Exception as error:
                self._en_ui(self._entrenamiento_fallo, str(error))

        threading.Thread(target=tarea, daemon=True).start()

    def _limpiar_progreso(self):
        self.txt_progreso.config(state="normal")
        self.txt_progreso.delete("1.0", "end")
        self.txt_progreso.config(state="disabled")

    def _preparacion_lista(self, datos):
        self._log(
            "Fotos preparadas: {} para entrenar y {} para validar.".format(
                datos["train"], datos["val"]
            )
        )
        if not datos["confiable"]:
            self.lbl_resultado.config(
                text=(
                    "La validación no es suficiente: al terminar, el resultado se "
                    "mostrará como NO CONFIABLE."
                ),
                foreground=COLOR_AVISO,
            )
            self.lbl_metricas.config(
                text="\n".join(datos["faltantes"]), foreground=COLOR_AVISO
            )
        else:
            self.lbl_resultado.config(
                text="Validación suficiente. Entrenando...", foreground=COLOR_AVISO
            )

    def _ejecutar_entrenamiento(self, comando, datos):
        entorno = os.environ.copy()
        entorno["PYTHONUNBUFFERED"] = "1"
        entorno["PYTHONIOENCODING"] = "utf-8"

        opciones = {}
        if os.name == "nt":
            opciones["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proceso = subprocess.Popen(
            comando,
            cwd=str(config.RAIZ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=entorno,
            **opciones,
        )
        self._proceso_entrenamiento = proceso

        for linea in proceso.stdout:
            for fragmento in re.split(r"[\r\n]+", linea):
                limpia = limpiar_linea(fragmento)
                if not limpia:
                    continue
                self._salida_entrenamiento.append(limpia)
                if len(self._salida_entrenamiento) > 4000:
                    self._salida_entrenamiento = self._salida_entrenamiento[-4000:]
                self._en_ui(self._actualizar_progreso, limpia)

        codigo = proceso.wait()
        self._proceso_entrenamiento = None
        texto = "\n".join(self._salida_entrenamiento)
        resultado = parsear_resultado(texto)
        resultado["codigo"] = codigo
        resultado["faltantes"] = datos.get("faltantes", [])

        if codigo != 0 and resultado.get("best") is None:
            ultimas = "\n".join(self._salida_entrenamiento[-8:])
            self._en_ui(
                self._entrenamiento_fallo,
                "El entrenamiento terminó con error (código {}).\n{}".format(
                    codigo, ultimas
                ),
            )
            return

        self._en_ui(self._entrenamiento_terminado, resultado)

    def _actualizar_progreso(self, linea):
        self.txt_progreso.config(state="normal")
        self.txt_progreso.insert("end", linea + "\n")
        try:
            total_lineas = int(self.txt_progreso.index("end-1c").split(".")[0])
            if total_lineas > 6:
                self.txt_progreso.delete("1.0", "2.0")
        except Exception:
            pass
        self.txt_progreso.see("end")
        self.txt_progreso.config(state="disabled")

    def _entrenamiento_terminado(self, resultado):
        self.entrenando = False
        self.progreso.stop()
        self._actualizar_estado_laptop()
        self._actualizar_botones()

        best = resultado.get("best")
        if best is not None:
            best = Path(best)
            if not best.exists():
                # Respaldo: la ruta estándar de Ultralytics.
                candidato = (
                    ENTRENAMIENTO_DIR
                    / "runs"
                    / best.parent.parent.name
                    / "weights"
                    / "best.pt"
                )
                if candidato.exists():
                    best = candidato
        self._ultimo_best = best if best is not None and best.exists() else None

        datos = self._datos_entrenamiento or {}
        faltantes = resultado.get("faltantes") or datos.get("faltantes") or []
        confiable = bool(resultado.get("confiable")) and not resultado.get(
            "no_confiable"
        )
        self._ultimo_confiable = confiable
        self._ultimo_faltantes = list(faltantes)

        if not confiable:
            self.lbl_resultado.config(
                text="NO CONFIABLE: pocas imágenes de validación",
                foreground=COLOR_ERROR,
            )
            detalle = list(faltantes)
            if not detalle:
                detalle = [
                    "Se necesitan al menos {} imágenes de validación y {} figuras "
                    "de cada clase.".format(
                        config.MIN_IMAGENES_VAL, config.MIN_INSTANCIAS_POR_CLASE
                    )
                ]
            self.lbl_metricas.config(
                text=(
                    "No se muestran mAP50 ni mAP50-95 porque la validación no es "
                    "suficiente.\n" + "\n".join(detalle)
                ),
                foreground=COLOR_ERROR,
            )
        else:
            mapa50 = resultado.get("map50")
            mapa5095 = resultado.get("map50_95")
            self.lbl_resultado.config(
                text="Entrenamiento terminado.", foreground=COLOR_OK
            )
            if mapa50 is None:
                self.lbl_metricas.config(
                    text="No se pudo leer el mAP del entrenamiento.",
                    foreground=COLOR_AVISO,
                )
            else:
                lineas = [
                    "mAP50 (precisión promedio al 50 % de coincidencia): {:.4f}".format(
                        mapa50
                    )
                ]
                if mapa5095 is not None:
                    lineas.append(
                        "mAP50-95 (precisión promedio más exigente): {:.4f}".format(
                            mapa5095
                        )
                    )
                if mapa50 >= 0.70:
                    lineas.append("Cumple el mínimo recomendado de 0.70.")
                    color = COLOR_OK
                else:
                    lineas.append("Está por debajo del mínimo recomendado de 0.70.")
                    color = COLOR_AVISO
                self.lbl_metricas.config(
                    text="\n".join(lineas), foreground=color
                )

        if self._ultimo_best is not None:
            self.btn_usar_modelo.config(state="normal")
            self._log(
                "Entrenamiento terminado. Mejor modelo: {}".format(self._ultimo_best)
            )
        else:
            self.btn_usar_modelo.config(state="disabled")
            self._log("Entrenamiento terminado, pero no se encontró best.pt.")

    def _entrenamiento_fallo(self, mensaje):
        self.entrenando = False
        self.progreso.stop()
        self._actualizar_estado_laptop()
        self._actualizar_botones()
        self.btn_usar_modelo.config(state="disabled")
        self.lbl_resultado.config(
            text="El entrenamiento no terminó.", foreground=COLOR_ERROR
        )
        self.lbl_metricas.config(text=mensaje, foreground=COLOR_ERROR)
        self._log("Entrenamiento fallido: {}".format(mensaje))

    def _usar_modelo(self):
        if self._ultimo_best is None:
            messagebox.showerror(
                "Sin modelo", "Todavía no hay un modelo entrenado para usar."
            )
            return

        aviso = ""
        if not self._ultimo_confiable:
            aviso = (
                "\n\nAtención: el resultado fue NO CONFIABLE por pocas imágenes de "
                "validación. Úsalo solo si confías en el entrenamiento."
            )
        confirmar = messagebox.askyesno(
            "Usar este modelo en la competencia",
            (
                "¿Copiar el modelo entrenado a:\n{}\n\n"
                "No se cambia config.py. El modo de detección ya es yolo.{}"
            ).format(config.PESOS_ENTRENADO, aviso),
        )
        if not confirmar:
            return

        try:
            destino = copiar_modelo(self._ultimo_best)
        except Exception as error:
            messagebox.showerror(
                "No se pudo copiar el modelo", str(error)
            )
            self._log("No se pudo copiar el modelo: {}".format(error))
            return

        self._log("Modelo copiado a {}".format(destino))
        messagebox.showinfo(
            "Modelo listo",
            "El modelo quedó en:\n{}\n\nNo se cambió config.py.".format(destino),
        )

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------
    def _cerrar(self):
        if self._cerrando:
            return
        self._cerrando = True

        cam = self._cam_captura
        self._cam_captura = None
        if cam is not None:
            try:
                cam.cerrar()
            except Exception:
                pass

        proceso = self._proceso_entrenamiento
        if proceso is not None and proceso.poll() is None:
            try:
                proceso.terminate()
            except Exception:
                pass

        if self.pipeline_corriendo:
            try:
                main.detener_pipeline(self.estado)
            except Exception:
                pass

        try:
            self.root.destroy()
        except Exception:
            pass


def main_gui():
    if not TK_OK:
        print("tkinter no disponible")
        return
    root = tk.Tk()
    Aplicacion(root)
    root.mainloop()


if __name__ == "__main__":
    main_gui()
