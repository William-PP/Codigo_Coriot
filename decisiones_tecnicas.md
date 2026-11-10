# Decisiones técnicas — Código Rescate (CORIOT GAMES 2026)

**Última actualización:** 2026-11-09
**Evento:** 12 de noviembre de 2026

Este archivo registra las decisiones que no quedan claras en el código o que se
tomaron al implementarlo. No sustituye al README ni al documento de contexto.

---

## 1. Jerarquía documental

Instrucción del usuario: si `ACTUALIZACION_CONTEXTO_OPENCODE.md` y
`CONTEXTO_OPENCODE_v2.md` se contradicen, prevalece la actualización. Orden
aplicado:

1. `ACTUALIZACION_CONTEXTO_OPENCODE.md` — correcciones de pista, D10, 24 X y
   navegación reactiva (2026-11-09).
2. `CONTEXTO_OPENCODE_v2.md` — arquitectura y tareas T1–T9.
3. `firmware/robot_esp32/firmware_robot_v3_4_esp32.ino` — comportamiento real
   del robot (protocolo, umbrales y pines). **No se modifica desde OpenCode.**
4. `Contexto.txt` — reglamento, medidas y requisitos de la pista.
5. `README.md` — memoria del proyecto. Su arquitectura está desactualizada
   hasta que se haga la tarea T9.

El 2026-11-09 el usuario renombró `CONTEXTO_OPENCODE_v2 (1).md` a
`CONTEXTO_OPENCODE_v2.md`; ya existe con el nombre exacto pedido.

Regla: una contradicción se avisa y se resuelve con el usuario. No se cambia en
silencio.

---

## 2. Arquitectura adoptada (v2 §3, decisiones D1–D12)

Se adoptan las doce decisiones sin cambios:

| # | Tema | Decisión |
|---|---|---|
| D1 | Visión | La **laptop** detecta H y S con la cámara del celular (IP Webcam). |
| D2 | JSON al servidor | El **robot** arma el JSON y lo manda a la laptop; la laptop lo reenvía **tal cual** al servidor. |
| D3 | Derribo | Lo decide el **robot** con sus sensores. La laptop no manda órdenes de derribo. |
| D4 | ACK | La laptop responde ACK al robot **solo después** del PUBACK del servidor (qos 1). Sin ACK no hay derribo. |
| D5 | Color de piso | **TCS34725 por I2C** en el robot. Detecta cuadrante y borde negro. |
| D6 | Distancia | **3 HC-SR04** (frente, izquierda, derecha). |
| D7 | Motores | **2 DRV8871** alimentados directo de la LiPo 2S. Sin buck de 6 V. |
| D8 | Cuadrante | Lo calcula el **robot** con el TCS34725. La laptop no calcula cuadrante. |
| D9 | Conteo | Lo lleva el **robot**; solo cuenta derribos confirmados. La laptop solo reenvía. |
| D10 | Borde negro | **ACTIVO**. El límite exterior es negro; lo prohibido es la línea guía interior. |
| D11 | Escaneo | **24 X** (6 por cuadrante), no 16. |
| D12 | Navegación | **Reactiva**, sin mapa fijo de obstáculos (su posición depende del montaje). |

Consecuencia: `logica/contador.py`, `logica/cuadrante.py` y
`logica/calibrar_piso.py` quedan **fuera del flujo**. Se eliminan en T8, con
confirmación explícita del usuario antes de borrar.

---

## 3. Decisiones de T1 — `config.py`

