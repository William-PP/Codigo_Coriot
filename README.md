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
| Cuadrante por color de piso | 🔄 Código listo y probado solo sintético; **sin validar** hasta decidir sensor vs cámara |
| Flujo en `main.py` | ✅ stream → detección → conteo → reporte JSON (sin cuadrante aún) |
| IoT | ⬜ Pendiente (`logica/iot.py`): falta el protocolo oficial |
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
├── main.py                   # Flujo: stream → detección → conteo → JSON
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
    ├── deteccion_yolo.py     # Detector YOLO (misma interfaz que el de color)
    ├── contador.py           # Conteo por cuadrante sin doble conteo
    ├── calibrar_color.py     # Ajuste en vivo de los rangos HSV
    ├── probar_en_vivo.py     # Prueba el detector con cajas y conteo
    ├── cuadrante.py          # Color del piso → cuadrante (1-4) + prueba en vivo
    ├── calibrar_piso.py      # Guarda el color de piso de cada cuadrante
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

## 7. Cuadrante por color de piso

> **⚠️ Implementación provisional, sin pruebas por ahora.**
> El reglamento permite **dos caminos** para saber el cuadrante:
>
> 1. **Sensor de color hacia el suelo** (ej. TCS34725, sensor de línea RGB).
> 2. **Cámara de navegación** apuntando al piso (el código actual).
>
> Todavía **no está decidido** cuál se va a usar en el robot. Por eso este
> módulo queda escrito y probado solo con imágenes sintéticas, pero **no se
> validará en pista ni se integrará a `main.py` hasta definir el hardware**.
> Si al final se usa un sensor de color, `logica/cuadrante.py` cambia de fuente
> de datos (lee el sensor por serie/I2C en vez de la franja del frame), pero la
> calibración y la lógica de "color → cuadrante" se reutilizan tal cual.

El reglamento pide asociar cada víctima a **uno de los 4 cuadrantes** (1 m × 1 m
cada uno, pista total 2 m × 2 m) y el piso de cada cuadrante está pintado de un
color distinto. La cámara de víctimas no sabe en qué cuadrante está, así que se
usa el **color del piso bajo el robot**.

La idea:

```
franja inferior del frame  →  color HSV  →  cuadrante (1-4)  →  sumar H y S
```

### Calibrar el piso (en la pista, no en casa)

Los colores del piso del auditorio no se conocen hasta el evento, así que
`modelo/piso.json` se genera allí (y está ignorado en Git). Esto aplica solo si
al final se usa la **cámara** para leer el piso; con un sensor de color, la
calibración se hace sobre el sensor.

```powershell
python -m logica.calibrar_piso
```

1. Apunta la cámara al piso del cuadrante 1 (la franja verde inferior debe caer
   sobre ese color).
2. Pulsa `1`. Repite con los cuadrantes `2`, `3` y `4`.
3. `q` para salir. Se guarda `modelo/piso.json` con el HSV de cada cuadrante.

Teclas: `1`–`4` guardan, `r` borra toda la calibración, `q` sale.

### Probar (opcional, cuando se decida el hardware)

```powershell
python -m logica.cuadrante
```

Muestra en pantalla `cuadrante: N` y la distancia al color calibrado. Mueve la
cámara entre cartulinas de colores: debe cambiar de cuadrante.

### Cómo funciona `logica/cuadrante.py`

| Función | Qué hace |
|---|---|
| `leer_piso(frame)` | HSV promedio de la franja inferior (15 % del alto). |
| `cargar()` / `guardar()` | Lee y escribe `modelo/piso.json`. |
| `clasificar(hsv, colores)` | Devuelve `(cuadrante, distancia)`; `0` si no se parece a ninguno. |

Detalles que importan:

- El tono (H) es **circular**: 0 y 179 son el mismo rojo, así que se promedia
  como vector con peso por saturación.
- Un piso **gris/blanco/negro no tiene tono**: se rechaza con
  `SAT_MIN = 50` y devuelve cuadrante `0`.
- `DIST_MAX = 0.30`: si el color no se parece lo suficiente a ninguno
  calibrado, no se inventa un cuadrante.
- La lectura del piso se limita a la **franja inferior** para que las figuras
  (y sobre todo una figura naranja) no contaminen el color del piso.

### Pendiente

- **Contador**: ya existe `logica/contador.py` (cuenta una figura cuando se ve
  `CONFIRMA_FRAMES` frames seguidos), pero **está sin validar con el hardware
  real**.
- Integrar el cuadrante en `main.py`: se activa con `USAR_CUADRANTE = True`
  cuando se decida el hardware.
---

## 8. Decisiones y convenciones

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
- **El JSON lo envía la laptop**, no el microcontrolador. El reglamento exige
  que el sistema transmita JSON por Wi-Fi al servidor central y permite
  cómputo off-board; no exige que salga del robot. Mandarlo desde la laptop
  evita un salto extra (detección → micro → servidor) y no añade latencia.
  Si algún día se requiere lo contrario, solo cambia `logica/iot.py`.
- **Detector intercambiable**: `config.MODO_DETECCION` = `"color"` (rápido, sin
  entrenar) o `"yolo"` (usa `modelo/pesos/rescate.pt` si existe). Ambos
  devuelven el mismo formato, así que `main.py` no cambia.
- **Conteo**: una figura se cuenta al verse `CONFIRMA_FRAMES` frames seguidos
  (5 por defecto). El derribo físico es la confirmación definitiva.

### Reporte JSON (propuesto)

```json
{
  "robot": "codigo-rescate",
  "tiempo": "2026-11-12T10:15:33",
  "cuadrantes": {
    "0": {"H": 1, "S": 0}
  }
}
```

