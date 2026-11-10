# Código Rescate — CORIOT GAMES 2026

> **DOCUMENTO VIVO.** Este README es la memoria del proyecto entre sesiones y
> entre computadores. **Actualizarlo al final de cada sesión de trabajo**
> (estado, decisiones, problemas y bitácora). Si otra sesión de OpenCode va a
> continuar, debe leer primero este archivo y `Contexto.txt`.

**Última actualización:** 2026-11-09

---

## 1. Qué es el proyecto

Robot autónomo para el reto **Código Rescate** (CORIOT GAMES 2026, 12 de
noviembre de 2026). Debe:

- Detectar visualmente **víctimas** con YOLO11n o por color:
  - **H** = herida → figura **naranja**.
  - **S** = suministros → figura **morado**.
- **Reportar por Wi-Fi/IoT** el JSON que arma el robot, con los conteos H y S
  por cuadrante.
- **Derribar físicamente** cada figura como confirmación (no manipularla).
- Todo el cómputo es autónomo (a bordo u off-board en red privada).

El reglamento completo y las medidas del robot están en `Contexto.txt`.

### Arquitectura de cómputo (decisión)

La **laptop detecta y reenvía; no cuenta, no calcula cuadrantes y no arma el
JSON**. El **robot** navega, escanea, lleva el conteo y decide el derribo.

```
[Cámara del celular (IP Webcam)]
        │ video por Wi-Fi privada
        ▼
[Laptop: detector → filtro vertical → línea de visión]
        │  coriot/vision/E01  (qos 0)
        ▼
[Robot: navega, escanea, cuenta y decide el derribo]
        │  coriot/robot/E01/reporte  (qos 1)
        ▼
[Laptop: reenvía al servidor y espera PUBACK]
        │  coriot/reporte  (qos 1, tema TODO)
        ▼
[Servidor de la competencia]
        │  PUBACK
        ▼
[Laptop: ACK al robot] ──▶ [Robot: derriba]
```

La laptop hace solo cuatro cosas:

1. Detecta H y S con la cámara del celular y envía la línea de visión al robot.
2. Recibe el reporte del robot y lo reenvía tal cual al servidor.
3. Responde el ACK al robot **solo después** del PUBACK del servidor.
4. Muestra el video y el último reporte en pantalla.

Esto es válido porque el reglamento permite **cómputo off-board** en una
laptop conectada por red inalámbrica privada (ver `Contexto.txt`, sección 1).
Las decisiones D1–D12 están en `CONTEXTO_OPENCODE_v2.md` §3 y en
`decisiones_tecnicas.md`.

---

## 2. Estado actual

| Área | Estado |
|---|---|
| Python / entorno virtual | ✅ Python **3.12.10** en `.venv/` |
| Librerías | ✅ ultralytics **8.4.192**, opencv **5.0.0**, torch **2.15.0+cpu**, paho-mqtt **2.1.0** |
| Verificación del entorno | ✅ `modelo/verificar_entorno.py` ejecuta una inferencia real |
| Estructura de carpetas | ✅ `modelo/`, `stream/`, `logica/`, `config.py`, `main.py` |
| Dataset | ⬜ **Vacío a propósito** (vaciado el 2026-11-07). Se captura en la sesión de práctica |
| `rescate.yaml` | ✅ Listo y portable (sin ruta absoluta) |
| Entrenamiento | ✅ `modelo/entrenar.py` probado (1 época). Falta entrenar de verdad con el dataset real |
| Evaluación | ✅ `modelo/evaluar.py` probado; imprime mAP y P/R por clase |
| Detección por color | ✅ `logica/deteccion_color.py` (prueba sintética OK) |
| Calibración de color | ✅ Inicial con IP Webcam (recalibrar en el evento) |
| Stream de video | ✅ `stream/recibir.py` (IP Webcam en hilo, frames recientes) |
| Cuadrante y conteo | ✅ En el robot (TCS34725 + firmware); la laptop no los calcula |
| Flujo en `main.py` | ✅ cámara → detección → filtro → visión MQTT; reporte → servidor → PUBACK → ACK |
| IoT | 🔄 MQTT implementado (`logica/iot.py`, `logica/robot_mqtt.py`); falta confirmar host, puerto y tema |
| Tests | ✅ 47 pruebas `unittest` (sin red ni broker) |
| Simulador | ✅ `tools/simular_robot.py` (sin hardware) |
| Git | ✅ Conectado a `github.com/William-PP/Codigo_Coriot` |

> Ojo: el modelo base `yolo11n.pt` está entrenado con COCO (80 clases:
> `person`, `bus`, etc.). **Todavía no conoce H ni S**; eso requiere entrenar
> con el dataset propio.