| # | Decisión | Motivo |
|---|---|---|
| T1-1 | `FUENTE_VIDEO` se lee de la variable de entorno **`CORIOT_VIDEO`**; si está vacía se usa `FUENTE_VIDEO_DEFECTO` (la URL actual del celular). | Cambiar de cámara sin editar código. |
| T1-2 | Si `CORIOT_VIDEO` es solo dígitos se convierte a `int` (p. ej. `"0"` → webcam 0). | `cv2.VideoCapture("0")` interpreta `"0"` como archivo, no como cámara. |
| T1-3 | `CUADRANTES` usa los nombres oficiales y el orden del firmware: `rojo`, `azul`, `verde`, `amarillo`. Los centros van en mm con origen en la esquina inferior izquierda. | Coincidir con el JSON de §6.3 y con `NOMBRE[]` del firmware. |
| T1-4 | `PUNTOS_X = None` con comentario `TODO`. | Dejar explícito que faltan las 24 coordenadas; no inventarlas. |
| T1-5 | `SERVIDOR_TEMA = "coriot/reporte"` marcado `TODO`. | Es el valor provisional que fija la v2 §6.1. |
| T1-6 | Se eliminan `BROKER_TEMA` y `USAR_CUADRANTE`. | Evitar dos fuentes de verdad; el tema pasa a ser parámetro (T5) y el cuadrante sale del flujo (T8). |
| T1-7 | `ROBOT_ID = "E01"` y `BROKER_CLIENTE = "laptop-E01"`. Los temas se construyen a partir de `ROBOT_ID`. | Un solo lugar para cambiar el identificador del equipo. |
| T1-8 | Se conservan `CONFIRMA_FRAMES` y `PISO_JSON`, marcados como legado. | `contador.py`, `cuadrante.py` y `calibrar_piso.py` todavía los importan hasta T8. |

### Consecuencia temporal de T1-6

Entre T1 y sus tareas de cierre, dos módulos viejos quedan **temporalmente
rotos** si se ejecutan:

- `main.py` lee `config.USAR_CUADRANTE` → se reescribe en **T4**.
- `logica/iot.py` imprime `config.BROKER_TEMA` al conectar → se cambia en **T5**.

No se tocaron ahora porque el usuario pidió no modificar T2, T4 ni T5 antes de
aprobar el plan. `import config` y el resto de módulos siguen funcionando.

---

## 4. Decisiones de T3 — `logica/vision_robot.py`

| # | Decisión | Motivo |
|---|---|---|
| T3-1 | `linea_vision()` devuelve una **lista** de líneas: 0, 1 o 2 (una por clase). | §6.2 permite H y S en el mismo frame; el llamador publica cada línea por separado. |
| T3-2 | Si no hay detecciones devuelve `["D,0,H,500,0,0,0"]`. | El robot declara visión caída si no recibe líneas en 1 s. |
| T3-3 | Por clase se conserva la detección de **mayor confianza**; el orden de salida es H y luego S. | Una sola línea por clase y salida determinista. |
| T3-4 | `x`, `w` y `h` usan el mismo `factor = 1000 / ancho_frame`, se redondean al entero más cercano y se limitan a 0–1000. | Conservar la proporción para que el firmware pueda exigir `h ≥ 1.2 × w`. |
| T3-5 | `conf` se multiplica por 100 y se redondea a entero (0–100). | YOLO entrega 0–1; el robot compara contra `CONF_MIN = 50`. |
| T3-6 | Las clases que no sean `H` o `S` se ignoran. | En modo YOLO con pesos COCO pueden llegar clases ajenas. |
| T3-7 | `ancho_frame <= 0` devuelve la línea sin figura. | Evitar división por cero en un frame inválido. |

---

## 5. Decisiones de T5 — `logica/iot.py`

