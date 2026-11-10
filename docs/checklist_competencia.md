# Checklist de competencia - Código Rescate (CORIOT GAMES 2026)

## Orden de encendido
1. Laptop encendida, sesión iniciada.
2. Broker Mosquitto local corriendo en 127.0.0.1:1883 (servicio de Windows).
3. app_gui.py abierto; verificar indicadores.
4. Celular con IP Webcam activo; anotar la URL del stream.
5. Robot encendido (botón físico). No enviar órdenes desde la laptop.

## Si la IP del celular cambió
- No editar config.py.
- En la GUI, campo "Fuente de video": pegar la nueva URL (http://IP:8080/video)
  o el índice de cámara ("0").
- O usar la variable de entorno CORIOT_VIDEO antes de arrancar.

## Si no hay conexión al servidor
- La GUI muestra aviso en rojo: "endpoint del servidor no configurado".
- No se envían reportes al servidor; el robot no recibe ACK y no derriba.
- Verificar BROKER_HOST, SERVIDOR_TEMA y credenciales en config.py (TODO).
- No inventar valores: usar los que dé la organización.

## Antes del intento
- [ ] Python 3.12 y .venv activos.
- [ ] Mosquitto corriendo (verificar_laptop.ps1 en verde).
- [ ] Pesos del modelo presentes (yolo11n.pt y rescate.pt si aplica).
- [ ] Tests en verde: python -m unittest discover -s tests -v.
- [ ] Equipo e intento cargados en la GUI.
- [ ] Pulsar "Preparar" (publica config retenida + arranca pipeline).
- [ ] Confirmar indicadores: cámara, broker, enlace.

## Durante el intento
- El único arranque del equipo es el botón del robot.
- Apagar el robot = parada (termina el intento).
- Reiniciar conteos = apagar y encender (RAM se pierde, secuencia sigue en NVS).
- La laptop solo detecta y reenvía; no cuenta ni calcula cuadrantes.

## Entrenamiento: mínimo de datos y tiempo medido

- **Validación mínima para confiar en el mAP:** 30 imágenes y al menos **10 instancias por clase** (H y S).
  Con menos, `modelo/entrenar.py` reporta `mAP50: NO CONFIABLE` y no aplica el umbral 0.70.
- **Medición local** (laptop de desarrollo, CPU Intel i5-12400F, sin GPU; 300 train + 60 val,
  640 px, lote 8, 3 épocas):

  | Época | Tiempo |
  |---|---:|
  | 1 | 72.8 s |
  | 2 | 68.0 s |
  | 3 | 64.3 s |
  | **Total 3 épocas** | **215.5 s (3.59 min)** |
  | **Proyección 30 épocas** | **2062.1 s (34.4 min)** |

- **Recomendación para el día:** `--epocas 30 --tiempo 40 --dispositivo cpu`.
  Son 40 min de tope, con ~5.6 min de margen sobre la proyección medida.
  Si el dataset supera ~300 imágenes, el tiempo crece casi linealmente: recalcular o bajar `--imgsz`.
  La proyección **no incluye** captura ni etiquetado.

## Cronograma oficial del día (reglamento §8)

- **9:30–10:10 Inspección técnica**: demostrar el modelo (entradas, salidas, registro de inferencias en `logs/`).
- **Antes de 10:10**: capturar figuras, etiquetar, entrenar `rescate.pt` y verificar con `verificar_laptop.ps1`. El tiempo de entrenamiento debe tener límite para no pasar de 11:50.
- **10:10–11:50**: pruebas libres con el robot (2 turnos de 5 min).
- **12:50–13:00**: montaje de la pista (primera combinación).
- **13:00–14:30**: competencia oficial ronda 1.
- **14:35–16:05**: competencia oficial ronda 2.

Comandos del día:
- Captura: `$env:CORIOT_VIDEO = "http://IP:8080/video"; python -m stream.capturar`
  (o `python -m stream.capturar --fuente "http://IP:8080/video"`).
- Entrenamiento: `python -m modelo.entrenar --epocas 30 --tiempo 40 --dispositivo cpu`
- Verificación: `scripts\verificar_laptop.ps1`