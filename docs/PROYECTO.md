# Código Rescate — CORIOT GAMES 2026

**Evento:** 12 de noviembre de 2026, Auditorio Pedro Nel Gómez, Campus Robledo (ITM).
**Repositorio:** `github.com/William-PP/Codigo_Coriot`
**Última actualización:** 2026-11-10

Robot autónomo que explora una pista de 2 × 2 m, clasifica víctimas **H** (heridas, naranja) y **S** (necesitan suministros, morado), reporta los conteos por cuadrante por MQTT y derriba cada figura como confirmación física.

---

## 0. Cómo usar este documento

Este es el único documento de referencia. Léelo completo antes de cualquier tarea.

- Si un dato no está aquí ni en el código, no se inventa: se escribe como **TODO** con un dueño en la sección 9.
- Si dos fuentes se contradicen, se usa la más reciente y la contradicción se registra en la sección 5.
- El código es la referencia del comportamiento real; este documento explica el estado esperado y el porqué.
- Al terminar una sesión de trabajo se actualiza la sección 1 y se agrega una línea a la bitácora (sección 10).

---

## 1. Estado actual

| Área | Estado | ¿Bloquea la competencia? |
|---|---|---|
| Laptop: `main.py`, visión, filtro vertical, MQTT y ACK | Implementada y probada con cámara, detector y enlace simulados; falta la prueba con broker real | No por sí sola; depende de los datos del servidor |
| GUI de 3 pestañas | Implementada; entrenamiento en segundo plano y captura por sesiones | No |
| Pruebas automáticas | Suite `unittest` en verde, sin red ni broker | No |
| Firmware v3.7 | Archivo y carpeta presentes; no se compiló en esta sesión porque `arduino-cli` no está instalado | **Sí:** falta compilarlo y probarlo en el robot |
| Modelo YOLO | `yolo11n.pt` presente; `rescate.pt` ausente; dataset vacío | **Sí:** sin `rescate.pt` el modo `yolo` no arranca |
| Datos del servidor MQTT | Host, puerto, tema, credenciales y esquema JSON sin confirmar | **Sí:** sin ellos no hay ACK ni derribo |
| Coordenadas de las 24 X | Sin medir; el firmware usa posiciones provisionales | No impide reportar; limita la cobertura completa |
| Documentación | Consolidada en este archivo | No |

Los bloqueos reales son los marcados con **Sí** en la última columna.

---

## 2. Reglamento resumido

### 2.1 Pista y objetos

| Elemento | Especificación |
|---|---|
| Área | 2,00 m × 2,00 m, plana |
| Cuadrantes | 4 de 1,00 m × 1,00 m: rojo y azul arriba; verde y amarillo abajo |
| Límite | Borde negro bajo y visible |
| Inicio | Rectángulo **START** en la esquina inferior izquierda del cuadrante verde; centro inicial (100, 100) mm |
| Edificios | 12 obstáculos de ~15 cm de lado y 20 cm de alto; su posición depende del montaje y es igual para todos los equipos de la ronda |
| Posiciones de víctimas | 24 X, 6 por cuadrante |
| Víctimas por intento | 12, 3 por cuadrante |
| Combinaciones | X negras (combinación 1) y X blancas (combinación 2); clases H/S sorteadas antes de cada ronda |

Centros aproximados de cuadrante, en mm con origen en la esquina inferior izquierda: verde (500, 500), amarillo (1500, 500), rojo (500, 1500), azul (1500, 1500).

**Obligación de código:** el cuadrante se reconoce por el color del piso, no por una posición preprogramada. El centro geométrico del robot decide en qué zona está.

### 2.2 Robot, IA y conteo

| Regla | Consecuencia para el código |
|---|---|
| Un robot terrestre, alimentación propia | Un solo equipo compite |
| Medidas máximas | 13 cm de ancho × 18 cm de largo × 20 cm de alto, con partes desplegadas |
| Cómputo | A bordo o en un computador local previamente registrado; no se permiten cámaras externas, observadores ni órdenes manuales |
| Clasificación H/S | Debe salir de un modelo de aprendizaje automático entrenado o adaptado; se permiten modelos preentrenados y bibliotecas |
| Verificación de IA | En la inspección se muestran el modelo, sus entradas y salidas, y un registro de inferencias; el juez puede pedir una demostración |
| Conteo | Cada figura física se cuenta una sola vez, aunque aparezca en varios fotogramas |
| Asignación | La víctima pertenece al color del piso donde está su base, no al cuadrante desde donde la observa la cámara |
| Zona puntuable | Para puntuar, el robot debe visitar la zona y reconocer su color |
| Cero y desconocido | `0` significa zona explorada sin víctimas de esa clase; una zona sin explorar se reporta como desconocida (`null`) |

No se usan códigos QR ni identificadores que revelen la clase. Tampoco se codifican cantidades o posiciones del montaje oficial.

### 2.3 Reporte IoT y JSON

El servidor de la organización es la evidencia oficial. El robot publica por MQTT; no se aceptan capturas de pantalla ni envíos manuales.

| Campo | Contenido requerido |
|---|---|
| `equipo` | Identificador del equipo registrado |
| `intento` | Identificador habilitado por el juez |
| `secuencia` | Entero creciente; una retransmisión conserva el mismo número |
| `estado` | `en_curso` o `final` |
| `cuadrantes` | Lista con los cuatro colores, sin repetir |
| `color` | `rojo`, `azul`, `verde` o `amarillo` |
| `explorado` | `true` o `false` |
| `heridos` | Entero ≥ 0 si `explorado=true`; `null` si es `false` |
| `necesitan_suministros` | Entero ≥ 0 si `explorado=true`; `null` si es `false` |

