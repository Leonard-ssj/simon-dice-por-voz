# ============================================================
# serial_bridge.py — Puente Serial ↔ motor del juego
#
# Responsabilidades:
#   - Abrir/cerrar el puerto Serial del ESP32
#   - Leer líneas de texto y paquetes de audio binario
#   - Notificar al servidor cuando llega PTT_START, audio, etc.
#   - Enviar comandos al ESP32 (LED:, OLED:)
#   - Exponer iniciar_ptt_remoto() / detener_ptt_remoto() para el panel web
#
# Protocolo recibido del ESP32 (texto):
#   READY                → sistema listo
#   PTT_START            → grabación iniciada (botón físico)
#   PTT_STOP             → grabación detenida
#   AUDIO_CORTO          → grabación demasiado corta, descartada
#   AUDIO_START:N        → vienen N bytes de audio PCM int16 LE 8kHz
#   [N bytes]            → audio crudo (binario)
#   AUDIO_END            → fin del paquete de audio
#
# Protocolo enviado al ESP32 (texto):
#   R                    → iniciar grabación remota (PTT del panel)
#   T                    → detener grabación remota
#   LED:ROJO / LED:OFF   → color del LED activo
#   OLED:l1|l2|l3        → texto en OLED (| separa las 3 líneas)
# ============================================================

import serial
import serial.tools.list_ports
import threading
import time
import sys

from config import SERIAL_PORT, BAUD_RATE, DEBUG


def _encontrar_puerto() -> str:
    """
    Detecta automáticamente el primer puerto con ESP32/CH340/CP210x.
    Retorna el nombre del dispositivo (ej: "COM3", "/dev/ttyUSB0").
    """
    puertos = serial.tools.list_ports.comports()
    # Palabras clave comunes en los descriptores de adaptadores USB-Serial
    keywords = ["cp210", "ch340", "ch341", "ftdi", "uart", "usb serial", "esp", "silabs"]
    candidatos = [
        p.device for p in puertos
        if any(kw in (p.description or "").lower() for kw in keywords)
    ]
    if candidatos:
        return candidatos[0]
    # Sin detección específica: tomar el primero disponible
    todos = [p.device for p in puertos]
    if todos:
        print(f"[Serial] No se detectó ESP32 específico. Usando: {todos[0]}")
        return todos[0]
    raise RuntimeError(
        "[Serial] No se encontró ningún puerto serial.\n"
        "         Verifica que el ESP32 esté conectado por USB."
    )