---

## 3. Estructura del proyecto

```
Codigo_Coriot/
├── Contexto.txt              # Reglamento y requisitos del reto
├── Requirements.txt          # Dependencias (ultralytics, opencv-python, paho-mqtt)
├── README.md                 # Este documento (mantener actualizado)
├── config.py                 # Rutas, clases, umbrales, IDs y temas MQTT
├── main.py                   # Orquesta: cámara → visión → robot; sin conteo local
├── ACTUALIZACION_CONTEXTO_OPENCODE.md
├── CONTEXTO_OPENCODE_v2.md
├── decisiones_tecnicas.md    # Decisiones y contradicciones detectadas
├── firmware/                 # Referencia del robot ESP32 (no se modifica)
├── modelo/
│   ├── verificar_entorno.py  # Diagnóstico: versiones + inferencia de prueba
│   ├── rescate.yaml          # Dataset y clases para YOLO
│   ├── entrenar.py           # Entrena YOLO11n → modelo/pesos/rescate.pt
│   ├── evaluar.py            # mAP50, mAP50-95 y P/R por clase sobre val
│   ├── revisar_dataset.py    # Detecta y quita etiquetas dudosas
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
├── logica/
│   ├── deteccion_color.py    # Detector HSV (H naranja, S morado)
│   ├── deteccion_yolo.py     # Detector YOLO (misma interfaz que el de color)
│   ├── filtros.py            # Solo cajas verticales (figura de pie)
│   ├── vision_robot.py       # Detecciones → línea D,v,c,x,w,h,conf
│   ├── robot_mqtt.py         # Reporte → servidor → PUBACK → ACK
│   ├── iot.py                # Cliente MQTT único de la laptop
│   ├── calibrar_color.py     # Ajuste en vivo de los rangos HSV
│   └── probar_en_vivo.py     # Prueba el detector con cajas
├── tests/
│   ├── test_vision_robot.py
│   ├── test_filtros.py
│   ├── test_enlace.py
│   └── test_simulador.py
└── tools/
    └── simular_robot.py      # Simulador del robot para probar sin hardware
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

### Dependencias del firmware (ESP32)

El firmware usa únicamente librerías del core ESP32 y una externa:

- **Core ESP32** (`esp32:esp32`): `Wire`, `WiFi`, `Preferences`, `math.h`,
  `esp_task_wdt.h`, `Arduino.h`.
- **PubSubClient** (MQTT): `#include <PubSubClient.h>`.

Compilación con Arduino CLI (la carpeta y el `.ino` deben tener el mismo nombre):

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware\firmware_robot_v3_7_esp32
```

Estructura por sketch (Arduino CLI exige que el nombre de la carpeta coincida
con el del archivo `.ino`):

```
firmware/
└── firmware_robot_v3_7_esp32/
    └── firmware_robot_v3_7_esp32.ino
```

Instalación del core y la librería (si faltan):

```powershell
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install PubSubClient
```

---

## 5. Calibración de color (IP Webcam)

La detección por color necesita ajustar los rangos HSV a la luz y a las figuras
reales. Para desarrollo se usa un celular con **IP Webcam** como cámara.

### Preparar el celular

1. Instalar **IP Webcam** y conectar celular y laptop a la misma red Wi-Fi.
2. Pulsar “Start server” y copiar la URL (ej. `http://192.168.80.145:8080`).
3. En los ajustes de la app, bajar la resolución a **640×480** para reducir
   latencia.
4. Elegir la fuente de video sin editar código con la variable de entorno
   `CORIOT_VIDEO` (o cambiar `FUENTE_VIDEO_DEFECTO` en `config.py`):

   ```powershell
   $env:CORIOT_VIDEO = "http://192.168.80.145:8080/video"
   ```

   Valor por defecto actual: `http://192.168.80.145:8080/video`.
   Usa `"0"` para la webcam de la laptop.

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

Valores actuales en `config.py` (recalibrar con la luz del evento):

```python
RANGOS_HSV = {
    "H": ((0, 111, 80), (25, 255, 255)),    # naranja
    "S": ((125, 80, 60), (160, 255, 255)),  # morado
}
```

`AREA_MIN = 300` y `CONF_MIN = 0.25` completan el detector de color.

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

> Los pasos para ejecutar el flujo completo y los temas MQTT están en §8.

---

## 6. Ruta YOLO: captura, entrenamiento y evaluación

Herramienta de **preparación**, no del runtime de competencia: sirve para
construir el dataset en casa y, sobre todo, en la sesión de práctica del evento.