Reglas de actualización:

- Como máximo **1 mensaje por segundo**.
- Los valores son **acumulados actuales** por zona: un reporte nuevo reemplaza al anterior; el servidor no suma mensajes ni fotogramas.
- Una secuencia ya recibida se reconoce como duplicada.
- El intento cierra con el primer mensaje válido con `estado: "final"`, al cumplirse el tiempo o por detención de seguridad.
- Se evalúa el **último reporte completo válido** recibido antes del cierre. El puntaje del equipo es el mejor de sus intentos, no la suma.

### 2.4 Derribo de validación

- Primero se publica el conteo actualizado del cuadrante; **después** se derriba la figura.
- Un derribo previo al reporte no cuenta como confirmación.
- Cada víctima contabilizada en el reporte evaluado debe tener su derribo, verificado por el juez.
- Derribar una víctima no reportada, o de clase distinta a la reportada, se penaliza y ese conteo no se valida.
- Derribar no es manipular: no se recoge, sujeta ni transporta la figura.

### 2.5 Tiempo, puntaje y penalizaciones

- Cada intento oficial dura **hasta 8 minutos (480 s)**. Incluye exploración, procesamiento y comunicación.
- El intento termina al recibir el primer mensaje válido con estado final, al cumplirse 480 s o por detención de seguridad.
- El robot debe detener sus motores al cerrar. No se exige volver al inicio.

| Componente | Máximo | Asignación |
|---|---:|---|
| Conteo de heridos | 40 | Hasta 10 puntos por cada uno de los 4 cuadrantes |
| Conteo de víctimas que necesitan suministros | 40 | Hasta 10 puntos por cada uno de los 4 cuadrantes |
| Exploración y color | 10 | 2,5 por cuadrante visitado y reconocido correctamente |
| Reporte IoT | 10 | 2,5 por cuadrante explorado con registro válido en el reporte evaluado |
| **Total antes de penalizaciones** | **100** | |

Para cada combinación de cuadrante y clase: conteo exacto = 10 puntos; error de una víctima cuando la cantidad real es mayor que cero = 5 puntos; cualquier otro error = 0 puntos. Si la cantidad real es cero, solo el reporte cero obtiene puntos; `null` o ausente recibe 0.

| Infracción | Consecuencia |
|---|---|
| Desplazar un obstáculo más de 2 cm | −5 puntos por incidente |
| Derribar sin reporte válido previo, o de clase distinta | −5 puntos por incidente; el conteo no se valida |
| Salida del campo | −5 puntos y fin del intento; se conservan los resultados recibidos |
| Intervención humana no autorizada | Intento invalidado, 0 puntos |
| Manipular reportes o precargar respuestas | Descalificación por fraude comprobado |
| Trampa observada por el panel de jueces | Descalificación inmediata |

Un incidente es una interacción continua con un objeto; solo se cuenta otro cuando cesa el contacto y ocurre uno nuevo. Si un hecho corresponde a varias filas, se aplica la consecuencia más severa.

El procedimiento y el cronograma del día están en la sección 8.5.

---

## 3. Arquitectura y flujo

### 3.1 Responsabilidades

**La laptop hace cuatro cosas:**

1. Detecta H y S con la cámara del celular (IP Webcam) y envía la línea de visión al robot.
2. Recibe el reporte del robot y lo reenvía al servidor sin modificarlo.
3. Responde el ACK al robot solo después de que el servidor confirmó el mensaje.
4. Muestra el video, los indicadores y el último reporte en la GUI.

**La laptop NO hace:** navegación, escaneo, conteo, cálculo de cuadrante ni derribo. Tampoco envía órdenes de movimiento, arranque o parada al robot.

**El robot decide y ejecuta:** navegación reactiva, escaneo de 360°, acercamiento, centrado, derribo y verificación. Detecta borde negro, atasco y batería baja. Arma el reporte y lo publica en el tema privado. No derriba sin ACK.

**El broker** reparte los mensajes entre laptop y robot. **El servidor de la organización** recibe el reporte reenviado y es la evidencia oficial.

### 3.2 Temas MQTT

| Tema | Dirección | Contenido | QoS |
|---|---|---|---|
| `coriot/vision/E01` | laptop → robot | Línea de visión | 0 |
| `coriot/robot/E01/reporte` | robot → laptop | JSON del robot | 1 |
| `coriot/robot/E01/ack` | laptop → robot | `{"secuencia": N, "ok": true}` | 0 |
| `coriot/robot/E01/config` | laptop → robot | `{"equipo": "E01", "intento": "I1"}` retenido | 1 |
| `coriot/reporte` | laptop → servidor | JSON reenviado tal cual | 1 |

`coriot/reporte` es un valor provisional marcado **TODO**; el tema oficial lo confirma la organización. El tema de configuración es el que usa el firmware v3.7 para recibir equipo e intento.

### 3.3 Línea de visión

Una línea CSV por frame, sin salto final:

```
D,v,c,x,w,h,conf
```

| Campo | Rango | Significado |
|---|---|---|
| `D` | fijo | Cabecera |
| `v` | 0 o 1 | 1 = figura detectada; 0 = ninguna |
| `c` | `H` o `S` | Clase |
| `x` | 0–1000 | Centro horizontal de la caja; 500 = centro del frame |
| `w` | 0–1000 | Ancho de la caja |
| `h` | 0–1000 | Alto de la caja |
| `conf` | 0–100 | Confianza; YOLO entrega 0–1 y se multiplica por 100 |

