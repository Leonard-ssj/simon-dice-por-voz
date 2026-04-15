# ============================================================
# config.py — Configuración central del servidor
# ============================================================

# ─── Puerto Serial ────────────────────────────────────────────────────────────
# "auto" detecta automáticamente el primer ESP32/CH340/CP210x conectado.
# Si hay varios dispositivos, especifica el puerto exacto:
#   Windows: "COM3", "COM4", ...
#   Linux:   "/dev/ttyUSB0", "/dev/ttyACM0"
#   macOS:   "/dev/cu.usbserial-..."
SERIAL_PORT = "auto"
BAUD_RATE   = 921600

# ─── Modelo Whisper ───────────────────────────────────────────────────────────
# El modelo se descarga automáticamente en ~/.cache/whisper/ la primera vez.
#
#   "tiny"   (~39MB)  — 0.5-1s CPU,   peor calidad
#   "base"   (~74MB)  — 1-2s CPU,     buena calidad  ← fallback en CPU lenta
#   "small"  (~244MB) — 3-8s CPU,     mejor calidad  ← recomendado
#   "medium" (~769MB) — 5-15s CPU,    muy buena      ← solo si tienes GPU NVIDIA
#
# Con GPU NVIDIA (CUDA) el modelo small tarda ~0.5s → cambiar fp16=True en whisper_engine.py
WHISPER_MODEL = "small"

# ─── WebSocket ────────────────────────────────────────────────────────────────
# Puerto en el que el servidor escucha conexiones del panel web.
# El web-panel debe apuntar a ws://localhost:8765
WS_HOST = "localhost"
WS_PORT = 8766   # Puerto del Servidor PC (ESP32). El simulador usa 8765 — así no chocan.

# ─── Audio ────────────────────────────────────────────────────────────────────
SAMPLE_RATE  = 8000    # Hz del ESP32 (definido en proyecto.ino)
WHISPER_SR   = 16000   # Hz que Whisper requiere internamente

# ─── Tonos del juego (Hz) ─────────────────────────────────────────────────────
VOLUMEN_TONOS = 0.3    # 0.0 – 1.0

# ─── Juego ────────────────────────────────────────────────────────────────────
TIMEOUT_RESPUESTA = 60000   # ms — tiempo por turno para responder (60s para CPUs lentas con Whisper small)
DURACION_LED_SIM  = 800     # ms — tiempo que cada LED permanece encendido
PAUSA_ENTRE_LEDS  = 300     # ms — pausa entre LEDs al mostrar la secuencia
NIVEL_INICIAL     = 1
MAX_NIVEL         = 20

# ─── Whisper ──────────────────────────────────────────────────────────────────
# Tiempo máximo que Whisper puede tardar antes de descartar el audio.
# Si la transcripción supera este límite, se pide al usuario que hable de nuevo.
WHISPER_TIMEOUT = 10   # segundos

# ─── Debug ────────────────────────────────────────────────────────────────────
DEBUG = True   # muestra logs detallados en la terminal
