# Código Rescate — CORIOT GAMES 2026

Robot autónomo para el reto **Código Rescate** de CORIOT GAMES 2026 (12 de noviembre de 2026, Auditorio Pedro Nel Gómez, Campus Robledo). Explora una pista de 2 × 2 m, clasifica víctimas **H** (heridas, naranja) y **S** (necesitan suministros, morado), reporta los conteos por cuadrante por MQTT y derriba cada figura como confirmación física.

## Instalación en la laptop

1. Instalar **Python 3.12** (no 3.15: PyTorch todavía no publica ruedas para esa versión).
2. Clonar el repositorio y entrar a la carpeta:

   ```powershell
   git clone https://github.com/William-PP/Codigo_Coriot.git
   cd Codigo_Coriot
   ```

3. Ejecutar el instalador:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\instalar_laptop.ps1
   ```

   El script crea `.venv`, instala las dependencias y verifica el entorno. Si existe `kit\wheels`, instala sin internet; si no, descarga las dependencias.

4. Copiar los pesos a `modelo\pesos\`:
   - `yolo11n.pt` (obligatorio).
   - `rescate.pt` (modelo entrenado; obligatorio para competir en modo `yolo`).

## Cómo abrir la GUI

```powershell
.\.venv\Scripts\python.exe app_gui.py
```

También se puede abrir con doble clic en `Iniciar_GUI.bat`.

La GUI tiene tres pestañas:

1. **Operación:** equipo, intento y fuente de video; botones Preparar y Detener; indicadores de cámara, broker, servidor, robot y visión.
2. **Captura de figuras:** guarda fotos de H, S y sin figura en una sesión.
3. **Entrenamiento:** entrena YOLO en segundo plano y copia el mejor modelo a `modelo\pesos\rescate.pt`.

## Verificación rápida

```powershell
scripts\verificar_laptop.ps1
python -m unittest discover -s tests -v
```

---

Lee `docs/PROYECTO.md` para todo lo demás: reglamento, arquitectura, decisiones, firmware, entrenamiento y día de la competencia.