Reglas:

- `x`, `w` y `h` usan la misma escala: `factor = 1000 / ancho_frame`; se redondean a entero y se limitan a 0–1000.
- Se envía al menos una línea por frame; sin figura: `D,0,H,500,0,0,0`.
- Si hay H y S en el mismo frame, se envían dos líneas (máximo una por clase).
- La visión se calcula y envía como máximo a **15 Hz**.
- El robot considera que la visión está caída si no recibe líneas en 1 s.

### 3.4 Reporte y ACK

- El robot arma el JSON de la sección 2.3 y lo publica con qos 1. La laptop **no lo modifica**.
- `EnlaceRobot` lo reenvía al servidor con qos 1, espera el PUBACK hasta 5 s y solo entonces publica el ACK.
- Sin PUBACK no hay ACK; sin ACK el robot no derriba.
- Si llega una secuencia ya reenviada con contenido idéntico, se responde el ACK sin volver a publicar en el servidor.
- La deduplicación usa `(secuencia, contenido idéntico)`, no solo el número.
- La cola de reportes tiene capacidad para 100; si se llena, se descarta el más nuevo y se avisa por consola.
- El ACK sale con qos 0: si se pierde, el reintento del robot lo recupera.
- El worker de reportes corre fuera del hilo de red de paho; nunca se publica ni se espera PUBACK dentro de `on_message`.
- La conversión al formato oficial del servidor, si hace falta, va en una sola función: `formatear_para_servidor()` (**TODO** hasta confirmar el esquema).

Limitación conocida: si el PUBACK expira pero el broker sí entregó el mensaje, el reintento puede duplicarlo en el servidor. El protocolo no permite distinguirlo; el servidor debe deduplicar por `secuencia`.

### 3.5 Flujo del robot

1. **Esperar arranque:** recibir configuración válida, calibrar giroscopio y confirmar que el sensor ve el cuadrante verde. Iniciar cronómetro.
2. **Buscar:** ir a la X sin revisar más cercana, prefiriendo cuadrantes sin revisar; evitar obstáculos con los tres ultrasonidos. Si aparece una figura confirmada (5 de los últimos 7 frames) y no está contada en esa posición, pasar a acercarse. Si cambia el color del piso, actualizar cuadrante. Si hay borde negro (2 lecturas seguidas) o atasco, retroceder y girar.
3. **Escanear:** al llegar a una X, girar 360° en 12 pasos con pausa. Si aparece una figura, pasar a acercarse. Al terminar, marcar la X como revisada y, si están las 6 del cuadrante, marcar el cuadrante.
4. **Acercarse:** centrar la figura y avanzar mientras se ve. Si se pierde más de 1 s, volver a buscar. Si hay obstáculo sin figura, rodear. Si la distancia frontal es ≤ 6 cm y la figura está centrada, pasar a reportar.
5. **Reportar:** enviar el reporte con la secuencia. Esperar ACK hasta 8 s; si no llega, reenviar con la misma secuencia hasta agotar los envíos. Sin ACK no se derriba: se descarta y se vuelve a buscar.
6. **Derribar:** mover el servo, verificar con la cámara si cayó. Si sigue en pie y hay menos de 3 golpes, otro golpe; si no cae tras 3, descartar. Si cae, contar en el cuadrante, enviar el reporte actualizado, retroceder y girar.
7. **Terminar:** al cumplirse el tiempo o si la batería baja del mínimo, detener motores, poner el servo en reposo y enviar el reporte final.

Reglas que no se rompen: reportar y recibir ACK antes de derribar; una figura derribada no se vuelve a perseguir; el cronómetro se revisa en cada paso.

### 3.6 Estructura del repositorio

```
Codigo_Coriot/
├── README.md                 # Portada corta
├── docs/
│   └── PROYECTO.md           # Este documento
├── config.py                 # Rutas, clases, umbrales, pista, temas MQTT
├── main.py                   # Orquesta cámara → visión → robot; reporte → servidor → ACK
├── app_gui.py                # GUI de operación, captura y entrenamiento
├── Iniciar_GUI.bat           # Lanzador de la GUI en Windows
├── Requirements.txt          # Dependencias de Python
├── requirements-lock.txt     # Versiones fijadas para instalar
├── firmware/
│   └── firmware_robot_v3_7_esp32/
│       └── firmware_robot_v3_7_esp32.ino
├── logica/
│   ├── deteccion_color.py    # Detector HSV para pruebas y calibración
│   ├── deteccion_yolo.py     # Detector YOLO
│   ├── filtros.py            # Solo cajas verticales (figura de pie)
│   ├── vision_robot.py       # Detecciones → línea D,v,c,x,w,h,conf
│   ├── robot_mqtt.py         # Reporte → servidor → PUBACK → ACK
│   ├── iot.py                # Cliente MQTT único de la laptop
│   ├── calibrar_color.py     # Ajuste en vivo de los rangos HSV
│   └── probar_en_vivo.py     # Prueba del detector con cajas
├── modelo/
│   ├── verificar_entorno.py  # Diagnóstico: versiones + inferencia de prueba
│   ├── rescate.yaml          # Dataset y clases para YOLO
│   ├── entrenar.py           # Entrena YOLO11n → modelo/pesos/rescate.pt
│   ├── evaluar.py            # mAP50, mAP50-95 y P/R por clase
│   ├── revisar_dataset.py    # Detecta y quita etiquetas dudosas
│   ├── pesos/                # yolo11n.pt y modelos entrenados
│   └── dataset/              # images/ y labels/ para train y val
├── stream/
│   ├── recibir.py            # Cámara IP Webcam en hilo (último frame)
│   └── capturar.py           # Guarda frames + etiquetas YOLO
├── tests/                    # Suite unittest
├── tools/
│   └── simular_robot.py      # Simulador del robot sin hardware
├── scripts/
│   ├── instalar_laptop.ps1   # Instalación del entorno
│   └── verificar_laptop.ps1  # Verificación completa
├── datos/                    # Capturas y datasets de la GUI (no se versiona)
└── logs/                     # Inferencias y registros de entrenamiento
```