class SerialBridge:
    """
    Puente asíncrono entre el ESP32 (Serial) y el motor del juego (Python).
    Corre un hilo de lectura en background que parsea el stream Serial.
    """

    def __init__(self):
        self._serial: serial.Serial | None = None
        self._hilo:   threading.Thread    | None = None
        self._activo  = False

        # ── Estado del buffer de audio ────────────────────────────────────────
        self._leyendo_audio       = False
        self._audio_bytes_esp     = 0        # bytes esperados
        self._audio_buffer        = bytearray()
        self._linea_buffer        = b""      # acumulador de líneas texto

        # ── Callbacks (asignar desde servidor.py) ─────────────────────────────
        self.on_ready:           callable | None = None   # ()
        self.on_ptt_start:       callable | None = None   # ()  → pausar timer
        self.on_ptt_stop:        callable | None = None   # ()
        self.on_audio_recibido:  callable | None = None   # (bytes pcm)
        self.on_audio_corto:     callable | None = None   # ()
        self.on_log:             callable | None = None   # (str)

        self._ready_event = threading.Event()

    # ── Conexión ──────────────────────────────────────────────────────────────

    def conectar(self, puerto: str = None) -> bool:
        """
        Abre el puerto Serial y lanza el hilo de lectura.
        Bloquea hasta recibir READY del ESP32 (timeout 10s).
        """
        if self._activo:
            return True

        puerto = puerto or (None if SERIAL_PORT == "auto" else SERIAL_PORT)
        if puerto is None:
            try:
                puerto = _encontrar_puerto()
            except RuntimeError as e:
                print(e)
                return False

        print(f"[Serial] Conectando a {puerto} @ {BAUD_RATE} baud...")
        try:
            self._serial = serial.Serial(puerto, BAUD_RATE, timeout=0.1)
        except serial.SerialException as e:
            print(f"[Serial] ERROR: {e}")
            print("         Cierra el Serial Monitor del Arduino IDE si está abierto.")
            return False

        self._activo = True
        self._ready_event.clear()

        # Limpiar basura del buffer ANTES de esperar al ESP32 (bytes de arranques previos)
        self._serial.reset_input_buffer()

        # Dar tiempo al ESP32 para resetear tras abrir el puerto (DTR toggling).
        # El ESP32 tarda ~2-3s en arrancar y enviar READY — NO limpiar el buffer aquí.
        time.sleep(0.2)

        # Lanzar hilo lector
        self._hilo = threading.Thread(target=self._hilo_lector, daemon=True, name="serial-reader")
        self._hilo.start()

        # Esperar READY del firmware
        if not self._ready_event.wait(timeout=10.0):
            print("[Serial] WARN: No llegó READY en 10s. Continuando de todas formas.")
        else:
            print("[Serial] ESP32 listo (READY recibido).")

        return True

    def desconectar(self):
        self._activo = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("[Serial] Desconectado.")

    # ── Hilo lector ───────────────────────────────────────────────────────────

    def _hilo_lector(self):
        """
        Lee el stream Serial en background.
        Alterna entre dos modos:
          - Texto: acumula bytes hasta '\n', procesa líneas
          - Binario: acumula exactamente N bytes del paquete de audio
        """
        while self._activo:
            try:
                chunk = self._serial.read(self._serial.in_waiting or 1)
            except Exception as e:
                if self._activo:
                    print(f"[Serial] Error de lectura: {e}")
                break

            if not chunk:
                continue

            # Procesar byte a byte para manejar la transición texto↔binario
            i = 0
            while i < len(chunk):
                byte = chunk[i:i+1]
                i += 1

                if self._leyendo_audio:
                    # ── Modo binario: acumular bytes del paquete de audio ─────
                    self._audio_buffer += byte
                    if len(self._audio_buffer) >= self._audio_bytes_esp:
                        # Paquete completo → disparar callback en hilo separado
                        self._leyendo_audio = False
                        audio_completo = bytes(self._audio_buffer)
                        if self.on_audio_recibido:
                            threading.Thread(
                                target=self.on_audio_recibido,
                                args=(audio_completo,),
                                daemon=True,
                                name="audio-proc",
                            ).start()
                else:
                    # ── Modo texto: acumular hasta '\n' ───────────────────────
                    if byte == b"\n":
                        linea = self._linea_buffer.decode("latin-1", errors="replace").strip()
                        self._linea_buffer = b""
                        if linea:
                            self._procesar_linea(linea)
                    elif byte != b"\r":
                        self._linea_buffer += byte

        if DEBUG:
            print("[Serial] Hilo lector terminado.")

    def _procesar_linea(self, linea: str):
        """Despacha una línea de texto recibida del ESP32."""
        if DEBUG:
            print(f"  [ESP32 →] {linea}")

        if linea == "READY":
            self._ready_event.set()
            if self.on_ready:
                self.on_ready()

        elif linea == "PTT_START":
            if self.on_ptt_start:
                self.on_ptt_start()

        elif linea == "PTT_STOP":
            if self.on_ptt_stop:
                self.on_ptt_stop()

        elif linea == "AUDIO_CORTO":
            if self.on_audio_corto:
                self.on_audio_corto()
            if self.on_log:
                self.on_log("PTT muy corto — habla más tiempo.")

        elif linea.startswith("AUDIO_START:"):
            try:
                n = int(linea.split(":")[1])
                if DEBUG:
                    duracion = n / (8000 * 2)
                    print(f"  [Serial] Recibiendo {n} bytes de audio ({duracion:.1f}s)...")
                self._audio_bytes_esp = n
                self._audio_buffer    = bytearray()
                self._leyendo_audio   = True
            except (ValueError, IndexError):
                print(f"[Serial] WARN: AUDIO_START malformado: {linea}")

        elif linea == "AUDIO_END":
            # El paquete ya fue procesado cuando se completaron los N bytes.
            # Esta línea es solo el terminador textual del ESP32.
            pass

        else:
            # Línea de log del firmware (Serial.printf durante tests, etc.)
            if self.on_log:
                self.on_log(f"[ESP32] {linea}")

    # ── Enviar comandos al ESP32 ───────────────────────────────────────────────

    def _enviar(self, texto: str):
        """Envía una línea de texto al ESP32. Thread-safe."""
        if not self._serial or not self._serial.is_open:
            return
        try:
            self._serial.write((texto + "\n").encode("utf-8"))
            if DEBUG:
                print(f"  [→ ESP32] {texto}")
        except serial.SerialException as e:
            print(f"[Serial] Error al enviar: {e}")

    def enviar_led(self, color: str):
        """Enciende el RGB con el color indicado. color="OFF" para apagar."""
        self._enviar(f"LED:{color.upper()}")

    def enviar_oled(self, l1: str = "", l2: str = "", l3: str = ""):
        """Actualiza el OLED con hasta 3 líneas de texto."""
        # Truncar a 21 chars (OLED 128px con textSize=1)
        l1 = str(l1)[:21]
        l2 = str(l2)[:21]
        l3 = str(l3)[:21]
        self._enviar(f"OLED:{l1}|{l2}|{l3}")

    # ── PTT remoto (desde el panel web vía spacebar) ───────────────────────────

    def iniciar_ptt_remoto(self):
        """
        Inicia grabación desde el panel web (spacebar).
        El ESP32 empezará a capturar audio y enviará PTT_START de vuelta.
        """
        if DEBUG:
            print("[Serial] PTT remoto: iniciando ('R')")
        try:
            if self._serial and self._serial.is_open:
                self._serial.write(b"R")
        except serial.SerialException as e:
            print(f"[Serial] Error enviando PTT remoto: {e}")

    def detener_ptt_remoto(self):
        """
        Detiene grabación desde el panel web (spacebar suelto).
        El ESP32 parará de capturar y enviará el audio.
        """
        if DEBUG:
            print("[Serial] PTT remoto: deteniendo ('T')")
        try:
            if self._serial and self._serial.is_open:
                self._serial.write(b"T")
        except serial.SerialException as e:
            print(f"[Serial] Error enviando stop PTT remoto: {e}")
