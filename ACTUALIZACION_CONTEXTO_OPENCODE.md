# ACTUALIZACIÓN 2026-11-09

**Este documento prevalece sobre `CONTEXTO_OPENCODE.md` y sobre el README donde se contradigan.**

---

## 1. Especificación de la pista (tabla oficial del reto)

| Elemento | Especificación |
|---|---|
| Área total | 2,00 m × 2,00 m, plana |
| Cuadrantes | 4 de 1,00 m × 1,00 m: **rojo y azul** en la fila superior; **verde y amarillo** en la inferior |
| Límite exterior | **Borde negro bajo y visible** |
| Zona de inicio | Rectángulo **START** en la esquina inferior izquierda del cuadrante verde |
| Obstáculos (edificios) | 12 en total, de unos 15 cm de lado y 20 cm de alto; **la posición depende de la configuración del montaje** |
| Posiciones de víctimas | **24**, marcadas con una X, **6 por cuadrante** |
| Víctimas por prueba | **12**, 3 por cuadrante |

### Coordenadas de referencia (mm, origen en la esquina inferior izquierda de la pista)

| Cuadrante | Posición | Centro aprox. |
|---|---|---|
| Verde | inferior izquierda | (500, 500) |
| Amarillo | inferior derecha | (1500, 500) |
| Rojo | superior izquierda | (500, 1500) |
| Azul | superior derecha | (1500, 1500) |

START: (100, 100), en el cuadrante verde.

---

## 2. Correcciones a decisiones anteriores

| Antes | Ahora | Motivo |
|---|---|---|
| **D10: borde negro desactivado** | **Borde negro ACTIVO.** El límite exterior es negro. Lo que está prohibido es la línea guía en el **interior** de la pista. | La tabla dice explícitamente "Límite exterior: borde negro bajo y visible". |
| 16 puntos de escaneo (4 por cuadrante) | **24 posiciones** (6 por cuadrante, marcadas con X) | La tabla dice 24 X y 6 por cuadrante. |
| Mapa fijo de obstáculos | **Sin mapa fijo.** Navegación reactiva con los 3 ultrasonidos | La posición de los edificios depende del montaje. |

---

## 3. Qué hace cada parte

**El robot (firmware) decide y ejecuta:**
- Navegación, escaneo 360°, acercamiento, centrado, derribo y verificación.
- Detección de borde negro, atasco y batería baja.
- Reporte: arma el JSON y lo envía a la laptop por MQTT.
- No derriba sin ACK.

**La laptop solo hace cuatro cosas:**
1. Detecta H y S con la cámara del celular (YOLO o color) y envía la línea de visión al robot.
2. Recibe el reporte del robot y lo reenvía al servidor de la competencia.
3. Responde el ACK al robot solo después de que el servidor confirmó el mensaje.
4. Muestra el video y el último reporte en pantalla.

**La laptop NO hace:** navegación, escaneo, conteo, cálculo de cuadrante ni derribo. Esto significa que `logica/contador.py`, `logica/cuadrante.py` y `logica/calibrar_piso.py` no forman parte del flujo.

---

## 4. Flujo del robot (v2, vigente)

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
    ¿Cambió el color del piso?  → actualizar cuadrante, marcarlo visitado
    ¿Borde negro?               → retroceder, girar al centro, seguir
    ¿Atascado?                  → retroceder, girar, seguir
    ¿Llegó a la X?              → ir a [3]
  │
  ▼
[3] ESCANEAR (en cada X)
    Girar 360° en 12 pasos con pausa en cada uno.
    ¿Figura confirmada? → ir a [4]
    Al terminar: marcar la X como revisada.
    ¿Están revisadas las 6 X del cuadrante? → marcar el cuadrante.
    Volver a [2].
  │
  ▼
[4] ACERCARSE
    Centrar la figura en la imagen. Avanzar mientras se ve.
    ¿Figura perdida más de 1 s?                 → volver a [2]
    ¿Obstáculo frente sin figura?                → rodear, volver a [2]
    ¿Distancia frontal ≤ 6 cm y figura centrada? → ir a [5]
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

**Reglas que no se rompen:**
- Reportar y recibir ACK antes de derribar.
- Una figura derribada no se vuelve a perseguir.
- El cronómetro se revisa en cada paso.

---

## 5. Firmware: estado

- El firmware v3.3 **tiene** `BORDE_NEGRO = false` y 16 puntos de escaneo. **Debe pasar a v3.4** con borde activo y 24 posiciones.
- El firmware **no está en el repositorio**. Los cambios a v3.4 los hace el usuario o se agregan después de crear `firmware/robot_esp32/`. **No modificar el firmware desde OpenCode sin confirmación.**

---

## 6. Pendientes que no se pueden decidir todavía

1. **Coordenadas de las 24 X** respecto a cada cuadrante. Se miden en la pista. **No inventar valores.** Usar `TODO` en el código.
2. **Formato oficial del JSON** del servidor.
3. **Host, puerto y tema** del servidor de la competencia.
4. **Límite de tiempo** del intento. La tabla no lo indica. El firmware usa 470 s como valor provisional.
5. **Si la laptop puede enviar detecciones al robot** por red privada sin contar como control remoto. Confirmar por escrito.

---

## 7. Qué debe hacer OpenCode ahora

1. Leer completos: `README.md`, `Contexto.txt`, `CONTEXTO_OPENCODE.md` y este documento.
2. Confirmar en una lista corta su entendimiento de: qué hace la laptop, qué hace el robot y qué cambió respecto al README.
3. Hacer **T1** (`config.py`) y **T3** (`logica/vision_robot.py`) de `CONTEXTO_OPENCODE.md`, con las constantes de la pista de la sección 1.
4. Antes de tocar `main.py` o `logica/iot.py`, presentar el plan de T2, T4 y T5 y esperar confirmación.
5. No tocar el firmware ni el flujo del robot.
6. Señalar cualquier contradicción que encuentre, en lugar de resolverla en silencio.