> **El dataset está vacío a propósito** desde el 2026-11-07. Las carpetas
> existen y están listas; solo faltan las fotos. No hace falta crear nada:
> `stream/capturar.py` las llena solo.
>
> Respaldo de las fotos de prueba (antes de vaciar):
> `%TEMP%\opencode\dataset_respaldo_20261029.zip`. No forma parte del repo.

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

### Limpiar las etiquetas (`modelo/revisar_dataset.py`)

Las etiquetas de `stream/capturar.py` son automáticas: el detector de color a
veces enmarca un borde, dos objetos o píxeles sueltos. Antes de entrenar
conviene revisarlas:

```powershell
python -m modelo.revisar_dataset            # solo informa
python -m modelo.revisar_dataset --borrar   # aplica los cambios
```

Una caja se descarta si cumple cualquiera de estas condiciones:

| Problema | Regla | Por qué |
|---|---|---|
| `horizontal` | alto/ancho < 0.35 | Una figura de pie nunca es tan plana: es una cinta, un borde o la figura derribada |
| `color disperso` | menos del 45 % de píxeles del color dentro de la caja | La caja envuelve píxeles sueltos, no un objeto |
| `duplicada` | dos cajas de la misma clase se solapan más de 0.50 | La misma víctima anotada dos veces |
| `clase o formato inválido` | clase fuera de `0`/`1` o línea rota | Ultralytics no lo puede leer |

Si una imagen se queda **sin** cajas buenas se borra entera. Dejarla como
negativa sería peor: enseñaría que ahí no hay víctima cuando sí la hay.

> Ojo: que una caja tenga alto/ancho ~1 **no** la vuelve mala. El objeto de
> prueba morado es casi cuadrado y sus etiquetas son correctas. `ASPECTO_MIN`
> es un filtro del **runtime** para las figuras reales, no una regla de
> etiquetado.

### Entrenar (`modelo/entrenar.py`)

```powershell
python -m modelo.entrenar
```

Toma `modelo/pesos/yolo11n.pt` (entrenado con COCO, no conoce H ni S), lo
ajusta con las imágenes de `dataset/images/train` y sus etiquetas, y guarda el
resultado en **`modelo/pesos/rescate.pt`**.

| Opción | Por defecto | Para qué |
|---|---|---|
| `--epocas` | `config.EPOCAS` (50) | Vueltas completas al dataset |
| `--lote` | `config.LOTE` (8) | Imágenes por paso; bajar si falta memoria |
| `--imgsz` | `config.TAMANO_IMG` (640) | Resolución de entrenamiento |
| `--desde` | `yolo11n.pt` | Pesos iniciales (útil para seguir entrenando) |

Se detiene solo si pasan `PACIENCIA` (15) épocas sin mejorar. Los resultados
crudos quedan en `modelo/runs/entrenar/` (ignorado en Git).

> En CPU y con 36 imágenes, entrenar de verdad tarda y da métricas malas: es
> normal. El objetivo hoy es que el script funcione; el valor real aparece con
> el dataset de las figuras reales.

### Evaluar (`modelo/evaluar.py`)

```powershell
python -m modelo.evaluar
```

Pasa `rescate.pt` por las imágenes de `dataset/images/val` (que el modelo **no**
vio al entrenar) e imprime:

| Métrica | Qué significa |
|---|---|
| `mAP50` | Qué tan bien encuentra y clasifica; más alto, mejor |
| `mAP50-95` | Igual, pero exigiendo cajas más precisas |
| precisión | De lo que dijo “hay víctima”, cuánto era verdad |
| recall | De las víctimas reales, cuántas encontró |

Regla práctica: `mAP50 > 0.70` → vale la pena `MODO_DETECCION = "yolo"`;
`< 0.40` → quedarse con el detector de color.

> Los pasos de ejecución y los topics MQTT están en §8. Para probar sin
> hardware, usa el simulador de §9.

---

## 7. Cuadrante y conteo (en el robot)

La laptop **no** calcula el cuadrante ni cuenta víctimas. Esas funciones son del
robot, según D5, D8, D9, D10, D11 y D12:

- **Cuadrante:** TCS34725 por I2C en el robot. Lee el color del piso y detecta
  el borde negro (D10: borde **activo**; lo prohibido es la línea guía interior).
- **Conteo:** el robot cuenta H y S por cuadrante y solo confirma un derribo
  después del ACK de la laptop.
- **Escaneo:** 24 X (6 por cuadrante), no 16.
- **Navegación:** reactiva con 3 HC-SR04; sin mapa fijo de obstáculos.