### 3.7 Cómo ejecutar

```powershell
# Flujo de competencia (sin ventana de video)
python main.py

# GUI
.\.venv\Scripts\python.exe app_gui.py
# o doble clic en Iniciar_GUI.bat

# Simulador del robot, sin hardware
python tools/simular_robot.py --duracion 30

# Pruebas
python -m unittest discover -s tests -v
```

`main.py` acepta `--equipo`, `--intento` y `--modo {yolo,color}`. El modo `color` es solo para pruebas y exige activarlo explícitamente; en competencia se usa `yolo`.

---

## 4. Decisiones

### 4.1 Decisiones de arquitectura

| # | Fecha | Decisión | Motivo |
|---|---|---|---|
| D1 | 2026-11-09 | La laptop detecta H y S con la cámara del celular (IP Webcam). | El cómputo off-board está permitido y la cámara del celular es más fácil de ubicar que una a bordo. |
| D2 | 2026-11-09 | El robot arma el JSON y lo manda a la laptop; la laptop lo reenvía tal cual al servidor. | El robot conoce sus conteos y su cuadrante; la laptop no debe alterar la evidencia oficial. |
| D3 | 2026-11-09 | El robot decide el derribo con sus sensores. La laptop no manda órdenes de derribo. | Evitar control remoto y depender de una decisión local verificable. |
| D4 | 2026-11-09 | La laptop responde ACK al robot solo después del PUBACK del servidor (qos 1). Sin ACK no hay derribo. | Garantizar que el servidor recibió el reporte antes de la confirmación física. |
| D5 | 2026-11-09 | El color del piso se lee con un TCS34725 por I2C en el robot. | El reglamento exige reconocer el color, no asignarlo por posición. |
| D6 | 2026-11-09 | Se usan 3 HC-SR04: frente, izquierda y derecha. | Navegación reactiva con obstáculos de posición variable. |
| D7 | 2026-11-09 | Dos DRV8871 alimentados directo de la LiPo 2S, sin buck de 6 V. | Simplificar la alimentación y evitar caídas de tensión en los motores. |
| D8 | 2026-11-09 | El robot calcula el cuadrante; la laptop no. | El centro del robot determina la zona y el robot tiene el sensor de color. |
| D9 | 2026-11-09 | El robot lleva el conteo y solo cuenta derribos confirmados; la laptop solo reenvía. | Evitar doble conteo y mantener la confirmación física en el robot. |
| D10 | 2026-11-09 | **Borde negro ACTIVO.** El límite exterior es negro; lo prohibido es la línea guía interior. **Reemplaza** la decisión anterior de borde negro desactivado. | La tabla oficial dice explícitamente que el límite exterior es un borde negro visible. |
| D11 | 2026-11-09 | **24 X** (6 por cuadrante), no 16. **Reemplaza** el escaneo de 16 puntos. | La tabla oficial fija 24 posiciones de víctima. |
| D12 | 2026-11-09 | **Navegación reactiva**, sin mapa fijo de obstáculos. **Reemplaza** el mapa fijo. | La posición de los edificios depende del montaje. |

### 4.2 Decisiones de implementación

| # | Fecha | Decisión | Motivo |
|---|---|---|---|
| D13 | 2026-11-09 | Un solo cliente MQTT (`laptop-E01`) para visión, suscripción al robot, envío al servidor y ACK. | Dos clientes con el mismo ID se expulsan entre sí. |
| D14 | 2026-11-09 | El reenvío usa qos 1 y `wait_for_publish(timeout=5)`; el ACK usa qos 0. Sin conexión no se encolan mensajes con qos > 0. | No confirmar como enviado lo que el servidor no recibió y no bloquear la visión. |
| D15 | 2026-11-09 | La deduplicación usa `(secuencia, contenido idéntico)`. | El firmware v3.4 reiniciaba la secuencia en RAM; el v3.7 ya la persiste en NVS, pero la huella de contenido sigue protegiendo ante reinicios y reintentos. |
| D16 | 2026-11-09 | La visión se calcula y envía como máximo a 15 Hz, con qos 0. | La red nunca debe bloquear el bucle de visión. |
| D17 | 2026-11-09 | El firmware v3.7 persiste la secuencia en NVS y recibe `{equipo, intento}` por configuración MQTT retenida. | Evitar que un reinicio reutilice números y permitir que el juez asigne el intento. |
| D18 | 2026-11-09 | En competencia se usa **solo YOLO**; el detector de color queda para pruebas y calibración y exige activación explícita. **Reemplaza** la regla anterior de competir con color si el mAP era bajo. | El reglamento exige que la clasificación H/S provenga de un modelo de aprendizaje automático. |
| D19 | 2026-11-10 | La GUI tiene 3 pestañas (Operación, Captura y Entrenamiento) y solo controla la laptop. | Separar operación, captura y entrenamiento sin agregar órdenes al robot. |
| D20 | 2026-11-10 | El entrenamiento desde la GUI corre en segundo plano, con tiempo máximo y copia del mejor modelo a `modelo/pesos/rescate.pt`. | No congelar la interfaz y ajustarse al tiempo del evento. |

