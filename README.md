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
| Dataset | 🔄 23 train + 20 val (val ya tiene H y S; muchos negativos) |
| `rescate.yaml` | ✅ Listo y portable (sin ruta absoluta) |
| Entrenamiento | ⬜ Pendiente (`modelo/entrenar.py`) |
| Evaluación | ⬜ Pendiente (`modelo/evaluar.py`) |
| Detección por color | ✅ `logica/deteccion_color.py` (prueba sintética OK) |
| Calibración de color | ✅ Inicial con IP Webcam (recalibrar en el evento) |
| Stream de video | ✅ `stream/recibir.py` (IP Webcam en hilo, frames recientes) |
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
│   ├── recibir.py            # Cámara IP Webcam en hilo (último frame)
│   │                         # En competencia, URL del stream del robot
│   └── capturar.py           # Herramienta: guarda frames + etiquetas YOLO
└── logica/
    ├── deteccion_color.py    # Detector HSV (H naranja, S morado)
    ├── calibrar_color.py     # Ajuste en vivo de los rangos HSV
    ├── probar_en_vivo.py     # Prueba el detector con cajas y conteo
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

### Activar el entorno virtual (cada sesión)

El entorno **no queda activo solo**: hay que activarlo en cada terminal nueva.
Si no ves `(.venv)` al inicio del prompt, `python` usará el Python del sistema
(3.15) y fallará con `ModuleNotFoundError`.

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Debe verse así:

```
(.venv) PS D:\Documents\Proyectos\Codigo_Coriot>
```

Si PowerShell bloquea la activación por política de ejecución:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Alternativa sin activar (usa siempre el Python correcto):

```powershell
.\.venv\Scripts\python.exe -m logica.deteccion_color
```

Si usas VS Code, selecciona el intérprete `.venv\Scripts\python.exe`
(`Ctrl+Shift+P` → *Python: Select Interpreter*) para que las terminales nuevas
lo usen por defecto.

El `.venv/`, los pesos `.pt` y el dataset **no están en Git**: se regeneran o
se copian aparte.

---

## 5. Calibración de color (IP Webcam)

La detección por color necesita ajustar los rangos HSV a la luz y a las figuras
reales. Para desarrollo se usa un celular con **IP Webcam** como cámara.

### Preparar el celular

1. Instalar **IP Webcam** y conectar celular y laptop a la misma red Wi-Fi.
2. Pulsar “Start server” y copiar la URL (ej. `http://192.168.80.145:8080`).
3. En los ajustes de la app, bajar la resolución a **640×480** para reducir
   latencia.
4. Poner la URL del video en `config.py`:

   ```python
   FUENTE_VIDEO = "http://192.168.80.145:8080/video"
   ```

### Calibrar

Con el entorno activo y el objeto naranja o morado frente a la cámara:

```powershell
python -m logica.calibrar_color H   # naranja
python -m logica.calibrar_color S   # morado
```

Se abren dos ventanas: el video con la caja detectada y la **máscara** (blanco =
color detectado). Ajustar las barras hasta que en la máscara solo quede blanca
la figura:

| Barra | Controla | Ajuste |
|---|---|---|
| `H_min` / `H_max` | Tono (el color) | Estrechar alrededor del color. |
| `S_min` / `S_max` | Saturación (pureza) | Subir `S_min` para quitar blancos/grises. |
| `V_min` / `V_max` | Brillo | Subir `V_min` para quitar sombras. |

Teclas:
- **`p`** imprime la línea lista para pegar en `config.py`.
- **`q`** cierra las ventanas.

Pegar las dos líneas en `RANGOS_HSV` dentro de `config.py`:

```python
RANGOS_HSV = {
    "H": ((...), (...)),   # naranja calibrado
    "S": ((...), (...)),   # morado calibrado
}
```

### Si el video va lento

1. En IP Webcam: resolución **640×480**, calidad **50 %**, **15–20 FPS**.
2. Usar `stream/recibir.py`, que lee en un hilo y descarta los frames viejos.
3. Probar la fluidez sin calibrar:

   ```powershell
   python -m stream.recibir
   ```