| # | Decisión | Motivo |
|---|---|---|
| T5-1 | **Un solo cliente MQTT** (`laptop-E01`) para visión, suscripción al robot, envío al servidor y ACK. | Dos clientes con el mismo ID se expulsan entre sí. |
| T5-2 | `publicar(reporte, tema)` exige tema, usa qos 1 y `wait_for_publish(timeout=5)`; devuelve True solo si `is_published()` es verdadero. | En paho 2.1 `wait_for_publish` **no lanza** al agotar el tiempo: hay que consultar el estado. |
| T5-3 | `publicar_texto(texto, tema, qos=0)` para visión y ACK. Con qos 0 no espera; devuelve True si se encoló (`rc == 0`). | La visión no puede bloquearse. |
| T5-4 | Si no hay conexión, los envíos con qos > 0 devuelven False y **no** se encolan. | Evitar que un reporte viejo salga después, cuando ya se decidió no mandar ACK. |
| T5-5 | `suscribir(tema, callback, qos=1)`; el callback recibe `(tema, texto)` y se vuelve a suscribir en cada reconexión. | T2 necesita recibir los reportes sin depender de una sola conexión. |
| T5-6 | Los callbacks corren en el hilo de red de paho. **T2 debe encolar** el trabajo: publicar al servidor y esperar el PUBACK nunca dentro de `on_message`; el ACK sale del mismo worker. | Condición del usuario; no bloquear el hilo de red. |
| T5-7 | `TIMEOUT_PUBACK = 5.0`; `conectado()` expone el estado para la pantalla de T4. | Valor del protocolo v2 y diagnóstico simple. |
| T5-8 | `cerrar()` espera hasta 3 s al último mensaje y luego corta el bucle. | No perder el último envío al salir. |

---

## 6. Decisiones de T2 — `logica/robot_mqtt.py`

| # | Decisión | Motivo |
|---|---|---|
| T2-1 | `EnlaceRobot` se suscribe con `iot.suscribir(TEMA_REPORTE_ROBOT, ...)` y usa ese mismo cliente compartido. No crea otro cliente ni importa paho. | Mantener un solo `laptop-E01` (T5-1) y el mismo canal para todo. |
| T2-2 | `_al_recibir` solo valida el JSON, guarda el último reporte y hace `put_nowait`. Nunca publica, espera ni bloquea. | El callback corre en el hilo de red de paho; bloquearlo detiene toda la conexión (T5-6). |
| T2-3 | Un único worker (`enlace-robot`) saca de la cola, reenvía con `iot.publicar()` (qos 1 + PUBACK) y **solo después** manda el ACK con qos 0. | D4: el ACK es la autorización de derribo. |
| T2-4 | Sin PUBACK no se marca el reporte como reenviado y no sale ACK; el siguiente reintento del robot vuelve a intentarlo. | Sin ACK el robot no derriba; nunca se confirma lo que el servidor no recibió. |
| T2-5 | La deduplicación usa `(secuencia, contenido idéntico)`, no solo el número. Un reintento exacto recibe ACK sin reenviarse; la misma secuencia con otro contenido sí se reenvía. | El firmware arranca `secuencia = 0` en RAM, sin NVS (línea 239): tras un reinicio reutiliza números y una deduplicación por número silenciaría reportes nuevos. |
| T2-6 | Cola de 100 reportes; si se llena se descarta y se avisa por consola. | Sin ACK el robot reintenta; no conviene crecer sin límite. |
| T2-7 | El ACK es `{"secuencia": N, "ok": true}` y sale con qos 0. | El parser del firmware solo busca `"secuencia":N`. Con qos 0 no bloquea; si se pierde, el reintento del robot lo recupera. |
| T2-8 | `formatear_para_servidor()` devuelve el reporte tal cual, con `TODO`. | D2: la laptop reenvía; falta que la organización confirme el formato oficial. |
| T2-9 | `cerrar()` detiene el worker, descarta lo pendiente y **no** cierra el cliente compartido. | `iot.cerrar()` se llama una sola vez desde `main.py`; sin ACK no se derriba, así que descartar es seguro al salir. |
| T2-10 | Limitación conocida: si el PUBACK expira pero el broker sí entregó el mensaje, el reintento puede duplicarlo en el servidor. | El protocolo no permite distinguirlo; el servidor debe deduplicar por `secuencia`. Avisado, no oculto. |

### Pruebas de T2

Pasaron sin broker real, con dos dobles:

- `iot` falso: `on_message` responde en menos de 0,1 s mientras la publicación
  está bloqueada; ACK solo tras PUBACK; sin PUBACK no hay ACK; reintento
  idéntico solo recibe ACK; misma secuencia con otro contenido se reenvía;
  JSON inválido descartado; visión con qos 0; un solo cliente.
- `iot` real + cliente paho falso: publica al servidor con qos 1, llama
  `wait_for_publish(5)` y comprueba `is_published()`; luego ACK qos 0 sin
  esperar; con `is_published() == False` no hay ACK.