La calibración del TCS34725 se hace en el robot/firmware, **no con la cámara de
la laptop**. Los colores del piso del auditorio se ajustan en la pista.

En T8 se retiraron los módulos de cámara que hacían este trabajo en la laptop:
cuadrante por color de piso, calibración de piso y conteo por frames. Ya no
forman parte del flujo ni se ejecutan con `python -m`.

Pendiente (solo lo confirma la organización): coordenadas exactas de las 24 X y
nombres de los cuadrantes en el servidor. No se inventan valores.

---

## 8. Decisiones, ejecución y MQTT

- **Laptop = detección y reenvío**: toda la visión corre en la laptop; el robot
  navega, escanea, cuenta y decide el derribo.
- **Robot = navegación, conteo y derribo**: no procesa imágenes; arma el JSON y
  lo publica en el tema privado del robot.
- **Sin ACK no hay derribo**: la laptop solo confirma después del PUBACK del
  servidor (qos 1).
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
- Umbrales por defecto: confianza `0.25`, IoU `0.45`, `ASPECTO_MIN = 1.2`.
- Dataset: ~80 % `train`, ~20 % `val`; incluir escenas sin víctimas (etiqueta
  vacía) para reducir falsos positivos.
- **El robot arma el JSON**; la laptop lo reenvía tal cual. El formato oficial
  del servidor está pendiente (TODO); `formatear_para_servidor()` es el punto
  de conversión.
- **Detector intercambiable**: `config.MODO_DETECCION` = `"color"` (rápido, sin
  entrenar) o `"yolo"` (usa `modelo/pesos/rescate.pt` si existe). Ambos
  devuelven el mismo formato, así que `main.py` no cambia.
- **Solo cajas verticales**: `logica/filtros.py` descarta las detecciones donde
  el alto no llega a `ASPECTO_MIN` (1.2) veces el ancho. Una figura derribada
  queda horizontal y ya no se cuenta como víctima nueva. Se aplica en
  `main.py` y en `stream/capturar.py` (para no etiquetar figuras caídas).

### Ejecución

```powershell
python main.py
```

Flujo real de `main.py`:

1. Abre la cámara (`stream/recibir.py`) y reintenta si falla.
2. Detecta H y S con `config.MODO_DETECCION`.
3. Aplica `solo_verticales()` (figura de pie).
4. Arma la línea de visión y la envía al robot por `coriot/vision/E01`
   (qos 0, máximo 15 Hz).
5. El robot publica su reporte en `coriot/robot/E01/reporte`.
6. `EnlaceRobot` lo reenvía a `coriot/reporte` (qos 1) y espera PUBACK.
7. Solo tras el PUBACK responde `coriot/robot/E01/ack` (qos 0).
8. Muestra el video y el último reporte; `q` sale.

> `main.py` no cuenta, no calcula cuadrantes y no decide derribos.

### Reporte JSON del robot (propuesto)

```json
{
  "equipo": "E01",
  "intento": "SIM",
  "secuencia": 1,
  "estado": "en_curso",
  "cuadrantes": [
    {
      "color": "rojo",
      "explorado": true,
      "heridos": 0,
      "necesitan_suministros": 0
    }
  ]
}
```

- `equipo`: `config.ROBOT_ID`.
- `secuencia`: sube con cada reporte nuevo; los reintentos repiten la misma.
- `cuadrantes`: lista; cada cuadrante trae `color`, `explorado`, `heridos` y
  `necesitan_suministros`.
- El formato definitivo depende del servidor de la competencia: **TODO**.
  `formatear_para_servidor()` en `logica/robot_mqtt.py` es donde se ajustará.

### Topics MQTT (valores de `config.py`)

| Variable | Valor actual | Dirección |
|---|---|---|
| `ROBOT_ID` | `E01` | Identificador del robot |
| `TEMA_VISION` | `coriot/vision/E01` | laptop → robot (qos 0) |
| `TEMA_REPORTE_ROBOT` | `coriot/robot/E01/reporte` | robot → laptop (qos 1) |
| `TEMA_ACK_ROBOT` | `coriot/robot/E01/ack` | laptop → robot (qos 0) |
| `SERVIDOR_TEMA` | `coriot/reporte` | laptop → servidor (**TODO**) |
| `BROKER_CLIENTE` | `laptop-E01` | ID único del cliente |

### Broker MQTT

| Variable | Valor actual | Qué es |
|---|---|---|
| `BROKER_HOST` | `127.0.0.1` | IP del broker (**TODO: confirmar**) |
| `BROKER_PORT` | `1883` | Puerto MQTT |
| `BROKER_USUARIO` / `BROKER_PASSWORD` | vacío | Credenciales, si el broker las pide |