---

## 5. Contradicciones

| # | Una fuente dice | Otra fuente o la realidad dice | Estado |
|---|---|---|---|
| C1 | El README antiguo decía que la laptop calculaba cuadrantes, conteo e IoT. | D8 y D9: el robot calcula el cuadrante y cuenta; la laptop solo reenvía. | Resuelta en T9 (2026-11-09). |
| C2 | El README antiguo leía el cuadrante por cámara mirando el color del piso. | D5: lo lee el TCS34725 del robot. | Resuelta en T9. |
| C3 | El README antiguo decía que la laptop construía el JSON. | D2: lo arma el robot y la laptop lo reenvía tal cual. | Resuelta en T9. |
| C4 | Una nota antigua del firmware decía “borde negro: desactivado”. | El firmware v3.7 tiene `BORDE_NEGRO = true` y 2 lecturas seguidas. | Resuelta en v3.7. |
| C5 | El encabezado del firmware v3.7 dice “24 posiciones de víctima” y el comentario de `main` dice “6 X por cuadrante”. | `PUNTOS_POR_Q = 4` crea 4 waypoints por cuadrante (16 en total) y `cuadranteCompleto()` revisa 4 por cuadrante. Las 6 X no se visitan una por una. | **Abierta.** Decidir si se aceptan 4 puntos de barrido por cuadrante o se cambia el firmware. Dueño: Wilk. |
| C6 | El firmware usa `DEDUP_MM = 150`: figuras a menos de 15 cm se consideran la misma. | En 1 m × 1 m con 6 X por cuadrante puede haber separaciones menores a 15 cm. | **Abierta.** Medir en la pista antes de confiar en el deduplicado. |
| C7 | Los documentos anteriores suponían que el firmware no estaba en el repositorio. | `firmware/firmware_robot_v3_7_esp32/` existe localmente (sin seguimiento en Git). | Resuelta como hecho; no se modifica el firmware desde OpenCode. |
| C8 | Un documento decía que la v2 reemplazaba a la actualización. | La actualización decía que ella prevalecía. | Resuelta: prevalece la actualización de 2026-11-09. |
| C9 | La actualización decía que el firmware vigente era v3.3. | El archivo local es v3.7, con borde activo y 24 posiciones en el encabezado. | Resuelta: se usa v3.7. |
| C10 | El firmware v3.4 reiniciaba la secuencia en RAM. | La deduplicación por número podía silenciar reportes nuevos. | Resuelta con huella de contenido (D15); el v3.7 además persiste la secuencia en NVS. |
| C11 | La documentación decía “reenviar máximo 2 veces”. | El firmware v3.4 tenía `MAX_ENVIOS = 2` y el v3.7 tiene `MAX_ENVIOS = 3`; con el envío inicial da 3 transmisiones. | Resuelta en v3.7: inicial + 2 reenvíos. |
| C12 | El README antiguo decía 47 pruebas. | La suite actual tiene 76 pruebas: 18 nuevas de la GUI. | Resuelta en este documento (ver §8.4). |
| C13 | La documentación anterior decía que se competía con el detector de color si no había `rescate.pt` o si el mAP era ≤ 0.70. | `config.py` pone `MODO_DETECCION = "yolo"` por defecto y `main.py` exige `rescate.pt` para arrancar en modo `yolo`. | **Abierta.** Decisión vigente: competir con YOLO (D18). Falta que el modelo exista; dueño: Wilk. |
| C14 | La documentación de entrenamiento recomienda `--tiempo 40` (40 min de tope). | La GUI propone 20 minutos por defecto. | **Abierta.** Decidir el tope real del día. Dueños: Wilk y OpenCode. |
| C15 | El encabezado interno del firmware dice “v3.6”. | La carpeta y el archivo se llaman `firmware_robot_v3_7_esp32`. | **Abierta (cosmética).** La versión que se cita es v3.7; dueño: Wilk. |
| C16 | La documentación anterior decía que el robot arranca con un botón físico y que la GUI “Preparar” no arranca el robot. | El firmware v3.6/v3.7 no usa botón: al encender espera una configuración válida por MQTT y arranca. La GUI publica esa configuración retenida en “Preparar”. | **Abierta y crítica.** Definir la secuencia oficial de arranque con el juez. Dueños: Wilk y OpenCode. |
| C17 | `_servidor_configurado()` considera que `127.0.0.1` no es un servidor configurado. | El broker local de pruebas usa `127.0.0.1`; si el broker oficial también fuera local, la GUI mostraría una advertencia falsa. | **Abierta.** Confirmar el host oficial; dueño: organización. |
| C18 | `config.FUENTE_VIDEO_DEFECTO` es una IP fija (`http://192.168.80.145:8080/video`). | La GUI propone `"0"` (webcam de la laptop) por defecto. | **Abierta (diferencia de valores por defecto).** No es un error si se elige la fuente en la GUI; dueño: OpenCode. |
| C19 | `.gitignore` ignora pesos, dataset y `modelo/runs/`. | No ignora `logs/` ni `datos/`, que contienen inferencias y capturas. | **Abierta.** Agregarlos antes de un commit; dueño: OpenCode. |
| C20 | `requirements-lock.txt` está guardado en UTF-16LE (BOM `FF FE`). | `pip install -r` espera UTF-8. | **Abierta.** Puede fallar la instalación; dueño: OpenCode. |
| C21 | `modelo/verificar_entorno.py` incluye un mensaje que apunta a una guía de pesos externa. | Si esa guía se retira, la referencia queda rota. | **Abierta.** Actualizar el mensaje o conservar la guía; dueño: OpenCode (no se tocó el código en esta tarea). |
| C22 | La documentación anterior hablaba de 470 s como límite provisional. | El reglamento fija 480 s; el firmware envía el reporte final a los 470 s y detiene todo a los 480 s. | Resuelta: 480 s totales, con cierre anticipado de reporte a los 470 s. |

