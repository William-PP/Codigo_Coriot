# Código Rescate — CORIOT GAMES 2026

> **DOCUMENTO VIVO.** Este README es la memoria del proyecto entre sesiones y
> entre computadores. **Actualizarlo al final de cada sesión de trabajo**
> (estado, decisiones, problemas y bitácora). Si otra sesión de OpenCode va a
> continuar, debe leer primero este archivo y `Contexto.txt`.

**Última actualización:** 2026-10-29

---

## 1. Qué es el proyecto

Robot autónomo para el reto **Código Rescate** (CORIOT GAMES 2026, 12 de
noviembre de 2026). Debe:

- Detectar visualmente **víctimas** con YOLO11n:
  - **H** = herida → figura **naranja**.
  - **S** = suministros → figura **morado**.
- Asociar cada víctima al **cuadrante** correcto (pista de 2 m × 2 m, 4
  cuadrantes de 1 m × 1 m, 12 víctimas, sin líneas guía en el piso).
- Reportar por **Wi-Fi/IoT** un JSON con los conteos H y S por cuadrante.
- **Derribar físicamente** cada figura como confirmación (no manipularla).
- Todo el cómputo es autónomo (a bordo u off-board en red privada).

El reglamento completo y las medidas del robot están en `Contexto.txt`.

### Arquitectura de cómputo (decisión)

La **laptop** es el cerebro: recibe el video del robot por Wi-Fi privada y
ejecuta toda la visión (color/YOLO), la asociación a cuadrantes y el envío IoT.
El **microcontrolador** del robot solo controla motores, sensores y el
mecanismo de derribo; **no procesa imágenes**.

```
[Robot: cámara + microcontrolador + motores + derribo]
        │  video por Wi-Fi (MJPEG/RTSP)
        ▼
[Laptop: stream → detección → cuadrante → IoT]
        │  JSON al broker de la competencia
        │  comandos por Wi-Fi al robot (derribo)
        ▼
[Robot: actuador de derribo]
```

Esto es válido porque el reglamento permite cómputo **off-board** en una
laptop conectada por red inalámbrica privada (ver `Contexto.txt`, sección 1).

---

## 2. Estado actual

| Área | Estado |
|---|---|
| Python / entorno virtual | ✅ Python **3.12.10** en `.venv/` |
| Librerías | ✅ ultralytics **8.4.192**, opencv **5.0.0**, torch **2.15.0+cpu** |
| Verificación del entorno | ✅ `modelo/verificar_entorno.py` ejecuta una inferencia real |
| Estructura de carpetas | ✅ `modelo/`, `stream/`, `logica/`, `config.py`, `main.py` |
| Dataset | ⬜ Carpetas creadas (`modelo/dataset/`), **sin imágenes todavía** |
| `rescate.yaml` | ✅ Listo y portable (sin ruta absoluta) |
| Entrenamiento | ⬜ Pendiente (`modelo/entrenar.py`) |
| Evaluación | ⬜ Pendiente (`modelo/evaluar.py`) |
| Stream de video | ⬜ Pendiente (`stream/recibir.py`) |
| Cuadrante + IoT | ⬜ Pendiente (`logica/`) |
| Git | ✅ Conectado a `github.com/William-PP/Codigo_Coriot` |

> Ojo: el modelo base `yolo11n.pt` está entrenado con COCO (80 clases:
> `person`, `bus`, etc.). **Todavía no conoce H ni S**; eso requiere entrenar
> con el dataset propio.

---

## 3. Estructura del proyecto

```
Codigo_Coriot/
├── Contexto.txt              # Reglamento y requisitos del reto
├── Requirements.txt          # Dependencias (ultralytics, opencv-python)
├── README.md                 # Este documento (mantener actualizado)
├── config.py                 # Rutas, clases, umbrales, broker
├── main.py                   # Punto de entrada / orquestador (esqueleto)
├── modelo/
│   ├── verificar_entorno.py  # Diagnóstico: versiones + inferencia de prueba
│   ├── rescate.yaml          # Dataset y clases para YOLO
│   ├── entrenar.py           # (pendiente) YOLO11n + hiperparámetros
│   ├── evaluar.py            # (pendiente) mAP50, mAP50-95, P/R por clase
│   ├── pesos/                # yolo11n.pt y modelos entrenados (ignorado en Git)
│   └── dataset/              # images/ y labels/ (ignorado en Git)
│       ├── images/train/
│       ├── images/val/
│       ├── labels/train/
│       └── labels/val/
├── stream/
│   └── recibir.py            # (pendiente) recibe video del robot por Wi-Fi
│                             # (webcam de la laptop solo para desarrollo)
└── logica/
    ├── cuadrante.py          # (pendiente) detección → cuadrante
    └── iot.py                # (pendiente) JSON → broker
```

> La carpeta real es `Codigo_Coriot/` (el contexto habla de `codigo_rescate/`;
> se unificó con el nombre del repositorio).

---

## 4. Puesta en marcha en otro computador

1. Instalar **Python 3.12** (NO 3.15: PyTorch aún no publica wheels para ella).
   En Windows, el instalador de python.org con “Add python.exe to PATH”.
2. Clonar y entrar:

   ```bash
   git clone https://github.com/William-PP/Codigo_Coriot.git
   cd Codigo_Coriot
   ```

3. Crear y activar el entorno:

   ```powershell
   # Windows PowerShell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   ```bash
   # Linux / macOS
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

4. Instalar dependencias:

   ```bash
   python -m pip install --upgrade pip
   pip install -r Requirements.txt
   ```