- `robot`: identificador del equipo (`config.ROBOT_ID`).
- `tiempo`: hora local del reporte (ISO 8601).
- `cuadrantes`: conteo acumulado por cuadrante con claves `"1"`–`"4"`.
  **`"0"` = sin cuadrante**, que es lo que se usa mientras el hardware del
  cuadrante esté en pausa.
- El formato definitivo depende del servidor de la competencia; ajustar
  `reporte_json()` en `main.py` cuando se conozca.

### Flujo de `main.py`

```powershell
python main.py
```

1. Abre el stream (`stream/recibir.py`).
2. Detecta víctimas con el modo de `config.MODO_DETECCION`.
3. Lee el cuadrante (si `USAR_CUADRANTE` y hay `modelo/piso.json`).
4. `logica/contador.py` acumula H y S por cuadrante sin duplicar.
5. Cuando el conteo cambia, imprime el JSON (luego será `logica/iot.py`).
6. `q` cierra y muestra el reporte final.

---

## 9. Hoja de ruta (checklist)

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
- [x] `logica/cuadrante.py` + `calibrar_piso.py` (color de piso → cuadrante)
- [ ] **Decidir hardware del cuadrante: sensor de color al piso vs cámara**
- [ ] Validar el cuadrante con el hardware elegido (bloqueado por la decisión)
- [ ] Contador por cuadrante sin doble conteo (misma víctima en varios frames)
- [ ] `logica/iot.py` (definir protocolo y JSON)
- [x] Flujo `stream → detección → conteo → JSON` en `main.py`
- [x] `logica/contador.py` (sin doble conteo por frames seguidos)
- [ ] Activar cuadrante en `main.py` (`USAR_CUADRANTE`) al decidir el hardware
- [ ] Pruebas en pista real y calibración de umbrales
- [ ] (Opcional) Docker para reproducibilidad

---

## 10. Cómo continuar en otra sesión de OpenCode

1. Leer `README.md` y `Contexto.txt` completos.
2. `git pull` para traer los últimos cambios.
3. Activar `.venv` y confirmar versiones con `modelo/verificar_entorno.py`.
4. Revisar la sección **Estado actual** y la **bitácora** antes de tocar código.
5. Trabajar **un paso a la vez**, explicando los comandos (el usuario prefiere
   ejecutarlos él para aprender).
6. Al terminar la sesión: actualizar **Estado actual**, **Hoja de ruta** y
   **Bitácora** de este README, luego `git add / commit / push`.

---

## 11. Problemas conocidos (gotchas)

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
- **Piso sin color**: una superficie gris, blanca o negra no tiene tono, así que
  se rechaza (cuadrante `0`) en vez de inventar uno. Si el piso real es poco
  saturado, bajar `SAT_MIN` en `logica/cuadrante.py`.
- **Colores vecinos**: cyan se confunde con azul y un piso muy claro con blanco.
  Conviene que los 4 cuadrantes tengan tonos bien separados; si no, calibrar
  con buena luz y revisar las distancias que muestra `python -m logica.cuadrante`.
- **Cuadrante `0` en el JSON**: mientras `USAR_CUADRANTE = False`, el reporte
  acumula todo en `"0"`. No es un error; es el estado provisional.
- **Doble conteo posible**: si una figura desaparece de la vista más de
  `PERDIDA_MAX` (15 frames) y vuelve a aparecer, puede contarse de nuevo. La
  solución real es confirmar con el derribo físico.
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

## 12. Bitácora de sesiones

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

### 2026-10-29 — Cuadrante por color de piso
- Se creó `logica/cuadrante.py`: lee el color de la franja inferior del frame,
  lo promedia en HSV (tono circular, ponderado por saturación) y lo compara con
  los colores calibrados para devolver el número de cuadrante.
- Se creó `logica/calibrar_piso.py`: teclas `1`–`4` guardan el color de cada
  cuadrante en `modelo/piso.json` (ignorado en Git), `r` borra, `q` sale.
- Prueba sintética con verde/azul/amarillo/rojo: acierta los 4 con distancia 0
  y sigue acertando con la luz al 60 % (distancia < 0.05).
- Se corrigió un fallo: un piso gris se clasificaba como rojo (el gris no tiene
  tono). Ahora se rechaza con `SAT_MIN = 50` y devuelve cuadrante `0`.
- Pendiente: contador sin doble conteo y prueba con cartulinas reales.
- **Decisión abierta**: el cuadrante puede resolverse con **sensor de color al
  piso** o con **cámara de navegación**. Mientras no se elija el hardware, este
  módulo queda sin validar en pista y sin integrar a `main.py`; los colores del
  piso tampoco se pueden calibrar de verdad.

### 2026-10-29 — Flujo completo en main.py
- Se confirmó en el reglamento que **el JSON no tiene que salir del
  microcontrolador**: basta con que el sistema lo transmita y el cómputo
  off-board está permitido. Se envía desde la laptop.
- `main.py` quedó operativo: stream → detección → cuadrante (desactivado) →
  conteo → JSON impreso. `config.MODO_DETECCION` elige `"color"` o `"yolo"`.
- `logica/contador.py`: cuenta una víctima tras `CONFIRMA_FRAMES` frames
  seguidos y la sigue por cercanía, para no sumarla en cada frame.
- `logica/deteccion_yolo.py`: misma interfaz que el detector de color; usa
  `modelo/pesos/rescate.pt` si existe o `yolo11n.pt` (COCO) si no.
- Prueba con cámara simulada: una figura naranja durante 8 frames produjo
  `{"0": {"H": 1, "S": 0}}`, es decir, contó una sola vez.
- Pendiente: `logica/iot.py` (falta el protocolo oficial) y validar en cámara
  real.