---

## 6. Firmware

### 6.1 Versión y compilación

- **Versión vigente:** v3.7, en `firmware/firmware_robot_v3_7_esp32/firmware_robot_v3_7_esp32.ino`.
- El encabezado interno todavía dice v3.6 (C15); la carpeta y el archivo son la referencia.
- No se modifica el firmware desde OpenCode.

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 firmware\firmware_robot_v3_7_esp32
```

### 6.2 Dependencias

- Core ESP32 (`esp32:esp32`): `Wire`, `WiFi`, `Preferences`, `math.h`, `esp_task_wdt.h`, `Arduino.h`.
- `PubSubClient` para MQTT.

```powershell
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install PubSubClient
```

`arduino-cli` no está instalado en esta máquina; la compilación queda pendiente (sección 9).

### 6.3 Hardware y pines

| Elemento | Conexión |
|---|---|
| ESP32 DevKit | Controlador principal |
| TCS34725 (color) | I2C, dirección `0x29`, SDA 21 / SCL 22 |
| MPU-6050 (giroscopio) | I2C, dirección `0x68` |
| HC-SR04 frontal | TRIG 18 / ECHO 19 |
| HC-SR04 izquierdo | TRIG 16 / ECHO 17 |
| HC-SR04 derecho | TRIG 4 / ECHO 14 |
| DRV8871 izquierdo | IN1 25 / IN2 26 |
| DRV8871 derecho | IN1 27 / IN2 13 |
| Servo de derribo | GPIO 33 |
| Divisor de batería | GPIO 32 |
| Encoders | 34/35 (izquierdo) y 36/39 (derecho), solo entrada |
| Botón/arranque | GPIO 0 (el firmware v3.6+ no lo usa como botón) |

### 6.4 Comportamiento y constantes

- Al encender espera una configuración válida `{equipo, intento}` en `coriot/robot/E01/config`; no hay botón de arranque.
- `USAR_ACK_SERVIDOR = true`: el derribo espera ACK de la laptop.
- `ACK_MS = 8000`; `MAX_ENVIOS = 3` (inicial + 2 reenvíos); `MAX_GOLPES = 3`.
- `LIMITE_MS = 470000` (7 min 50 s): envía reporte final y detiene motores.
- `LIMITE_TOTAL_MS = 480000` (8 min): detiene todo.
- `BORDE_NEGRO = true` con `BORDE_LECTURAS = 2`.
- `PUNTOS_POR_Q = 4`: 4 waypoints por cuadrante (16 en total). El encabezado habla de 24 X y el comentario de 6 por cuadrante; ver C5.
- `figsX[24]` y `figsY[24]`: capacidad para 24 figuras detectadas.
- `CIERRE_ANTICIPADO = false`.
- Visión: exige `h ≥ 1.2 × w`; `CONF_MIN = 50`; confirma una figura con 5 de los últimos 7 frames.

### 6.5 Parámetros que faltan calibrar (TODO)

- `WIFI_SSID` y `WIFI_PASS` reales.
- `MQTT_HOST`, `MQTT_PORT` y credenciales reales.
- `COLOR_CALIBRADO = false` y `COLOR_CAL[4][3]`: calibrar el TCS34725 en la pista.
- `CLEAR_MIN`: ajustar con la luz del auditorio.
- `BAT_FACTOR`: verificar con multímetro y divisor.
- `TICKS_REV`: confirmar los ticks por vuelta.
- Dimensiones del servo en reposo y en derribo: deben caber en 13 × 18 × 20 cm.
- Coordenadas de las 24 X: hoy son provisionales.
- Formato definitivo del JSON y broker/tema oficiales.
- Recepción de coordenadas de X por MQTT y deduplicación por rumbo ±15°.

---

## 7. GUI

La GUI se abre con `Iniciar_GUI.bat` o con `.\.venv\Scripts\python.exe app_gui.py`. No envía órdenes de movimiento, arranque ni parada al robot.

### Pestaña 1 — Operación

- **Identidad del intento:** equipo, intento y fuente de video (URL del celular o `0` para la webcam).
- **Preparar:** publica `{equipo, intento}` de forma retenida en `coriot/robot/E01/config` y arranca la cámara, la detección y el enlace de la laptop. **No** envía órdenes de movimiento. Ojo: el firmware v3.7 arranca al recibir una configuración válida, así que publicarla con el robot encendido equivale a la señal de arranque (C16).
- **Detener:** cierra los procesos de la laptop; no envía nada al robot.
- **Indicadores en vivo:** Cámara, Broker local, Enlace al servidor, Robot y Visión.
- **Aviso de servidor:** si el endpoint no está configurado, se muestra en rojo y no se envían reportes; el robot no recibe ACK y no derriba.
- **Último reporte del robot:** solo lectura.
- **Avisos de la laptop:** mensajes de operación y errores.

### Pestaña 2 — Captura de figuras

- Crea una **sesión** con fecha y hora; las fotos se guardan en `datos/capturas/<sesión>/`.
- Abre la cámara al entrar a la pestaña.
- Botones: **Guardar como H (herida)**, **Guardar como S (suministros)** y **Guardar sin figura**.
- Lleva el conteo de H, S y sin figura de la sesión.
- Permite abrir la carpeta de la sesión o empezar una sesión nueva.
- Las fotos se usan para armar el dataset de entrenamiento; “sin figura” sirve como negativo.

### Pestaña 3 — Entrenamiento

- **Carpeta del dataset:** por defecto, la última sesión de captura; se puede cambiar.
- **Tiempo máximo (minutos):** por defecto 20.
- **Épocas (máximo):** por defecto `config.EPOCAS` (50).
- **Dispositivo:** CPU o GPU; si no hay GPU, usa CPU.
- **Entrenar:** corre en segundo plano y muestra el progreso.
- **Resultado:** mAP y avisos. Si hay pocas imágenes de validación, muestra `NO CONFIABLE: pocas imágenes de validación` y no aplica el umbral 0.70.
- **Usar este modelo en la competencia:** copia el mejor resultado a `modelo/pesos/rescate.pt`; no cambia `config.py`.

En el pie de la ventana hay un botón para abrir `logs/`, donde quedan las inferencias y el registro de cada entrenamiento.

---

## 8. Entrenamiento y día de la competencia

### 8.1 Mínimos de datos

Para considerar confiable el mAP se necesitan al menos **30 imágenes de validación** y **10 instancias por clase** (H y S). Con menos, `modelo/entrenar.py` reporta `mAP50: NO CONFIABLE` y no aplica el umbral 0.70. Estos mínimos están en `config.py` como `MIN_IMAGENES_VAL = 30` y `MIN_INSTANCIAS_POR_CLASE = 10`.

### 8.2 Pesos del modelo

- `modelo/pesos/yolo11n.pt`: modelo base obligatorio (~5,6 MB). No se descarga solo; se copia desde el USB o se instala antes del evento.
- `modelo/pesos/rescate.pt`: modelo entrenado con las figuras reales. Se genera con `python -m modelo.entrenar`.
- Los pesos no están en Git. `rescate.pt` es obligatorio para competir en modo `yolo`.

### 8.3 Comandos de captura, limpieza y entrenamiento

```powershell
# Captura con la cámara del celular
$env:CORIOT_VIDEO = "http://IP:8080/video"
python -m stream.capturar