Comportamiento de `logica/iot.py`:

- Un solo cliente (`laptop-E01`) para visión, reportes, servidor y ACK.
- Visión y ACK con `qos=0`: no esperan red ni bloquean la visión.
- Reporte al servidor con `qos=1`: espera PUBACK hasta 5 s y solo devuelve
  `True` si el broker confirmó.
- Sin conexión no se encolan mensajes con qos > 0: un reporte viejo no debe
  salir después de haber decidido no enviar ACK.
- Reconexión automática; las suscripciones se renuevan al reconectar.

### Probar sin broker

El simulador del robot y la suite de tests funcionan sin red:

```powershell
python tools/simular_robot.py --duracion 30
python -m unittest discover -s tests -v
```

Para una prueba real de MQTT hace falta un broker local (Mosquitto o similar):
apunta `BROKER_HOST` a su IP y suscríbete a los temas con un visor MQTT.

---

## 9. Hoja de ruta (checklist)

- [x] Instalar Python 3.12 y crear `.venv`
- [x] Instalar ultralytics + opencv + paho-mqtt
- [x] Crear estructura de carpetas
- [x] `config.py` con IDs, temas y umbrales v2
- [x] `modelo/verificar_entorno.py` funcionando
- [x] `modelo/rescate.yaml` portable
- [x] Conectar repositorio Git
- [x] `logica/deteccion_color.py` (HSV naranja/morado)
- [x] Calibrar rangos HSV iniciales con cámara real (recalibrar en evento)
- [ ] Capturar fotos de las figuras H y S (desde la cámara del robot)
- [ ] Etiquetar el dataset (Roboflow / CVAT / LabelImg)
- [x] `modelo/revisar_dataset.py` y limpieza del dataset de prueba
- [x] `modelo/entrenar.py` (YOLO11n; probado con 1 época)
- [x] `modelo/evaluar.py` (mAP50, mAP50-95, precisión/recall por clase)
- [x] `stream/recibir.py` (IP Webcam en hilo, frames recientes)
- [x] `stream/capturar.py` (dataset con etiquetas automáticas)
- [x] `logica/filtros.py` (solo cajas verticales)
- [x] `logica/vision_robot.py` (línea `D,v,c,x,w,h,conf`)
- [x] `logica/iot.py` (cliente MQTT único; qos 1 con PUBACK)
- [x] `logica/robot_mqtt.py` (reporte → servidor → PUBACK → ACK)
- [x] `main.py` v2 (cámara → visión → robot; sin conteo local)
- [x] `tools/simular_robot.py` (simulador sin hardware)
- [x] `tests/` con `unittest` (47 tests, sin red)
- [x] T8: retirar los módulos de cámara de cuadrante, calibración de piso y
      conteo por frames (eliminados)
- [ ] Confirmar con la organización `BROKER_HOST`, `BROKER_PORT`,
      `SERVIDOR_TEMA` y el formato oficial del JSON
- [ ] Cuadrante y conteo en el robot (TCS34725 + firmware)
- [ ] Medir las coordenadas exactas de las 24 X en la pista
- [ ] Pruebas en pista real y calibración de umbrales
- [ ] (Opcional) Docker para reproducibilidad

### Día del evento (2026-11-12)

**9.1 Inspección técnica**

- [ ] Medidas ≤ 13 × 18 × 20 cm e interruptor de apagado accesible.
- [ ] Prueba de transmisión IoT: confirmar **broker, puerto y temas** reales y
      dejarlos en `config.py`.
- [ ] Probar `python main.py` sin celular: el robot debe arrancar y mostrar el
      video aunque el broker no responda.

**9.2 Sesión de práctica en pista (lo más importante)**

1. [ ] **Recalibrar HSV** con la luz del auditorio (los valores de casa no
       sirven): `python -m logica.calibrar_color H` y `S`.
2. [ ] Ajustar `ASPECTO_MIN` con la figura real: de pie se cuenta, acostada no.
3. [ ] Cuadrante en el robot: calibrar el TCS34725 en pista (no con la cámara
       de la laptop) y confirmar el borde negro.
4. [ ] Capturar dataset con las figuras reales: `python -m stream.capturar`.
5. [ ] Revisar etiquetas y, si el tiempo alcanza, entrenar y evaluar:
       `python -m modelo.entrenar` → `python -m modelo.evaluar`.
6. [ ] Solo si `mAP50 > 0.70`: `MODO_DETECCION = "yolo"` y volver a probar.

**Intento oficial**