Falta la prueba de extremo a extremo con un broker real (T6), porque no hay
Mosquitto local ni el puerto 1883 abierto.

---

## 7. Decisiones de T4 — `main.py`

| # | Decisión | Motivo |
|---|---|---|
| T4-1 | `main.py` solo orquesta: carga el detector, mantiene la cámara y llama a `EnlaceRobot`. No calcula cuadrante, no cuenta ni arma el JSON del servidor. | D8, D9 y D2: esas decisiones son del robot o de `EnlaceRobot`. |
| T4-2 | La visión se calcula y envía como máximo a **15 Hz**; el video se refresca al ritmo de la cámara. | §6.1: la laptop publica la línea "a la frecuencia de frames (máx. 15 Hz)". |
| T4-3 | Por ciclo: `detector(frame)` → `solo_verticales()` → `linea_vision(detecciones, ancho)` → `enlace.enviar_vision()` para cada línea. | Flujo v2. El filtro vertical descarta figuras derribadas. |
| T4-4 | Si el detector falla, se registra el error, se descartan las detecciones de ese ciclo y se envía `D,0,H,500,0,0,0`. | El robot no debe recibir una detección vieja ni la laptop caerse por un frame malo. |
| T4-5 | La apertura, lectura y cierre de cámara están protegidos. Si no abre o no entrega frames, se registra y se reintenta cada 0,5 s; tras 2 s sin frame se cierra y se reabre. | Condición T4: la cámara no puede tumbar el programa. |
| T4-6 | `stream/recibir.py` deja de entregar el frame viejo tras ~1 s de fallos de lectura (`FALLOS_MAX = 20`). | Sin esto, una cámara caída seguiría pareciendo viva y `main.py` no podría reabrirla. |
| T4-7 | La visión usa qos 0 a través de `EnlaceRobot.enviar_vision()`; el reenvío al servidor y el PUBACK ocurren en el worker de T2. | La red nunca bloquea el bucle de visión; la reconexión la maneja `iot`. |
| T4-8 | Se muestra en el video el estado MQTT, la secuencia y los conteos del último reporte; además se imprime una vez por secuencia nueva. | §8 T4: mostrar el último reporte y su secuencia. |
| T4-9 | Si `cv2.imshow()` falla, se desactiva solo el video y el pipeline sigue. | Un entorno sin GUI no debe detener la visión. |
| T4-10 | `ejecutar()` acepta cámara, detector, enlace, intervalo de visión, espera y límite de iteraciones inyectables. | Probar T4 sin cámara, sin broker y sin ventana; en producción se usan los valores por defecto. |

### Pruebas de T4

Pasaron sin cámara real y sin broker:

- Cámara falsa + detector falso + enlace falso: la caja 80×120 sale como
  `D,1,H,500,125,188,90` en cada ciclo.
- Cámara que no abre, que devuelve `None` o que lanza al leer: se registra el
  error, se cierra y se reintenta; el programa termina el bucle de prueba sin
  excepción.
- Detector que lanza: se envía `D,0,H,500,0,0,0` y el bucle sigue.
- `EnlaceRobot` real con `iot` falso y el PUBACK bloqueado: salieron 10 líneas
  de visión con qos 0 sin esperar al servidor y no salió ACK antes del PUBACK.
- Cliente MQTT real sin broker local: `main` arranca, completa el bucle y no se
  bloquea.
- `py_compile` de `main.py`, `config.py`, `stream/recibir.py` y `logica/*.py`.

Queda pendiente la prueba con cámara real, ventana real y broker real (T6).

---

## 8. Decisiones de T6 — `tools/simular_robot.py`