# Revisar etiquetas automáticas (sin borrar)
python -m modelo.revisar_dataset
python -m modelo.revisar_dataset --borrar

# Entrenar con tope de tiempo
python -m modelo.entrenar --epocas 30 --tiempo 40 --dispositivo cpu

# Evaluar el modelo entrenado
python -m modelo.evaluar
```

La captura también se puede hacer desde la pestaña 2 de la GUI. El entrenamiento desde la GUI usa los mismos parámetros y muestra el resultado sin bloquear la ventana.

### 8.4 Tiempos medidos

Medición local en una laptop de desarrollo (CPU Intel i5-12400F, sin GPU), con 300 imágenes de entrenamiento y 60 de validación, 640 px, lote 8 y 3 épocas:

| Época | Tiempo |
|---|---:|
| 1 | 72,8 s |
| 2 | 68,0 s |
| 3 | 64,3 s |
| **Total 3 épocas** | **215,5 s (3,59 min)** |
| **Proyección 30 épocas** | **2062,1 s (34,4 min)** |

La proyección no incluye captura ni etiquetado. Si el dataset supera ~300 imágenes, el tiempo crece casi linealmente: recalcular o bajar `--imgsz`.

### 8.5 Cronograma y procedimiento del día

| Hora | Actividad |
|---|---|
| 9:00–9:30 | Apertura y acreditación; sorteo del orden de turnos |
| 9:30–10:10 | Inspección técnica: medidas, modelo de IA y conexión IoT; 4 min por equipo |
| 10:10–11:00 | Pruebas en pista, turno 1: 5 min por equipo |
| 11:00–11:50 | Pruebas en pista, turno 2: 5 min por equipo |
| 11:50–12:50 | Almuerzo; pista cerrada |
| 12:50–13:00 | Montaje de la primera combinación |
| 13:00–14:30 | Competencia oficial, ronda 1: un intento por equipo, hasta 8 min |
| 14:30–14:35 | Cambio a la segunda combinación |
| 14:35–16:05 | Competencia oficial, ronda 2: un intento por equipo, hasta 8 min |
| 16:05–17:00 | Cierre, consolidación de puntajes y resultados |

**Antes del intento:**

1. Laptop encendida y `.venv` activo.
2. Mosquitto local corriendo (ver §8.6).
3. Pesos presentes: `yolo11n.pt` y, si se entrenó, `rescate.pt`.
4. `scripts\verificar_laptop.ps1` en verde.
5. Equipo e intento cargados en la GUI.
6. Decidir con el juez el momento exacto de publicar la configuración y arrancar el robot (C16).

**Durante el intento:** el robot es autónomo; no se tocan controles ni se envían órdenes. La laptop solo detecta y reenvía. El apagado del robot termina el intento.

**Cierre:** el robot detiene motores; se conserva el último reporte válido. No se exige volver al inicio.

### 8.6 Broker local (Mosquitto)

Mosquitto no está incluido en el repositorio. Antes del evento, descargar el instalador de `https://mosquitto.org/download/` y llevarlo en el USB; la máquina de competencia puede no tener internet.