- [ ] Un solo comando (`python main.py`), sin tocar código ni ventanas extra.
- [ ] Verificar que el robot reporta y que el ACK llega solo tras el PUBACK.

---

## 10. Cómo continuar en otra sesión de OpenCode

1. Leer `README.md`, `Contexto.txt`, `ACTUALIZACION_CONTEXTO_OPENCODE.md` y
   `CONTEXTO_OPENCODE_v2.md`.
2. `git pull` para traer los últimos cambios.
3. Activar `.venv` y confirmar versiones con `modelo/verificar_entorno.py`.
4. Revisar la sección **Estado actual** y la **bitácora** antes de tocar código.
5. Comandos de verificación:

   ```powershell
   # Tests (sin red, 47 pruebas)
   python -m unittest discover -s tests -v

   # Simulador del robot (sin hardware)
   python tools/simular_robot.py --duracion 30

   # Comprobar que todo compila
   python -m py_compile main.py config.py logica/*.py tools/simular_robot.py
   ```

   > En PowerShell, `logica/*.py` no se expande para comandos nativos. Usa
   > `Get-ChildItem logica\*.py | ForEach-Object { $_.FullName }` o pasa los
   > archivos uno por uno.

6. Trabajar **un paso a la vez**, explicando los comandos (el usuario prefiere
   ejecutarlos él para aprender).
7. Al terminar la sesión: actualizar **Estado actual**, **Hoja de ruta** y
   **Bitácora** de este README, y `decisiones_tecnicas.md`.

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
- **Piso sin color**: el TCS34725 del robot rechaza superficies grises, blancas
  o negras sin tono; no se inventa un cuadrante. La calibración se hace en el
  robot, no con la cámara de la laptop.
- **Colores vecinos**: cyan se confunde con azul y un piso muy claro con blanco.
  Conviene que los 4 cuadrantes tengan tonos bien separados; calibrar el sensor
  con buena luz en la pista.
- **Cuadrante y conteo son del robot**: la laptop no los calcula. Si el robot no
  reporta un cuadrante explorado, el JSON lo muestra como sin explorar; no es
  un error de la laptop.
- **Doble conteo**: lo evita el robot confirmando el derribo físico; la laptop
  no lleva cuentas.
- **Filtro de verticalidad**: con `ASPECTO_MIN = 1.2`, una figura de pie que se
  vea casi cuadrada (por el ángulo de la cámara) quedaría **descartada**. Si las
  figuras reales son anchas, bajar a 1.0–1.1; si se cuelan derribadas, subir.
  Verificarlo con la figura real antes de competir.
- `logica/probar_en_vivo.py` muestra las detecciones **sin** el filtro (sirve
  para depurar); `main.py` sí lo aplica.
- **MQTT caído no detiene la visión**: si el broker no responde, `main.py` sigue
  detectando y enviando líneas de visión. Los mensajes con qos > 0 no se
  encolan y no sale ACK sin PUBACK; el robot no derriba. Revisar la consola:
  muestra `MQTT: conectado…` cuando logra enlazar.
- **`BROKER_CLIENTE` debe ser único**: dos equipos con el mismo ID se expulsan
  mutuamente del broker. Cambiarlo si hay varias laptops probando a la vez.
- **Datos del broker provisionales**: `BROKER_HOST` y `SERVIDOR_TEMA` deben
  confirmarse con la organización; `coriot/reporte` es un TODO.
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
- Ultralytics escribe en `runs/` por defecto; `entrenar.py` y `evaluar.py` ya
  fijan `project="modelo/runs"`.
- **Entrenar en CPU es lento**: para comprobar que el script funciona usar
  `python -m modelo.entrenar --epocas 1 --lote 4 --imgsz 320` (segundos). Un
  entrenamiento real con 640 px puede tardar horas.
- **Un modelo de 1 época “alucina”**: en un frame negro inventó 19 cajas H.
  Nunca activar `MODO_DETECCION = "yolo"` con pesos de prueba; se borraron los
  de la prueba de humo. Entrenar de verdad antes.
- Ultralytics crea `*.cache` en `dataset/labels/`; se regeneran solos y están
  ignorados en Git. No son un error.
- **Etiquetas automáticas**: el detector de color se equivoca. Antes de entrenar
  pasar `python -m modelo.revisar_dataset`; si hay etiquetas dudosas, el modelo
  aprende el error y las métricas no significan nada.
- **Pocas negativas en `train` y muchas en `val`**: al 2026-10-29, `val` tiene
  12 negativas de 18. Con tan pocos positivos las métricas saltan mucho;
  conviene más variedad de figuras antes de creerles.

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
- Se definió que la **laptop** procesa la visión; el microcontrolador solo
  actuaba sobre motores y derribo (cómputo off-board). Desde T1–T9 el robot
  también navega, cuenta y decide el derribo.

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