5. Verificar:

   ```bash
   python -c "import ultralytics, cv2; print(ultralytics.__version__, cv2.__version__)"
   python modelo/verificar_entorno.py
   ```

El `.venv/`, los pesos `.pt` y el dataset **no están en Git**: se regeneran o
se copian aparte.

---

## 5. Decisiones y convenciones

- **Laptop = cerebro**: toda la visión, los cuadrantes y el IoT corren en la
  laptop.
- **Microcontrolador = actuadores**: motores, sensores y mecanismo de derribo,
  sin procesar imágenes.
- **Video robot → laptop** por Wi-Fi privada (MJPEG/RTSP); los comandos
  laptop → robot (derribo) viajan por la misma red.
- **Python 3.12** para compatibilidad con PyTorch/ultralytics.
- **YOLO11n** como modelo base (ligero, apto para Raspberry Pi/Jetson).
- Clases en `rescate.yaml`: `0: H`, `1: S` (no cambiar el orden).
- **Dataset en formato YOLO**: un `.txt` por imagen, líneas
  `clase cx cy w h` normalizadas (0–1).
- **No usar `path:` absoluto en `rescate.yaml`.** Si se omite, ultralytics usa
  la carpeta del YAML como raíz; así funciona en Windows, Linux y Docker.
  (`train: dataset/images/train`, `val: dataset/images/val`.)
- Configuración centralizada en `config.py` (rutas con `Path(__file__)`).
- Carpetas y módulos en minúsculas (Linux distingue mayúsculas).
- Comentarios y documentación en **español**.
- **No agregar dependencias** sin actualizar `Requirements.txt` y este README.
- Umbrales por defecto: confianza `0.25`, IoU `0.45`.
- Dataset: ~80 % `train`, ~20 % `val`; incluir escenas sin víctimas (etiqueta
  vacía) para reducir falsos positivos.

---

## 6. Hoja de ruta (checklist)

- [x] Instalar Python 3.12 y crear `.venv`
- [x] Instalar ultralytics + opencv
- [x] Crear estructura de carpetas
- [x] `config.py` y esqueleto de `main.py`
- [x] `modelo/verificar_entorno.py` funcionando
- [x] `modelo/rescate.yaml` portable
- [x] Conectar repositorio Git
- [ ] Capturar fotos de las figuras H y S (desde la cámara del robot)
- [ ] Etiquetar el dataset (Roboflow / CVAT / LabelImg)
- [ ] `modelo/entrenar.py` (YOLO11n, hiperparámetros)
- [ ] `modelo/evaluar.py` (mAP50, mAP50-95, precisión/recall por clase)
- [ ] `stream/recibir.py` (webcam o stream del robot)
- [ ] `logica/cuadrante.py` (color de piso u odometría)
- [ ] `logica/iot.py` (definir protocolo y JSON)
- [ ] Integrar todo en `main.py`
- [ ] Pruebas en pista real y calibración de umbrales
- [ ] (Opcional) Docker para reproducibilidad

---

## 7. Cómo continuar en otra sesión de OpenCode

1. Leer `README.md` y `Contexto.txt` completos.
2. `git pull` para traer los últimos cambios.
3. Activar `.venv` y confirmar versiones con `modelo/verificar_entorno.py`.
4. Revisar la sección **Estado actual** y la **bitácora** antes de tocar código.
5. Trabajar **un paso a la vez**, explicando los comandos (el usuario prefiere
   ejecutarlos él para aprender).
6. Al terminar la sesión: actualizar **Estado actual**, **Hoja de ruta** y
   **Bitácora** de este README, luego `git add / commit / push`.

---

## 8. Problemas conocidos (gotchas)

- **Python 3.15 no sirve** para PyTorch todavía. Usar 3.12.
- El `py` launcher no ve la instalación de Microsoft Store; instalar Python
  3.12 desde python.org/winget y usar `py -3.12`.
- **`path` relativo en YAML**: ultralytics lo resuelve contra su carpeta global
  de datasets, no contra el YAML. Por eso se omite `path`.
- **Imágenes por URL**: `predict("https://...")` descarga el archivo en la
  carpeta actual. En `verificar_entorno.py` se descarga en memoria para no
  crear archivos fuera de `modelo/`.
- **Docker/Linux**: `opencv-python` necesita `libgl1` y `libglib2.0-0`, o usar
  `opencv-python-headless`. Montar `modelo/pesos/` y `modelo/dataset/` como
  volúmenes.
- Ultralytics escribe en `runs/` por defecto; en `entrenar.py` fijar
  `project="modelo/runs"`.

---

## 9. Bitácora de sesiones

### 2026-10-29 — Configuración inicial
- Se detectó que no había Python real (solo alias de Microsoft Store) y que
  `Contexto.txt`/`Requirements.txt` estaban vacíos.
- Se instaló Python 3.12.10 y se creó `.venv/` con ultralytics 8.4.192,
  opencv 5.0.0 y torch 2.15.0+cpu.
- Se renombraron `Moldelo/` → `modelo/`, `Steam/` → `stream/`,
  `Logica/` → `logica/`.
- Se crearon `config.py`, `main.py`, `README.md`, `.gitignore`.
- `modelo/verificar_entorno.py`: descarga `yolo11n.pt`, infiere sobre
  `bus.jpg` en memoria e imprime clase + confianza.
- `modelo/rescate.yaml`: clases H/S, rutas relativas portables.
- Dataset: carpetas creadas, sin imágenes aún.
- Repositorio Git conectado a `github.com/William-PP/Codigo_Coriot`.
- Se definió que la **laptop** procesa toda la visión e IoT; el
  microcontrolador solo actúa sobre motores y derribo (cómputo off-board).
