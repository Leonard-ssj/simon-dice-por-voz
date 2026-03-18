# ============================================================
# config_test.py — Configuración del simulador de PC
# Solo aplica al modo TEST. No afecta el código de producción.
# ============================================================

# WebSocket — el panel se conecta aquí
WS_HOST = "localhost"
WS_PORT = 8765

# Audio del sistema (sounddevice — solo para reproducción de tonos)
SAMPLE_RATE = 16000   # Hz

# Tonos del juego
VOLUMEN_TONOS = 0.3   # 0.0–1.0

# Simulación de LEDs en terminal
USAR_COLORES_ANSI = True

# Modelo Whisper local para reconocimiento de voz.
# El modelo se descarga automáticamente la primera vez a ~/.cache/whisper/
#
#   "tiny"   (~39MB)  — 0.5-1s CPU,  peor calidad
#   "base"   (~74MB)  — 1-2s CPU,    buena calidad  ← más rápido en laptop sin GPU
#   "small"  (~244MB) — 3-8s CPU,    mejor calidad  ← mismo que el navegador usa
#   "medium" (~769MB) — 5-15s CPU,   muy buena      ← solo si tienes GPU NVIDIA
#
# Con GPU NVIDIA (CUDA): small/medium tardan 0.3-1s → usar fp16=True en ws_server.py
# Sin GPU (CPU solamente): recomendar "base" para evitar timeouts frecuentes
WHISPER_MODEL = "small"

# Configuración del juego
# TIMEOUT_RESPUESTA: tiempo que el jugador tiene para hablar.
# Whisper local pausa el timer mientras transcribe, así que el timeout solo cuenta
# el tiempo que el jugador tarda en presionar PTT y hablar.
TIMEOUT_RESPUESTA  = 30000  # ms — 30s cubre incluso modelos lentos en CPU
DURACION_LED_SIM   = 800    # ms por LED en la secuencia
PAUSA_ENTRE_LEDS   = 300    # ms entre LEDs
NIVEL_INICIAL      = 1
MAX_NIVEL          = 20

# Debug — muestra logs internos del simulador
DEBUG = True
