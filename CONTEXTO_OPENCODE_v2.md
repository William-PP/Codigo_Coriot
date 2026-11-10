# CONTEXTO PARA OPENCODE · Código Rescate (CORIOT GAMES 2026) · v2

**Fecha:** 2026-11-09
**Repositorio:** `github.com/William-PP/Codigo_Coriot`
**Evento:** 12 de noviembre de 2026, Auditorio Pedro Nel Gómez, Campus Robledo.

Este documento reemplaza a `CONTEXTO_OPENCODE.md` y a `ACTUALIZACION_CONTEXTO_OPENCODE.md`. Si el README o `Contexto.txt` contradicen algo de aquí, avisa antes de cambiarlo. El README está desactualizado en la parte de arquitectura.

El firmware del robot (`firmware_robot_v3_4_esp32.ino`) es la referencia del comportamiento del robot. Se entrega junto con este documento y no forma parte del repositorio todavía.

---

## 1. Reglas del reglamento que no se pueden romper

- **100 % autónomo.** Prohibido el control manual, la observación humana remota y las cámaras externas suspendidas sobre la pista.
- **Cómputo off-board permitido** en una laptop conectada por red privada inalámbrica.
- **El robot reporta por Wi-Fi** un JSON con conteos de H (naranja) y S (morado) por cuadrante.
- **Reportar antes de derribar.** Tras publicar la víctima, el robot la derriba. El derribo es la confirmación física. No se manipula, sujeta ni transporta la figura.
- **No mover ni orillar obstáculos.** Penaliza.
- **Si el tiempo se agota,** solo cuentan los reportes recibidos y validados con derribo.
- **Dimensiones del robot:** máximo 13 × 18 × 20 cm.

---

## 2. Pista (tabla oficial)

| Elemento | Especificación |
|---|---|
| Área total | 2,00 m × 2,00 m, plana |
| Cuadrantes | 4 de 1,00 m × 1,00 m: **rojo y azul** arriba; **verde y amarillo** abajo |
| Límite exterior | **Borde negro bajo y visible** |
| Zona de inicio | Rectángulo **START** en la esquina inferior izquierda del cuadrante verde |
| Obstáculos (edificios) | 12, de unos 15 cm de lado y 20 cm de alto. **Posición variable según el montaje.** |
| Posiciones de víctimas | **24**, marcadas con una X, **6 por cuadrante** |
| Víctimas por prueba | **12**, 3 por cuadrante |

**Coordenadas de referencia** (mm, origen en la esquina inferior izquierda):

| Cuadrante | Centro aprox. |
|---|---|
| Verde (inferior izquierda) | (500, 500) |
| Amarillo (inferior derecha) | (1500, 500) |
| Rojo (superior izquierda) | (500, 1500) |
| Azul (superior derecha) | (1500, 1500) |

START: (100, 100), en el cuadrante verde.

**Pendiente:** las coordenadas exactas de las 24 X. Se miden en la pista. **No inventar valores.** Usar `TODO`.

---

## 3. Decisiones de arquitectura (vigentes)

| # | Tema | Decisión |
|---|---|---|
| D1 | Visión | **Laptop** con el celular (IP Webcam) como cámara. Detecta H y S con YOLO o color. |
| D2 | JSON al servidor | **La laptop** lo envía al servidor. El robot arma el JSON y lo manda a la laptop por el broker en un tema privado. La laptop lo reenvía tal cual. |
| D3 | Derribo | **Lo decide el robot** con sus sensores. La laptop no envía órdenes de derribo. |
| D4 | Confirmación antes del derribo | La laptop responde **ACK** al robot solo después de que el servidor confirmó el mensaje (PUBACK qos 1). **Sin ACK no hay derribo.** |
| D5 | Color de piso | **TCS34725 por I2C** en el robot. Detecta cuadrante y borde negro. |
| D6 | Distancia | **3 HC-SR04** (frente, izquierda, derecha). |
| D7 | Motores | **2 DRV8871** alimentados directo de la LiPo 2S. Sin buck de 6 V. |
| D8 | Cuadrante | Lo calcula el **robot** con el TCS34725. La laptop no calcula cuadrante. |
| D9 | Conteo | Lo lleva el **robot** (heridos y suministros por cuadrante, solo con derribo confirmado). La laptop solo reenvía. |
| D10 | Borde negro | **ACTIVO.** El límite exterior es negro. Lo prohibido es la línea guía **interior**. |
| D11 | Escaneo | **24 X** (6 por cuadrante), no 16. |
| D12 | Navegación | **Reactiva.** No hay mapa fijo de obstáculos, porque su posición depende del montaje. |