| # | Decisión | Motivo |
|---|---|---|
| T6-1 | Es una herramienta de pruebas fuera de `logica/`, `main.py`, `config.py` y `firmware/`. | Pedido T6 y condición 1. No forma parte del flujo de producción. |
| T6-2 | Un solo cliente paho con ID `robot-sim-E01`, distinto de `laptop-E01`. | Condición 2. Evita que el broker expulse a la laptop por ID duplicado. |
| T6-3 | Se suscribe a visión qos 0, ACK qos 1 y al tema del servidor simulado qos 1; publica reportes qos 1. | El robot real publica sus reportes con qos 1 y la visión no necesita confirmación. |
| T6-4 | La secuencia empieza en 1 y solo sube al generar un reporte **nuevo**. Los reintentos usan la misma secuencia. | v2 §6.3: la secuencia sube por reporte nuevo; los reintentos repiten la misma. |
| T6-5 | `TIMEOUT_ACK = 8 s` y `MAX_REINTENTOS = 2`: envío inicial + 2 reenvíos (3 transmisiones). | Instrucción explícita del usuario y paso [5] de v2: reenviar máximo 2 veces. |
| T6-6 | Un ACK solo cierra el reporte si `secuencia` coincide con el pendiente y `ok is True`. Cualquier otro ACK se ignora y se registra. | v2 §6.4: el ACK debe corresponder al reporte; `ok` falso no confirma. |
| T6-7 | El siguiente reporte se agenda al recibir el ACK o al agotar los reintentos (`ahora + periodo`), no cada 5 s a reloj fijo. | El robot real queda esperando el ACK del paso [5]; un solo reporte pendiente a la vez. |
| T6-8 | El reporte es una plantilla estática: 4 cuadrantes de `config.CUADRANTES`, solo el primero explorado con ceros; el resto `null`. | El simulador no calcula cuadrantes ni figuras; imita el formato del firmware. |
| T6-9 | Se escucha el tema del servidor solo para observar el reenvío de la laptop; el simulador no publica ahí. | Comprobar el camino robot → laptop → servidor de punta a punta. |
| T6-10 | Se registran latencia de cada ACK, reintentos usados, líneas de visión totales y tasa de líneas/s al terminar. | Pedido T6: medir tiempos. |
| T6-11 | `ejecutar(duracion)` usa un reloj y un `dormir` inyectables para las pruebas; en producción usa `time`. | Probar reintentos y cierre sin esperar 8 s reales ni depender del broker. |
| T6-12 | Si no puede conectar al broker, registra el error y sale con código 1; una duración o un periodo no positivos salen con código 2. | Un fallo de configuración o de red debe ser visible, no dejar un proceso colgado. |

### Pruebas de T6

No hay broker real disponible: Mosquitto no está instalado y el puerto 1883
está cerrado. Pasaron con cliente y reloj falsos:

- Un solo cliente con ID `robot-sim-E01`, distinto de `laptop-E01`.
- Visión: 250 líneas registradas sin pérdida y los tres temas suscritos.
- Tema del servidor: registra el reporte reenviado por la laptop.
- Sin ACK: envío inicial + 2 reenvíos con la misma secuencia (3
  publicaciones), luego descarta y registra el fallo.
- ACK con otra secuencia: se ignora y no cierra el reporte; el ACK correcto
  registra latencia y agenda el siguiente reporte.
- Fin de duración: el bucle termina solo, deja el resumen y no se cuelga.
- Integración sin broker (broker falso en memoria): `main.py` + `EnlaceRobot`
  real + simulador. El reporte seq 1 llegó a la laptop, se reenvió al tema del
  servidor y el ACK seq 1 volvió al simulador con latencia; la visión
  `D,1,H,500,125,188,90` salió con qos 0 y llegó al simulador.
- CLI: `--help` correcto; duración 0 y periodo 0 salen con código 2; sin broker
  el proceso registra el error y sale con código 1.
- `py_compile` de `tools/simular_robot.py`.

Queda pendiente la prueba con Mosquitto real y con `main.py` en dos procesos.

---

## 9. Decisiones de T7 — `tests/`