4. Si sigue lento, probar `http://IP:8080/videofeed` o acercar el celular al
   router (idealmente 5 GHz).

> Repetir la calibración el día del evento bajo la luz del auditorio: los
> valores de casa no sirven en otra iluminación.

---

## 6. Captura del dataset (YOLO)

Herramienta de **preparación**, no del runtime de competencia: sirve para
construir el dataset en casa y, sobre todo, en la sesión de práctica del evento.

```powershell
python -m stream.capturar
```

Muestra el video en vivo con las cajas del detector de color y guarda el frame
**sin dibujos** junto con su etiqueta `.txt` en formato YOLO. Haz **clic en la
ventana del video** antes de usar las teclas.

| Tecla | Carpeta | Qué guarda |
|---|---|---|
| `s` | `dataset/images/train` + `labels/train` | Frame con etiqueta automática (entrenamiento). |
| `v` | `dataset/images/val` + `labels/val` | Igual, pero para **validación**. |
| `n` | `dataset/images/train` | Frame con etiqueta **vacía** (negativo forzado). |
| `q` | — | Cierra. |

Reglas prácticas:

- **~80 % `train`, ~20 % `val`**. El conjunto `val` debe tener imágenes **con**
  víctimas (H, S, ambas) y también negativos; si es solo de escenas vacías, las
  métricas no sirven.
- Mover la figura y cambiar ángulo, distancia, luz y posición entre capturas:
  muchas fotos casi iguales aportan poco.
- Usar `n` cuando el detector se equivoque (objeto naranja que no es víctima).
- Revisar las etiquetas automáticas antes de entrenar (LabelImg, CVAT o
  Roboflow): el detector de color solo acelera el trabajo.

> Las fotos reales de las víctimas solo existen el día del evento. Hasta
> entonces se trabaja con objetos naranjas/morados y el dataset queda como
> prueba del flujo.

---

## 7. Decisiones y convenciones

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

## 8. Hoja de ruta (checklist)

- [x] Instalar Python 3.12 y crear `.venv`
- [x] Instalar ultralytics + opencv
- [x] Crear estructura de carpetas
- [x] `config.py` y esqueleto de `main.py`
- [x] `modelo/verificar_entorno.py` funcionando
- [x] `modelo/rescate.yaml` portable
- [x] Conectar repositorio Git
- [x] `logica/deteccion_color.py` (HSV naranja/morado)
- [x] Calibrar rangos HSV iniciales con cámara real (recalibrar en evento)
- [ ] Capturar fotos de las figuras H y S (desde la cámara del robot)
- [ ] Etiquetar el dataset (Roboflow / CVAT / LabelImg)
- [ ] `modelo/entrenar.py` (YOLO11n, hiperparámetros)
- [ ] `modelo/evaluar.py` (mAP50, mAP50-95, precisión/recall por clase)
- [x] `stream/recibir.py` (IP Webcam en hilo, frames recientes)
- [x] `stream/capturar.py` (dataset con etiquetas automáticas)
- [ ] `logica/cuadrante.py` (color de piso u odometría)
- [ ] `logica/iot.py` (definir protocolo y JSON)
- [ ] Integrar todo en `main.py`
- [ ] Pruebas en pista real y calibración de umbrales
- [ ] (Opcional) Docker para reproducibilidad

---

## 9. Cómo continuar en otra sesión de OpenCode

1. Leer `README.md` y `Contexto.txt` completos.
2. `git pull` para traer los últimos cambios.
3. Activar `.venv` y confirmar versiones con `modelo/verificar_entorno.py`.
4. Revisar la sección **Estado actual** y la **bitácora** antes de tocar código.
5. Trabajar **un paso a la vez**, explicando los comandos (el usuario prefiere
   ejecutarlos él para aprender).
6. Al terminar la sesión: actualizar **Estado actual**, **Hoja de ruta** y
   **Bitácora** de este README, luego `git add / commit / push`.

