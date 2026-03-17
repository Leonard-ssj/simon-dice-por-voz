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

# Configuración del juego
# TIMEOUT_RESPUESTA: tiempo que el jugador tiene para hablar.
# Considera: latencia Whisper WASM (~2s) + tiempo para hablar (~1s) + margen
TIMEOUT_RESPUESTA  = 20000  # ms
DURACION_LED_SIM   = 800    # ms por LED en la secuencia
PAUSA_ENTRE_LEDS   = 300    # ms entre LEDs
NIVEL_INICIAL      = 1
MAX_NIVEL          = 20

# Debug — muestra logs internos del simulador
DEBUG = True