---

## 4. Qué hace cada parte

**El robot (firmware) decide y ejecuta:**
- Navegación entre las 24 X, escaneo 360°, acercamiento, centrado, derribo y verificación.
- Detección de borde negro, atasco y batería baja.
- Arma el reporte y lo envía a la laptop.
- No derriba sin ACK.

**La laptop hace cuatro cosas:**
1. Detecta H y S con la cámara del celular y envía la línea de visión al robot.
2. Recibe el reporte del robot y lo reenvía al servidor.
3. Responde el ACK solo después de la confirmación del servidor.
4. Muestra el video y el último reporte en pantalla.

**La laptop NO hace:** navegación, escaneo, conteo, cuadrante ni derribo. Por eso `logica/contador.py`, `logica/cuadrante.py` y `logica/calibrar_piso.py` salen del flujo.

---

## 5. Flujo del robot (v2)

```
INICIO
  │
  ▼
[1] ESPERAR ARRANQUE
    Pulsar el botón una vez. Calibrar giroscopio.
    Confirmar que el sensor ve VERDE. Iniciar cronómetro.
  │
  ▼
[2] BUSCAR
    Ir a la X sin revisar más cercana, prefiriendo cuadrantes sin revisar.
    Evitar obstáculos con los tres ultrasonidos.

    ¿Figura confirmada (5 de los últimos 7 frames)?
      SÍ → ¿ya contada en esa posición?
             NO → ir a [4]
             SÍ → seguir buscando
    ¿Cambió el color del piso?  → actualizar cuadrante
    ¿Borde negro (2 lecturas seguidas)? → retroceder, girar al centro, seguir
    ¿Atascado?                  → retroceder, girar, seguir
    ¿Llegó a la X?              → ir a [3]
  │
  ▼
[3] ESCANEAR (en cada X)
    Girar 360° en 12 pasos con pausa en cada uno.
    ¿Figura confirmada? → ir a [4]
    Al terminar: marcar la X como revisada.
    ¿Las 6 X del cuadrante están revisadas? → marcar el cuadrante como revisado.
    Volver a [2].
  │
  ▼
[4] ACERCARSE
    Centrar la figura en la imagen. Avanzar mientras se ve.
    ¿Figura perdida más de 1 s?                  → volver a [2]
    ¿Obstáculo frente sin figura?                 → rodear, volver a [2]
    ¿Distancia frontal ≤ 6 cm y figura centrada?  → ir a [5]
  │
  ▼
[5] REPORTAR
    Enviar a la laptop el reporte con la secuencia.
    La laptop reenvía al servidor y responde ACK.
    ¿ACK recibido (8 s)?
      SÍ → ir a [6]
      NO → reenviar con la misma secuencia (máximo 2 veces)
           ¿Sigue sin ACK? → NO derribar. Descartar y volver a [2].
  │
  ▼
[6] DERRIBAR
    Mover el servo para tumbar la figura.
    Verificar con la cámara si cayó.
    ¿Sigue en pie?
      SÍ y golpes < 3 → otro golpe
      SÍ y golpes = 3 → descartar y volver a [2]
      NO → contar en el cuadrante, enviar reporte actualizado,
           retroceder y girar, volver a [2]
  │
  ▼
[7] TERMINAR
    Se activa desde cualquier paso al cumplirse el tiempo
    o si la batería baja del umbral mínimo.
    Detener motores, servo a reposo, enviar reporte final.
    Apagar con el interruptor.
```