1. Ejecutar el instalador como administrador.
2. Aceptar el servicio de Windows (Mosquitto Service).
3. Verificar que escucha en `127.0.0.1:1883`:

```powershell
mosquitto_sub -h 127.0.0.1 -p 1883 -t '#' -v
```

4. Si el firewall pregunta, permitir en red privada.

Comandos útiles:

```powershell
mosquitto_sub -h 127.0.0.1 -p 1883 -t coriot/robot/E01/config -v
mosquitto_pub -h 127.0.0.1 -p 1883 -t coriot/robot/E01/config -r -q 1 -m '{"equipo":"E01","intento":"I1"}'
```

### 8.7 Verificación final

```powershell
scripts\verificar_laptop.ps1
python -m unittest discover -s tests -v
```

La suite actual tiene **76 pruebas** y corre sin red ni broker. Si falla, no se compite hasta corregirla.

---

## 9. Pendientes

| Pendiente | Dueño | Nota |
|---|---|---|
| Confirmar host, puerto, tema, credenciales y esquema JSON del servidor | Organización | Sin esto no hay ACK ni derribo; `coriot/reporte` es provisional |
| Confirmar los nombres de los cuadrantes en el servidor | Organización | Deben coincidir con `rojo`, `azul`, `verde`, `amarillo` |
| Confirmar por escrito que la laptop puede enviar detecciones al robot por red privada | Organización | El reglamento permite el intercambio automático; conviene dejarlo por escrito |
| Medir las coordenadas exactas de las 24 X | Wilk | Se miden en la pista; no inventarlas |
| Compilar y probar el firmware v3.7 en el robot | Wilk | Requiere `arduino-cli`; no se compiló en esta sesión |
| Resolver la diferencia entre 4 waypoints por cuadrante y 24 X | Wilk | C5; decisión de firmware, no de OpenCode |
| Calibrar TCS34725, `COLOR_CAL`, `CLEAR_MIN` y `BAT_FACTOR` | Wilk | En la pista y con multímetro |
| Confirmar `TICKS_REV`, dimensiones del servo y medidas 13 × 18 × 20 cm | Wilk | Incluye partes desplegadas |
| Capturar el dataset real y entrenar `rescate.pt` | Wilk | Con apoyo de OpenCode; el dataset está vacío |
| Recalibrar HSV y `ASPECTO_MIN` con la luz del auditorio | Wilk | Los valores de casa no sirven |
| Decidir la secuencia oficial de arranque (configuración retenida vs. señal del juez) | Wilk y OpenCode | C16; crítica para no arrancar antes de tiempo |
| Decidir el tope de entrenamiento: 20 min de la GUI vs. 40 min recomendados | Wilk y OpenCode | C14 |
| Hacer la prueba de extremo a extremo con Mosquitto real y cámara real | OpenCode y Wilk | Falta broker y hardware conectados |
| Agregar `logs/` y `datos/` a `.gitignore` | OpenCode | C19; no se hizo en esta tarea |
| Corregir la codificación de `requirements-lock.txt` | OpenCode | C20; UTF-16LE puede romper `pip install -r` |
| Actualizar el mensaje de `modelo/verificar_entorno.py` que apunta a la guía de pesos, si esa guía se retira | OpenCode | C21; no se tocó el código en esta tarea |
| Probar la GUI con cámara y broker reales | OpenCode y Wilk | La prueba actual usa cámara simulada y sin broker |
| Revisar el aviso de servidor cuando el broker sea `127.0.0.1` | OpenCode | C17 |

---

## 10. Bitácora

### 2026-10-29 — Base del proyecto

- Se instaló Python 3.12.10, se creó `.venv` y se conectó el repositorio.
- Se crearon `config.py`, `main.py`, `modelo/`, `stream/` y `logica/`.
- Se implementó la detección por color HSV, el stream con hilo y la calibración en vivo.
- Se capturó y limpió el primer dataset; se agregó el filtro de figuras verticales.
- Se implementó el envío MQTT y se probaron entrenamiento y evaluación de YOLO.

### 2026-11-07 — Dataset vaciado

- Se vació el dataset de prueba para llegar limpio a la sesión de práctica del evento.

### 2026-11-09 — Arquitectura v2 y limpieza

- La laptop quedó como detector y reenvío; el robot navega, cuenta y decide el derribo.
- Se implementaron el enlace robot → laptop → servidor → ACK, el simulador y la suite de pruebas.
- Se retiraron los módulos de cuadrante, calibración de piso y conteo por cámara.
- Se actualizaron los temas MQTT, el flujo de `main.py` y la documentación de arquitectura.

### 2026-11-10 — GUI y consolidación

- Se terminó la GUI de 3 pestañas con captura por sesiones y entrenamiento en segundo plano.
- Se agregaron 18 pruebas de GUI; la suite completa quedó en 76 pruebas en verde.
- Se verificó una sesión de captura con H, S y sin figura, y un entrenamiento de 1 época.
- Se consolidó la documentación en este archivo y el README quedó como portada corta.
- Quedan pendientes las fuentes históricas por retirar cuando el usuario lo confirme.