### 2026-10-29 — Cuadrante por color de piso (prototipo retirado)

- Se creó un prototipo que leía el color de la franja inferior del frame, lo
  promediaba en HSV (tono circular, ponderado por saturación) y lo comparaba
  con colores calibrados para devolver el número de cuadrante.
- Se creó un calibrador de piso por cámara: teclas `1`–`4` guardaban el color
  de cada cuadrante, `r` borraba, `q` salía.
- Prueba sintética con verde/azul/amarillo/rojo: acertaba los 4 con distancia 0
  y seguía acertando con la luz al 60 % (distancia < 0.05).
- Se corrigió un fallo: un piso gris se clasificaba como rojo (el gris no tiene
  tono). Ahora se rechaza y devuelve cuadrante `0`.
- **Retirado en T8**: la arquitectura v2 (D5/D8) movió el cuadrante al robot con
  un TCS34725 por I2C. El prototipo de cámara ya no forma parte del flujo.

### 2026-10-29 — Flujo completo en main.py
- Se confirmó en el reglamento que **el JSON no tiene que salir del
  microcontrolador**: basta con que el sistema lo transmita y el cómputo
  off-board está permitido. Se envía desde la laptop.
- `main.py` quedó operativo: stream → detección → cuadrante (desactivado) →
  conteo → JSON impreso. `config.MODO_DETECCION` elige `"color"` o `"yolo"`.
- El conteo en la laptop (retirado en T8) contaba una víctima tras varios
  frames seguidos y la seguía por cercanía, para no sumarla en cada frame.
- `logica/deteccion_yolo.py`: misma interfaz que el detector de color; usa
  `modelo/pesos/rescate.pt` si existe o `yolo11n.pt` (COCO) si no.
- Prueba con cámara simulada: una figura naranja durante 8 frames produjo
  `{"0": {"H": 1, "S": 0}}`, es decir, contó una sola vez.
- Pendiente: `logica/iot.py` (falta el protocolo oficial) y validar en cámara
  real.
- Este flujo se reemplazó en T1–T9 por la arquitectura v2: la laptop detecta y
  reenvía; el robot cuenta y decide el derribo.

### 2026-10-29 — Solo víctimas verticales
- Se agregó `logica/filtros.py`: una detección solo cuenta si el alto es al
  menos `ASPECTO_MIN` (1.2) veces el ancho, es decir, figura **de pie**.
- Las figuras derribadas (horizontales) se descartan, evitando contarlas de
  nuevo después del derribo.
- Se aplica en `main.py` y en `stream/capturar.py`; `probar_en_vivo.py` queda
  sin filtro para diagnóstico.
- Prueba: caja 80×120 cuenta; 120×80, 100×100 y 140×122 no. Flujo completo con
  cámara simulada: solo la vertical produjo `H=1`.
- Pendiente: confirmar el umbral con la figura real (el ángulo de la cámara
  puede hacer que una figura de pie se vea casi cuadrada).
- **Validado con cámara real (IP Webcam)**: al acostar la figura, deja de
  contar. Con `ASPECTO_MIN = 1.2` la figura de pie sí se cuenta.

### 2026-10-29 — Envío MQTT
- El protocolo oficial es **MQTT**. Se agregó `paho-mqtt>=2.0` a
  `Requirements.txt` y se instaló `paho-mqtt 2.1.0`.
- `logica/iot.py` publica el JSON con `qos=1`, sin `retain`, usando
  `connect_async` + `loop_start` (hilo aparte, no bloquea la visión).
- Se publica solo cuando cambia el conteo; el reporte final se manda únicamente
  si cambió, para no duplicar el mismo JSON.
- Pruebas con un broker local de prueba: 2 mensajes publicados y recibidos por
  un suscriptor; con el flujo completo de `main.py` llegó **1** mensaje (sin
  duplicados). Sin broker, `main.py` sigue funcionando y no se cae.
- Se corrigieron dos fallos: el aviso imprimía “no se pudo conectar (Success)”
  por comparar mal el `ReasonCode` de paho 2.x, y `cerrar()` lanzaba
  `RuntimeError` si el mensaje se había encolado antes de conectar.
- Broker y tema son **provisionales** (`127.0.0.1`; hoy `config.py` usa
  `coriot/reporte`): hay que confirmarlos con la organización.

