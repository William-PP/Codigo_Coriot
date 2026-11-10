"""GUI de operación de la laptop (CORIOT GAMES 2026 - Código Rescate).

Solo controla procesos de la laptop y publica la configuración retenida.
Nunca envía órdenes de movimiento, arranque ni parada al robot.
"""

import json
import threading
import time

import config
import main

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:  # pragma: no cover
    tk = None

try:
    from paho.mqtt import client as mqtt
    PAHO_OK = True
except Exception:
    PAHO_OK = False

TEMA_CONFIG = "coriot/robot/E01/config"


def publicar_config(equipo, intento, host=None, port=None, usuario=None, password=None, timeout=5.0):
    """Publica {"equipo","intento"} retenido (qos 1) en TEMA_CONFIG.

    Devuelve (ok, mensaje). No envía ninguna orden de movimiento/arranque/parada.
    """
    equipo = (equipo or "").strip()
    intento = (intento or "").strip()
    if not equipo or not intento:
        return False, "equipo e intento son obligatorios"

    if not PAHO_OK:
        return False, "falta paho-mqtt (pip install -r Requirements.txt)"

    host = host or config.BROKER_HOST
    port = port if port is not None else config.BROKER_PORT
    usuario = usuario if usuario is not None else config.BROKER_USUARIO
    password = password if password is not None else config.BROKER_PASSWORD

    payload = json.dumps({"equipo": equipo, "intento": intento}, ensure_ascii=False)

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="laptop-gui-E01")
    if usuario:
        cliente.username_pw_set(usuario, password)

    resultado = {"ok": False, "msg": "sin respuesta", "conectado": False, "publicado": False, "info": None}

    def on_connect(client, userdata, flags, reason, props):
        valor = getattr(reason, "value", reason)
        if valor != 0:
            resultado["msg"] = "no se pudo conectar ({})".format(reason)
            resultado["conectado"] = True
            return
        resultado["conectado"] = True
        info = client.publish(TEMA_CONFIG, payload, qos=1, retain=True)
        resultado["info"] = info

    cliente.on_connect = on_connect
    try:
        cliente.loop_start()
        cliente.connect_async(host, port, keepalive=30)
        fin = time.monotonic() + timeout + 2
        while time.monotonic() < fin and not resultado["conectado"]:
            time.sleep(0.05)
        fin2 = time.monotonic() + timeout + 2
        while time.monotonic() < fin2:
            info = resultado.get("info")
            if info is not None and info.is_published():
                resultado["ok"] = True
                resultado["publicado"] = True
                resultado["msg"] = "publicado retenido en {}: {}".format(TEMA_CONFIG, payload)
                break
            if "conectar" in resultado["msg"] or "publicado" in resultado["msg"]:
                break
            time.sleep(0.05)
        if not resultado["ok"] and resultado["msg"] == "sin respuesta":
            resultado["msg"] = "sin PUBACK (tiempo agotado)"
        cliente.loop_stop()
        cliente.disconnect()
    except Exception as error:
        resultado["msg"] = "error de conexion: {}".format(error)
        try:
            cliente.loop_stop()
            cliente.disconnect()
        except Exception:
            pass
    return resultado["ok"], resultado["msg"]


def _servidor_configurado():
    host = (config.BROKER_HOST or "").strip()
    tema = (config.SERVIDOR_TEMA or "").strip()
    if not host or host == "127.0.0.1":
        return False
    if not tema:
        return False
    return True