---

## 6. Protocolo de mensajes

Broker MQTT: **por confirmar.** Mientras tanto, se usa el broker local de pruebas (`config.BROKER_HOST`). Los valores de la competencia van en `config.py`, no en el código.

### 6.1 Temas

| Tema | Dirección | Contenido | Publica | Suscribe |
|---|---|---|---|---|
| `coriot/vision/E01` | laptop → robot | Línea de detección (§6.2) | Laptop, a la frecuencia de frames (máx. 15 Hz) | Robot |
| `coriot/robot/E01/reporte` | robot → laptop | JSON del robot (§6.3) | Robot | Laptop |
| `coriot/robot/E01/ack` | laptop → robot | `{"secuencia": N, "ok": true}` | Laptop | Robot |
| Servidor de la competencia | laptop → servidor | JSON reenviado tal cual | Laptop | Servidor |

> El tema del servidor **no está confirmado.** Usar `SERVIDOR_TEMA = "coriot/reporte"` como valor provisional, marcado con `TODO`.

### 6.2 Línea de visión (laptop → robot)

Una línea CSV por frame, sin salto final:

```
D,v,c,x,w,h,conf
```

| Campo | Rango | Significado |
|---|---|---|
| `D` | fijo | Cabecera |
| `v` | 0 o 1 | 1 = figura detectada, 0 = ninguna |
| `c` | `H` o `S` | Clase |
| `x` | 0–1000 | Centro horizontal de la caja. 500 = centro del frame |
| `w` | 0–1000 | Ancho de la caja |
| `h` | 0–1000 | Alto de la caja |
| `conf` | 0–100 | Confianza. YOLO entrega 0–1: multiplicar por 100 |

**Reglas de escala (importantes):**
- `x`, `w` y `h` usan **la misma escala** para conservar la proporción: `factor = 1000 / ancho_frame`.
- Enviar **una línea por frame**, incluso sin figura (`D,0,H,500,0,0,0`). El robot considera la visión caída si no recibe líneas en 1 s.
- Si hay H y S en el mismo frame, enviar dos líneas (máximo una por clase).

### 6.3 Reporte del robot (robot → laptop)

```json
{
  "equipo": "E01",
  "intento": "I1",
  "secuencia": 12,
  "estado": "en_curso",
  "cuadrantes": [
    {"color": "rojo", "explorado": true, "heridos": 1, "necesitan_suministros": 0},
    {"color": "azul", "explorado": false, "heridos": null, "necesitan_suministros": null},
    {"color": "verde", "explorado": true, "heridos": 0, "necesitan_suministros": 2},
    {"color": "amarillo", "explorado": false, "heridos": null, "necesitan_suministros": null}
  ]
}
```

- `estado`: `en_curso` o `final`.
- `secuencia`: sube en cada reporte nuevo. Los reintentos usan la **misma** secuencia.
- **La laptop no modifica este JSON.** La conversión, si el servidor pide otro formato, va en **una sola función** (`formatear_para_servidor`).

### 6.4 ACK (laptop → robot)

Después de que el servidor confirma el mensaje:

```json
{"secuencia": 12, "ok": true}
```

- Si el reenvío falla, **no** enviar ACK. El robot reintenta y, sin ACK, no derriba.
- Si llega un reporte con una `secuencia` ya reenviada, **reenviar el ACK** sin volver a publicar en el servidor.

---

## 7. Estado del repositorio

### 7.1 Lo que sirve tal cual
- `stream/recibir.py`, `stream/capturar.py`
- `logica/deteccion_color.py`, `logica/deteccion_yolo.py`
- `logica/filtros.py` (figura de pie: `alto >= 1.2 × ancho`, coincide con el firmware)
- `modelo/*` (entrenar, evaluar, revisar dataset)

### 7.2 Lo que cambia