| # | Decisión | Motivo |
|---|---|---|
| T7-1 | Solo `unittest` de la biblioteca estándar; sin `pytest`. La suite se ejecuta con `python -m unittest discover -s tests -v`. | Condición 5 y v2 §T7: no agregar dependencias. |
| T7-2 | Ningún test abre red. `EnlaceRobot` se prueba con un `iot` falso inyectado en `rm.iot`; el simulador usa un cliente paho falso y un reloj inyectable. | Condiciones 1 y 2. No se toca `127.0.0.1:1883` ni ningún broker. |
| T7-3 | Cada test restaura el estado global que toca (`rm.iot`) y cierra sus enlaces en `tearDown`; no comparten objetos entre clases. | Condición 2: la suite no depende del orden. |
| T7-4 | `test_enlace.py` usa un `iot` falso con `Condition`/`Event` para bloquear el PUBACK y comprobar que `on_message` no bloquea y que el ACK sale **solo** después. | Reproduce la condición de aceptación de T2 sin esperar red ni tiempos reales. |
| T7-5 | No se prueban los `MORPH_OPEN`/`MORPH_CLOSE` porque no existe un filtro morfológico reutilizable: están en línea dentro de `logica/deteccion_color.py` y `logica/calibrar_color.py`. | No inventar una API que producción no tiene; se reporta como hueco de cobertura. |
| T7-6 | `test_simulador.py` se limita al parseo de argumentos (`_argumentos`) y al cálculo de latencias/reintentos con reloj falso, sin abrir conexión. | Pedido T7: solo lo comprobable sin red. |

### Archivos y cantidad de pruebas de T7

| Archivo | Pruebas | Cubre |
|---|---|---|
| `tests/test_vision_robot.py` | 16 | `linea_vision`, `SIN_FIGURA`, `_escala` a 1000/ancho, conf 0–100, orden H/S, caja 80×120 → `w=125`, `h=188`, `solo_verticales`. |
| `tests/test_filtros.py` | 8 | `es_vertical` (80×120 sí; 120×80 no; 100×100 no; umbral exacto) y `solo_verticales`. |
| `tests/test_enlace.py` | 14 | ACK solo tras PUBACK, sin PUBACK sin ACK, reintento idéntico sin republicar, misma secuencia con otro contenido se reenvía, JSON inválido/no objeto descartado, secuencia numérica en texto, qos 0 en ACK y visión, cola llena, `cerrar()`. |
| `tests/test_simulador.py` | 9 | Argumentos por defecto y personalizados, puerto inválido, duración/periodo 0, latencia sin reintentos, latencia tras dos reintentos, ACK con otra secuencia y `ok` falso. |
| **Total** | **47** | Suite completa en ~2,5 s. |

### Verificaciones de T7

- `python -m unittest discover -s tests -v`: 47 tests, OK, ~2,5 s.
- Con `socket.connect`, `socket.connect_ex` y `socket.create_connection` bloqueados: 47 tests, OK (ninguna red).
- Tres ejecuciones con el orden de las pruebas mezclado (semillas 1, 2 y 3): 47 tests, OK en cada una.
- No se modificó código de producción, `config.py`, `firmware/` ni archivos de T8; no se encontraron bugs nuevos.

### Huecos de cobertura de T7

- `main.py` (pipeline completo y sus decisiones).
- `stream/recibir.py` y la cámara real.
- paho/MQTT reales, PUBACK real y reconexión.
- Ruta real de `logica/iot.py`.
- Detectores de color/YOLO y su morfología en línea.
- Bucle de conexión real de `tools/simular_robot.py`.
- Firmware y JSON oficial del servidor.

---

## 10. Decisiones de T8 — limpieza