---

## 10. Problemas conocidos (gotchas)

- **Python 3.15 no sirve** para PyTorch todavía. Usar 3.12.
- **`ModuleNotFoundError: No module named 'cv2'`**: la terminal no tiene el
  `.venv` activo. Activarlo con `.\.venv\Scripts\Activate.ps1` o ejecutar con
  `.\.venv\Scripts\python.exe`.
- **IP Webcam**: si el celular cambia de IP, actualizar `FUENTE_VIDEO` en
  `config.py`.
- **Video lento con IP Webcam**: bajar la resolución a 640×480 y usar
  `stream/recibir.py` (hilo + descarte de frames viejos).
- **Rojo y naranja comparten tono**: con `H_min=0`, un objeto rojo también se
  detecta como H. Si el piso o el entorno tienen rojo, subir `H_min` o
  restringir la zona de detección.
- **Etiquetas automáticas**: las genera el detector de color; pueden estar
  incompletas o incluir falsos positivos. Revisarlas antes de entrenar.
- **Validación (`val`)**: debe contener imágenes **con** víctimas y también
  negativos; si es solo de escenas vacías, las métricas no sirven.
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

## 11. Bitácora de sesiones

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

### 2026-10-29 — Detección por color
- Se creó `logica/deteccion_color.py` (HSV + morfología + filtro de área) y se
  validó con una imagen sintética: confianza ≈ 0.99.
- Se conectó **IP Webcam** (`http://192.168.80.145:8080/video`) y se verificó
  con OpenCV: `isOpened=True`, frames de 1920×1080.
- Se creó `logica/calibrar_color.py` para ajustar los rangos HSV en vivo
  (teclas `p` = imprimir, `q` = salir).
- Pendiente: calibrar H y S con objetos reales y guardar los valores en
  `config.py`.

### 2026-10-29 — Fluidez del stream
- El video de IP Webcam iba lento por 1920×1080 y por frames viejos en el
  buffer.
- Se creó `stream/recibir.py`: hilo de lectura que conserva solo el último
  frame y reduce el ancho a 640 px.
- Se bajó IP Webcam a 640×480; la imagen quedó fluida.
- Pendiente: validar que los rangos HSV actuales no detecten colores vecinos.

### 2026-10-29 — Calibración validada
- Rango naranja ajustado a **H 0–25** (antes 0–70 detectaba amarillo y verde).
- Prueba sintética: amarillo y verde ya no se detectan; el morado sigue en S.
- Se creó `logica/probar_en_vivo.py` para validar cajas y conteo en vivo.
- Ojo: el rojo (H≈0) también entra como H; revisar el color del piso y de los
  obstáculos.

### 2026-10-29 — Captura del dataset
- Se creó `stream/capturar.py`: guarda el frame limpio + etiqueta YOLO
  automática con el detector de color (`s` = train, `v` = val, `n` = negativo
  forzado, `q` = salir).
- Dataset actual: **21 imágenes en `train`** (5 con etiqueta vacía) y
  **7 en `val`, todas con etiqueta vacía**.
- Problema detectado: `val` sin ningún positivo → no sirve para medir
  detección de H/S. Hay además capturas casi duplicadas en `train`.
- Pendiente: borrar/rehacer `val` con mezcla de H, S, ambas y negativos, con
  ~80/20 train/val y moviendo la figura entre capturas.

### 2026-10-29 — Val corregido
- `val` pasó de 7 imágenes todas vacías a **20 imágenes**, de las cuales **8
  tienen figuras** (5 cajas H y 5 cajas S) y 12 son negativas.
- `train` quedó en **23 imágenes** (5 negativas).
- Reparto actual: 53 % train / 47 % val; a futuro conviene acercarlo a 80/20
  moviendo negativos de `val` a `train`.
- Sigue apareciendo alguna caja muy pequeña (ej. 22×42 px) señal de detección
  parcial: revisar antes de entrenar.