| Archivo | Problema | Acción |
|---|---|---|
| `main.py` | Calcula conteo y publica su propio JSON | Reescribir el flujo (T4) |
| `logica/contador.py` | Cuenta en la laptop | Quitar del flujo. Solo para diagnóstico si el usuario lo pide |
| `logica/cuadrante.py`, `logica/calibrar_piso.py` | Cuadrante por cámara | Quitar del flujo. Eliminar en la limpieza, con confirmación |
| `logica/iot.py` | Tema fijo `BROKER_TEMA` | Recibir el tema como parámetro (T5) |
| `config.py` | Broker mezclado, `USAR_CUADRANTE`, IP fija en `FUENTE_VIDEO` | Reorganizar (T1) |
| `README.md` | Arquitectura antigua | Actualizar (T9) |

### 7.3 Lo que falta
- Módulo de comunicación con el robot (T2).
- Línea de visión (T3).
- Pruebas automáticas del protocolo y del filtro vertical (T7).
- Simulador del robot para probar la laptop sin hardware (T6).
- Carpeta `firmware/robot_esp32/` con el firmware v3.4. La agrega el usuario; **no modificar el firmware desde OpenCode.**

---

## 8. Tareas para OpenCode (en orden)

Trabajar **una tarea a la vez.** Al terminar cada una, mostrar qué cambió y cómo probarla.

**T1 · `config.py`**
- Separar la configuración del broker.
- Constantes: `ROBOT_ID = "E01"`, `TEMA_VISION`, `TEMA_REPORTE_ROBOT`, `TEMA_ACK_ROBOT`, `SERVIDOR_TEMA` (provisional, `TODO`).
- Constantes de la pista: `CUADRANTES` con sus centros (§2), `START = (100, 100)`, `PUNTOS_X_TOTAL = 24`, `PUNTOS_POR_CUADRANTE = 6`, `VICTIMAS_POR_PRUEBA = 12`.
- `FUENTE_VIDEO` a variable de entorno con valor por defecto.
- `BROKER_CLIENTE = "laptop-E01"`, distinto del ID del robot.
- *Aceptación:* `python -c "import config; print(config.TEMA_VISION)"` imprime el tema correcto.

**T2 · `logica/robot_mqtt.py` (nuevo)** · clase `EnlaceRobot`
- Conecta al mismo broker. Suscribe a `TEMA_REPORTE_ROBOT`.
- Al recibir un reporte: parsear. Si es inválido, descartarlo y registrar el error. Si la `secuencia` ya se reenvió, reenviar solo el ACK. Si no, publicar en `SERVIDOR_TEMA` con `formatear_para_servidor` y qos 1, esperar `wait_for_publish(timeout=5)`. Si se confirmó, publicar el ACK. Si no, no publicar ACK.
- Método `enviar_vision(linea)` con qos 0 en `TEMA_VISION`.
- Reconexión automática. Nunca bloquear el bucle de visión.
- *Aceptación:* con un broker local y el simulador (T6), el ACK sale solo después del PUBACK.

**T3 · `logica/vision_robot.py` (nuevo)**
- `linea_vision(detecciones, ancho_frame)` según §6.2.
- Sin detecciones: `D,0,H,500,0,0,0`.
- Por clase, la detección de mayor confianza. `conf` de 0–1 a 0–100.
- Misma escala para `x`, `w` y `h`: `factor = 1000 / ancho_frame`. Redondear a enteros.
- *Aceptación:* caja de 80×120 px en un frame de 640 px → `w = 125`, `h = 188` (proporción 1.5), y el firmware la acepta como figura de pie.

**T4 · `main.py`**
```
stream → detector → filtro vertical → línea de visión → robot
robot → reporte → formatear → servidor → ACK → robot
```
- Enviar la línea de visión en cada frame.
- Quitar el conteo y la publicación del JSON propio. Quitar `cargar_cuadrante`.
- Mostrar el último reporte del robot y su secuencia.
- *Aceptación:* arranca aunque el broker no responda, muestra video y no se cae.

