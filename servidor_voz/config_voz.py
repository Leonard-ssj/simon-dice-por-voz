# ============================================================
# config_voz.py — Configuración del servidor de voz
# Solo reconocimiento de voz (Whisper). Sin lógica de juego.
# ============================================================

# WebSocket — el panel web se conecta aquí para PTT
WS_HOST = "localhost"
WS_PORT = 8766          # distinto a 8765 del simulador

# Reconocimiento de voz
SAMPLE_RATE  = 16000    # Hz — INMP441 y Whisper usan 16kHz

# Modelo Whisper local
#   "tiny"   (~39MB)  — 0.5-1s CPU  ← más rápido
#   "base"   (~74MB)  — 1-2s CPU    ← buena calidad
#   "small"  (~244MB) — 3-8s CPU    ← mejor calidad (igual que el browser)
WHISPER_MODEL = "small"

# Debug — muestra logs internos
DEBUG = True