| # | Decisión | Motivo |
|---|---|---|
| T8-1 | Se borran `logica/cuadrante.py`, `logica/calibrar_piso.py` y `logica/contador.py` tras confirmación explícita del usuario. | D1–D12: la laptop no calcula cuadrante ni cuenta víctimas; esas funciones viven en el robot. |
| T8-2 | Antes de borrar se buscaron imports y referencias en todo el repo. El único import real era `logica/calibrar_piso.py:7 → logica.cuadrante` (entre dos archivos que se borran juntos). | No dejar imports colgantes ni romper código en uso. |
| T8-3 | `config.py` no se modificaba en T8: `CONFIRMA_FRAMES` y `PISO_JSON` solo los usaban los tres módulos borrados y sus comentarios quedaban obsoletos. | Condición 2 del pedido T8; el cambio no era necesario entonces. **Actualizado en el ajuste posterior**: sin usos en código/tests/tools, se eliminaron la cabecera legada y las dos constantes. |
| T8-4 | Las apariciones de `cuadrantes` en `main.py`, `tests/test_enlace.py` y `tools/simular_robot.py` son el campo JSON del reporte, no imports de módulos; se conservan. | Forman parte del protocolo robot → laptop → servidor. |
| T8-5 | No se toca `README.md`; sus referencias a los módulos se corrigen en T9. | Condición 3 del pedido. |

### Verificación de T8

- `python -m unittest discover -s tests -v`: **47 tests, OK, ~2,6 s**, `exit=0`.
- `python -m py_compile main.py config.py logica/*.py tools/simular_robot.py`:
  **11 archivos, `exit=0`**. En PowerShell el glob `logica/*.py` se pasó explícito
  porque PowerShell no lo expande para comandos nativos.
- Sin imports ni referencias de código a los módulos borrados.
- Residuos: `.pyc` huérfanos en `logica/__pycache__` (`cuadrante`, `calibrar_piso`,
  `contador`) y comentarios de `config.py:97-98`. No son código ejecutable ni
  permiten importar los módulos.

---

## 11. Contradicciones detectadas (no resueltas en silencio)

| # | Documento | Dice | Contradice a | Estado |
|---|---|---|---|---|
| C1 | `README.md` §1 y §8 | "Laptop = cerebro": visión, cuadrantes, conteo e IoT en la laptop. | D8, D9 (robot cuenta y calcula cuadrante) | **Resuelto en T9 (2026-11-09)**: §1 y §8 dicen que la laptop detecta y reenvía; el robot cuenta y decide. |
| C2 | `README.md` §7 | El cuadrante se lee por cámara mirando el color del piso. | D5 (TCS34725 por I2C) | **Resuelto en T9 (2026-11-09)**: §7 lo asigna al TCS34725 del robot. |
| C3 | `README.md` §8 | "El JSON lo envía la laptop" y la laptop lo construye con el conteo propio. | D2 (el robot arma el JSON; la laptop lo reenvía tal cual) | **Resuelto en T9 (2026-11-09)**: §8 dice que el robot arma el JSON y la laptop lo reenvía. |
| C4 | Firmware, línea 22 (nota de v3.2) | "Borde negro: desactivado". | Encabezado v3.4, línea 5, y D10: borde negro **activo** con 2 lecturas seguidas. | Avisado; el firmware no se toca. |
| C5 | Firmware, líneas 232 y 965 | `figsX[16]` / `figsY[16]` y límite `nFigs < 16`. | D11: 24 X (6 por cuadrante). | Limitación del firmware; avisada. No se modifica. |
| C6 | Firmware, líneas 121–122 | `DEDUP_MM = 150` y `DEDUP_MAX_CM = 150`: figuras a menos de 15 cm se consideran la misma. | 24 X con 6 por cuadrante en 1 m × 1 m (separación posible menor a 15 cm). | Avisado; medir en la pista antes de confiar en el deduplicado. |
| C7 | Documentos pedidos | Faltaba `CONTEXTO_OPENCODE_v2.md`; solo existía `CONTEXTO_OPENCODE_v2 (1).md`. | El nombre exacto que se pidió leer. | Resuelto el 2026-11-09: el usuario renombró el archivo. |
| C8 | `CONTEXTO_OPENCODE_v2.md`, línea 7 | Dice que la v2 sustituye a `ACTUALIZACION_CONTEXTO_OPENCODE.md`. | `ACTUALIZACION_CONTEXTO_OPENCODE.md`, línea 3: dice que ella prevalece. | Avisado; el usuario indicó que prevalece la actualización. |
| C9 | `CONTEXTO_OPENCODE_v2.md`, línea 9, y `ACTUALIZACION_CONTEXTO_OPENCODE.md`, línea 136 | Dicen que el firmware no está en el repositorio. | `firmware/` existe localmente (sin seguimiento en git). | Avisado; no se modifica. |
| C10 | Firmware, línea 239 | `secuencia = 0` en RAM, sin NVS: se reinicia al arrancar el robot. | La deduplicación por número en la laptop. | Resuelto en T2-5 con huella de contenido; el firmware no se toca. |
| C11 | `ACTUALIZACION_CONTEXTO_OPENCODE.md` §5 | Dice que el firmware vigente es v3.3, con borde negro desactivado y 16 puntos. | El archivo local es v3.4, con borde activo y 24 X (v2 y encabezado del firmware). | Avisado; se usa el v3.4 local como referencia. |
| C12 | v2 §4 y la instrucción de T6 | Dicen "reenviar máximo 2 veces" (envío inicial + 2 reenvíos = 3 transmisiones). | Firmware v3.4, líneas 116 y 914: `MAX_ENVIOS = 2` da envío inicial + 1 reenvío (2 transmisiones). | Avisado; el simulador usa 2 reintentos según la instrucción, pero no replica el límite real del firmware. |
| C13 | `CONTEXTO_OPENCODE_v2.md` T9 e instrucción de T9 | La v2 numera §5 = D1–D12, §6 = TCS34725, §8 = día del evento y §10 = bitácora; la instrucción pide ejecución/topics en §5–§6. | El README real tiene §5 = calibración de color, §6 = ruta YOLO, §7 = cuadrante, §8 = decisiones/MQTT, §9 = hoja de ruta + día del evento y §12 = bitácora. | Avisado; T9 se aplicó por contenido, sin renumerar secciones. |
| C14 | `README.md` §2 | "Estado actual" todavía describía el cuadrante por color de piso y el flujo con conteo en la laptop. | §1, §7 y §8 nuevos (T9) y D8/D9. | **Resuelto en el ajuste posterior (2026-11-09)**: §2 reescrito con cuadrante/conteo en el robot y flujo v2. |