**T5 · `logica/iot.py`**
- Tema como parámetro obligatorio en `publicar(reporte, tema)`.
- Devolver `True` solo si el PUBACK llegó (hoy devuelve `True` al encolar).
- *Aceptación:* devuelve `False` si el broker no está.

**T6 · `tools/simular_robot.py` (nuevo)**
- Publica un reporte con `secuencia` creciente cada 5 s en `TEMA_REPORTE_ROBOT`.
- Escucha `TEMA_ACK_ROBOT` e imprime si llegó el ACK.
- Escucha `TEMA_VISION` e imprime las líneas recibidas.

**T7 · `tests/` con unittest (biblioteca estándar)**
- `test_vision_robot.py`: formato, escala, conversión de `conf`, caso sin detecciones.
- `test_filtros.py`: 80×120 sí; 120×80 no; 100×100 no.
- `test_enlace.py`: el ACK sale solo tras confirmar el envío.
- No agregar `pytest` sin actualizar `Requirements.txt`.

**T8 · Limpieza** (con confirmación del usuario antes de borrar)
- Quitar `cuadrante.py`, `calibrar_piso.py` y `contador.py` del flujo.

**T9 · README**
- Actualizar §1, §3, §5 (decisiones D1–D12), §6 (calibración del TCS34725 en el robot, no con la cámara), §8 (día del evento), §9 (hoja de ruta), §10 (bitácora con fecha 2026-11-09).

---

## 9. Pendientes que solo confirma la organización

1. **Coordenadas exactas de las 24 X.** Se miden en la pista.
2. **Formato oficial del JSON** del servidor.
3. **Host, puerto y tema** del servidor.
4. **Credenciales** del broker, si las pide.
5. **Límite de tiempo** del intento. El firmware usa 470 s como valor provisional. La tabla no lo indica.
6. **Si la laptop puede enviar detecciones al robot** por red privada sin contar como control remoto.
7. **Nombres de los cuadrantes** en el servidor.

Hasta tener estos datos, usar valores provisionales marcados con `TODO`. No inventar.

---

## 10. Hardware de referencia (lista vigente)

- ESP32 DevKit (1 + 1 de repuesto)
- 2 motorreductores N20 de 6 V con encoder (100–150 RPM), llantas de 43 mm, apoyo pasivo
- 2 drivers DRV8871
- LiPo 2S (1000–2200 mAh, 15–20 C), cargador balanceador
- Buck 5 V (sensores, servo)
- Interruptor general, botón START en GPIO0
- Capacitores 470 µF y 100 nF; resistencias: pull-up 10 kΩ en encoders, divisor de batería 20 kΩ/10 kΩ, divisores de ECHO
- TCS34725 (I2C), 3 HC-SR04, MPU-6050 (I2C), servo SG90 o MG90S
- Celular con IP Webcam, soporte, power bank
- Chasis de máximo 13 × 18 × 20 cm

Pines del firmware: ver el encabezado de `firmware_robot_v3_4_esp32.ino`.

---

## 11. Reglas de trabajo con el usuario

- Responder y escribir comentarios en **español**.
- **Un paso a la vez.** Explicar los comandos antes de ejecutarlos.
- No agregar dependencias sin actualizar `Requirements.txt` y el README.
- **No hacer commit ni push** sin pedirlo.
- Antes de borrar archivos, preguntar.
- Si una decisión de §3 parece incorrecta, avisar y esperar confirmación. No cambiarla en silencio.
- Si falta un dato de §9, usar `TODO`, no inventarlo.
- No modificar el firmware desde OpenCode.

---

## 12. Primer encargo

> Lee `README.md`, `Contexto.txt`, este documento y el firmware v3.4. Confirma en una lista corta qué hace la laptop, qué hace el robot y qué cambió respecto al README. Señala contradicciones sin resolverlas en silencio. Luego haz T1 y T3, y presenta el plan de T2, T4 y T5 antes de tocarlos.