### 2026-10-29 — Entrenamiento y evaluación de YOLO
- Se agregó `modelo/entrenar.py`: parte de `modelo/pesos/yolo11n.pt`, entrena
  con `rescate.yaml`, guarda en `modelo/runs/entrenar/` y copia el mejor modelo
  a `modelo/pesos/rescate.pt`. Acepta `--epocas`, `--lote`, `--imgsz`, `--desde`.
- Se agregó `modelo/evaluar.py`: mide `rescate.pt` sobre `dataset/images/val` e
  imprime mAP50, mAP50-95, precisión y recall **por clase** (H y S).
- Nuevo bloque en `config.py`: `EPOCAS=50`, `LOTE=8`, `TAMANO_IMG=640`,
  `PACIENCIA=15`.
- **Prueba de humo**: `python -m modelo.entrenar --epocas 1 --lote 4 --imgsz 320`
  corrió completo (23 train / 20 val) y generó `rescate.pt`; `evaluar.py` lo
  cargó e imprimió las métricas. Ambos scripts funcionan.
- Las métricas salieron pésimas (mAP50 ≈ 0.001), como se esperaba con 1 época.
  Ese modelo **alucinaba** cajas en un frame negro, así que se borró
  `rescate.pt` y `modelo/runs/` para no activar YOLO por accidente.
- Conclusión: el día del evento solo hay que capturar, entrenar y evaluar; si
  `mAP50` no supera 0.70, se compite con el detector de color.

### 2026-10-29 — Limpieza del dataset
- Se agregó `modelo/revisar_dataset.py`: mide cada caja contra el blob de color
  y descarta las que no sirven (horizontal, color disperso, duplicada, clase o
  formato inválido). Sin `--borrar` solo informa.
- Se borraron 7 imágenes con 9 cajas malas (respaldo en
  `%TEMP%\opencode\dataset_respaldo_20261029.zip`):
  - `train`: `194020_459`, `194021_204` (dos franjas naranjas planas de 218×13
    y 86×15 px), `194028_079` (caja 420×53 con 30 % de color y 20 fragmentos),
    `194034_365`, `194034_867` (objeto naranja acostado, 159×45).
  - `val`: `195204_462` (140×123) y `195211_128` (140×153), con solo 23–25 %
    de color: la caja envolvía píxeles sueltos de un objeto pálido.
- **No** se tocaron las cajas moradas casi cuadradas (22×28 px en train,
  126×104 px en val): son etiquetas correctas de un objeto de prueba cuadrado.
  `ASPECTO_MIN` es un filtro de runtime, no una regla de etiquetado.
- Resultado: train 18 (H=4, S=7, 7 negativas), val 18 (H=3, S=5, 12 negativas).
  `revisar_dataset.py` ya no reporta nada.
- Quedan 2 pares de imágenes casi idénticas (`194004_854`/`194005_432` y
  `194158_071`/`194158_090`): no son un error, solo redundancia; se conservan
  porque el dataset es muy pequeño.
- `val` quedó con 12 negativas de 18: hay que capturar más figuras reales antes
  de darle valor a las métricas.

### 2026-11-07 — Dataset vaciado antes del evento
- Se vació `modelo/dataset/` (imágenes y etiquetas) para llegar limpio a la
  sesión de práctica. Solo quedan los `.gitkeep` y las cuatro carpetas.
- No hay que recrear nada: `stream/capturar.py` crea los archivos que falten.
- Con el dataset vacío, `python -m modelo.evaluar` avisa “no existe rescate.pt”
  y `python -m modelo.entrenar` se detiene con “no hay imágenes en train”.
  Es el comportamiento esperado, no un error.
- Respaldo de las 43 fotos de prueba: `%TEMP%\opencode\dataset_respaldo_20261029.zip`.

### 2026-11-09 — Arquitectura v2, tests y limpieza (T1–T9)

- La laptop quedó como **detector y reenvío**: cámara → detector → filtro
  vertical → línea de visión MQTT; reporte del robot → servidor → PUBACK → ACK.
- Topics en `config.py`: `coriot/vision/E01`, `coriot/robot/E01/reporte`,
  `coriot/robot/E01/ack`; servidor `coriot/reporte` (TODO).
- `logica/robot_mqtt.py`: el ACK sale solo tras el PUBACK; sin PUBACK no hay ACK
  y el robot no derriba.
- `tools/simular_robot.py`: simulador sin hardware.
- `tests/`: 47 pruebas con `unittest`, sin red, en ~2,5 s.
- T8: se retiraron los módulos de cámara de cuadrante, calibración de piso y
  conteo por frames; esa lógica vive ahora en el robot.
- T9: README actualizado; quedan como TODO los datos del servidor y las
  coordenadas de las 24 X.