---

## 12. Datos pendientes de la organización (v2 §9)

1. Coordenadas exactas de las **24 X**.
2. **Formato oficial del JSON** del servidor.
3. **Host, puerto y tema** del servidor.
4. **Credenciales** del broker, si las pide.
5. **Límite de tiempo** del intento (el firmware usa 470 s provisionales).
6. Si la laptop puede enviar detecciones al robot sin que cuente como control
   remoto.
7. **Nombres de los cuadrantes** en el servidor.

Mientras falten, se usan valores provisionales marcados `TODO`. No se inventan.

---

## 13. Estado de las tareas

| Tarea | Estado |
|---|---|
| T1 · `config.py` | Hecha y confirmada (2026-11-09). |
| T3 · `logica/vision_robot.py` | Hecha y confirmada (2026-11-09). |
| T5 · `logica/iot.py` | Hecha (2026-11-09). Probada sin broker; falta validarla con broker real. |
| T2 · `logica/robot_mqtt.py` | Hecha (2026-11-09). Probada con `iot` falso y con paho falso; falta extremo a extremo con broker real. |
| T4 · `main.py` | Hecha (2026-11-09). Probada con cámara/detector/enlace falsos; falta cámara y broker reales. |
| T6 · `tools/simular_robot.py` | Hecha (2026-11-09). Probada con cliente y reloj falsos; falta Mosquitto real y la prueba junto a `main.py`. |
| T7 · `tests/` | Hecha (2026-11-09). 47 tests en verde (~2,5 s), sin red y estables en orden aleatorio. |
| T8 · Limpieza | Hecha (2026-11-09). Borrados `cuadrante.py`, `calibrar_piso.py` y `contador.py`; 47 tests y `py_compile` en verde. |
| T9 · `README.md` | Hecha (2026-11-09). §1, §3, §5, §6, §8, §9, §10 y §12 actualizadas; sin referencias a los módulos retirados. Quedan TODO: host/puerto/tema del servidor y coordenadas de las 24 X. |