class Aplicacion:
    def __init__(self, root):
        self.root = root
        self.root.title("Código Rescate - Laptop")
        self.root.geometry("520x460")

        self.estado = None
        self.pipeline_corriendo = False

        # Identidad
        frm_id = ttk.LabelFrame(root, text="Identidad del intento")
        frm_id.pack(fill="x", padx=10, pady=5)
        ttk.Label(frm_id, text="Equipo:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.entry_equipo = ttk.Entry(frm_id, width=30)
        self.entry_equipo.grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(frm_id, text="Intento:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.entry_intento = ttk.Entry(frm_id, width=30)
        self.entry_intento.grid(row=1, column=1, padx=5, pady=2)
        ttk.Label(frm_id, text="Fuente de video (URL o índice):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.entry_fuente = ttk.Entry(frm_id, width=30)
        self.entry_fuente.insert(0, "0")
        self.entry_fuente.grid(row=2, column=1, padx=5, pady=2)

        # Botones
        frm_btn = ttk.Frame(root)
        frm_btn.pack(fill="x", padx=10, pady=5)
        self.btn_preparar = ttk.Button(frm_btn, text="Preparar", command=self.preparar)
        self.btn_preparar.pack(side="left", padx=5)
        self.btn_detener = ttk.Button(frm_btn, text="Detener", command=self.detener, state="disabled")
        self.btn_detener.pack(side="left", padx=5)

        # Indicadores
        frm_ind = ttk.LabelFrame(root, text="Indicadores en vivo")
        frm_ind.pack(fill="x", padx=10, pady=5)
        self.lbl_camara = ttk.Label(frm_ind, text="Cámara: sin señal")
        self.lbl_camara.pack(anchor="w", padx=5)
        self.lbl_broker = ttk.Label(frm_ind, text="Broker local: desconocido")
        self.lbl_broker.pack(anchor="w", padx=5)
        self.lbl_servidor = ttk.Label(frm_ind, text="Enlace al servidor: TODO")
        self.lbl_servidor.pack(anchor="w", padx=5)
        self.lbl_robot = ttk.Label(frm_ind, text="Robot: sin reporte")
        self.lbl_robot.pack(anchor="w", padx=5)
        self.lbl_vision = ttk.Label(frm_ind, text="Visión: 0 líneas/s")
        self.lbl_vision.pack(anchor="w", padx=5)

        # Aviso de servidor no configurado
        if not _servidor_configurado():
            self.lbl_aviso_servidor = ttk.Label(root, text="AVISO: endpoint del servidor no configurado (TODO). No se enviarán reportes al servidor.", foreground="red")
            self.lbl_aviso_servidor.pack(fill="x", padx=10, pady=2)
        else:
            self.lbl_aviso_servidor = None

        # Último reporte
        frm_rep = ttk.LabelFrame(root, text="Último reporte (solo lectura)")
        frm_rep.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_reporte = tk.Text(frm_rep, height=8, state="disabled", wrap="word")
        self.txt_reporte.pack(fill="both", expand=True, padx=5, pady=5)

        # Panel de avisos
        frm_av = ttk.LabelFrame(root, text="Avisos")
        frm_av.pack(fill="x", padx=10, pady=5)
        self.txt_avisos = tk.Text(frm_av, height=4, state="disabled", wrap="word")
        self.txt_avisos.pack(fill="x", padx=5, pady=5)

        self._actualizar()

    def _log(self, msg):
        if self.txt_avisos is not None:
            self.txt_avisos.config(state="normal")
            self.txt_avisos.insert("end", "{} {}\n".format(time.strftime("%H:%M:%S"), msg))
            self.txt_avisos.see("end")
            self.txt_avisos.config(state="disabled")

    def preparar(self):
        equipo = self.entry_equipo.get().strip()
        intento = self.entry_intento.get().strip()
        fuente = self.entry_fuente.get().strip()
        if not equipo or not intento:
            messagebox.showwarning("Faltan datos", "Equipo e intento son obligatorios.")
            self._log("Aviso: equipo e intento son obligatorios.")
            return

        self._log("Publicando configuración retenida...")
        self.btn_preparar.config(state="disabled")
        self.root.update_idletasks()

        def tarea():
            ok, msg = publicar_config(equipo, intento)
            self.root.after(0, lambda: self._log(("OK: " if ok else "ERROR: ") + msg))
            if ok:
                self.estado = main.iniciar_pipeline(equipo=equipo, intento=intento, mostrar=False, fuente_video=fuente)
                self.pipeline_corriendo = True
                self.root.after(0, self._on_pipeline_iniciado)
            else:
                self.root.after(0, lambda: self.btn_preparar.config(state="normal"))

        threading.Thread(target=tarea, daemon=True).start()

    def _on_pipeline_iniciado(self):
        self.btn_detener.config(state="normal")
        self._log("Pipeline iniciado.")

    def detener(self):
        self._log("Deteniendo pipeline...")
        self.btn_detener.config(state="disabled")
        def tarea():
            main.detener_pipeline(self.estado)
            self.pipeline_corriendo = False
            self.estado = None
            self.root.after(0, self._on_pipeline_detenido)
        threading.Thread(target=tarea, daemon=True).start()

    def _on_pipeline_detenido(self):
        self.btn_preparar.config(state="normal")
        self._log("Pipeline detenido.")

    def _actualizar(self):
        est = self.estado
        if est is not None:
            self.lbl_camara.config(text="Cámara: {}".format("conectada" if est.camera_ok else "sin señal"))
            self.lbl_broker.config(text="Broker local: {}".format("conectado" if est.broker_ok else "no conectado"))
            self.lbl_servidor.config(text="Enlace al servidor: {}".format(est.server_link))
            if est.last_seq is not None:
                hora = time.strftime("%H:%M:%S", time.localtime(est.last_report_time)) if est.last_report_time else "-"
                self.lbl_robot.config(text="Robot: seq {} a las {}".format(est.last_seq, hora))
            else:
                self.lbl_robot.config(text="Robot: sin reporte")
            self.lbl_vision.config(text="Visión: {} líneas/s".format(est.vision_rate()))
            # último reporte
            if est.last_report is not None:
                try:
                    texto = json.dumps(est.last_report, ensure_ascii=False, indent=2)
                except Exception:
                    texto = str(est.last_report)
                self.txt_reporte.config(state="normal")
                self.txt_reporte.delete("1.0", "end")
                self.txt_reporte.insert("end", texto)
                self.txt_reporte.config(state="disabled")
            # avisos del pipeline
            for ts, nivel, msg in est.snapshot_avisos():
                # solo los nuevos: comparar por longitud guardada
                pass
            # drenar avisos nuevos
            if not hasattr(self, "_avisos_vistos"):
                self._avisos_vistos = 0
            avisos = est.snapshot_avisos()
            if len(avisos) > self._avisos_vistos:
                for ts, nivel, msg in avisos[self._avisos_vistos:]:
                    self._log("[{}] {}".format(nivel, msg))
                self._avisos_vistos = len(avisos)
        else:
            self.lbl_camara.config(text="Cámara: -")
            self.lbl_broker.config(text="Broker local: -")
            self.lbl_servidor.config(text="Enlace al servidor: -")
            self.lbl_robot.config(text="Robot: sin reporte")
            self.lbl_vision.config(text="Visión: 0 líneas/s")

        self.root.after(500, self._actualizar)


def main():
    if tk is None:
        print("tkinter no disponible")
        return
    root = tk.Tk()
    app = Aplicacion(root)
    root.mainloop()


if __name__ == "__main__":
    main()
