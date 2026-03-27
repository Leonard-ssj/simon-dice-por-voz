#!/usr/bin/env python3
# ============================================================
# servidor_voz/main.py — Servidor de voz para modo ESP32
#
# Responsabilidad única: capturar micrófono de la PC y
# transcribir con Whisper local. Sin lógica de juego.
#
# El panel web se conecta en modo Serial al ESP32 (juego) y
# en modo WebSocket aquí (solo voz). Cuando el jugador pulsa
# PTT en el browser:
#   1. Browser → Serial → ESP32: "PTT_INICIO\n" (pausa timeout)
#   2. Browser → WS aquí: {"tipo":"control","accion":"PTT_INICIO"}
#      → este servidor abre el micrófono de la PC
#   3. Jugador habla
#   4. Browser → WS aquí: {"tipo":"control","accion":"PTT_FIN"}
#      → cierra mic, transcribe con Whisper, envía resultado
#   5. Browser recibe: {"tipo":"voz","texto":"rojo","comando":"ROJO"}
#   6. Browser → Serial → ESP32: "PTT_FIN\n" + "ROJO\n"
#
# Uso:
#   cd servidor_voz
#   pip install -r requirements.txt
#   python main.py
# ============================================================

import sys
import os
import asyncio
import json
import threading
import unicodedata
import re
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

import websockets
from config_voz import WS_HOST, WS_PORT, SAMPLE_RATE, WHISPER_MODEL, DEBUG

# ---- Grabación de micrófono ----

try:
    import sounddevice as sd
    SOUNDDEVICE_OK = True
except Exception:
    SOUNDDEVICE_OK = False

_grabando       = False
_frames_audio   = []
_stream_mic     = None
_lock_mic       = threading.Lock()


def _callback_mic(indata, frames, time_info, status):
    """Acumula frames de audio mientras se graba."""
    if _grabando:
        _frames_audio.append(indata.copy())


def abrir_mic() -> bool:
    global _grabando, _frames_audio, _stream_mic
    if not SOUNDDEVICE_OK:
        return False
    with _lock_mic:
        _frames_audio = []
        _grabando     = True
        try:
            _stream_mic = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=_callback_mic,
                blocksize=4096,
            )
            _stream_mic.start()
            if DEBUG:
                print(f"  [Mic] Grabando en {sd.query_devices(kind='input')['name']}")
            return True
        except Exception as e:
            _grabando = False
            print(f"  [Mic] Error al abrir: {e}")
            return False


def cerrar_mic() -> np.ndarray:
    global _grabando, _stream_mic
    with _lock_mic:
        _grabando = False
        if _stream_mic:
            try:
                _stream_mic.stop()
                _stream_mic.close()
            except Exception:
                pass
            _stream_mic = None
        if not _frames_audio:
            return np.array([], dtype=np.float32)
        return np.concatenate(_frames_audio, axis=0).flatten()


# ---- Whisper ----

_whisper_model   = None
_whisper_ok      = False
_whisper_modelo  = WHISPER_MODEL
_dispositivo_mic = "N/A"

# Prompt que mejora el reconocimiento del vocabulario del juego
_INITIAL_PROMPT = (
    "ROJO VERDE AZUL AMARILLO "
    "empieza para stop pausa repite reiniciar"
)

# Variantes fonéticas (espejo de validador.py)
_VARIANTES = {
    "ROJO":      ["ROJO", "ROJA", "ROXO", "RONJO", "ROCO", "ROSO"],
    "VERDE":     ["VERDE", "BERDE", "BERDI", "VERD", "ERDE", "BIRDE"],
    "AZUL":      ["AZUL", "ASUL", "AZUR", "ASOR", "ASUR"],
    "AMARILLO":  ["AMARILLO", "AMARILLA", "AMARIJO", "MARILLO", "AMARILO", "MARRILLO"],
    "START":     ["START", "EMPIEZA", "INICIA", "COMIENZA", "JUGAR", "ARRANCA",
                  "EMPEZAR", "INICIAR", "COMENZAR", "JUEGA", "EMPIEZE"],
    "STOP":      ["STOP", "PARA", "PARAR", "TERMINA", "FIN", "SALIR",
                  "TERMINAR", "DETENTE", "ALTO"],
    "PAUSA":     ["PAUSA", "PAUSAR", "ESPERA", "ESPERAR"],
    "REPITE":    ["REPITE", "REPETIR", "REPITA", "REPITELO", "REPITELA"],
    "REINICIAR": ["REINICIAR", "REINICIA", "RESET", "VOLVER", "REINICIATE"],
}

_FRASES = {"OTRA VEZ": "REPITE", "DE NUEVO": "REPITE"}

_MAPA: dict[str, str] = {}
for _cmd, _vars in _VARIANTES.items():
    for _v in _vars:
        _MAPA[_v] = _cmd


def _normalizar(texto: str) -> str:
    texto = texto.upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^A-Z0-9 ]", "", texto)
    return texto.strip()


def _texto_a_comando(texto: str) -> str:
    if not texto:
        return "DESCONOCIDO"
    norm = _normalizar(texto)
    if not norm:
        return "DESCONOCIDO"
    if norm in _MAPA:
        return _MAPA[norm]
    for frase, cmd in _FRASES.items():
        if frase in norm:
            return cmd
    palabras = norm.split()
    if len(palabras) <= 3:
        for p in palabras:
            if p in _MAPA:
                return _MAPA[p]
    return "DESCONOCIDO"


def cargar_whisper() -> bool:
    global _whisper_model, _whisper_ok, _dispositivo_mic
    try:
        import whisper
        print(f"  Cargando Whisper '{WHISPER_MODEL}'...")
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        _whisper_ok    = True
        print(f"  Whisper '{WHISPER_MODEL}' listo.")
    except Exception as e:
        print(f"  [Whisper] No disponible: {e}")
        _whisper_ok = False

    if SOUNDDEVICE_OK:
        try:
            _dispositivo_mic = sd.query_devices(kind="input")["name"]
        except Exception:
            _dispositivo_mic = "desconocido"

    return _whisper_ok


def transcribir(audio_np: np.ndarray) -> tuple[str, str]:
    """Transcribe audio PCM Float32 16kHz. Retorna (texto_crudo, comando)."""
    if not _whisper_ok or _whisper_model is None:
        return "", "DESCONOCIDO"
    if len(audio_np) < SAMPLE_RATE * 0.1:   # < 0.1s
        return "", "DESCONOCIDO"
    try:
        import whisper
        resultado = _whisper_model.transcribe(
            audio_np,
            language="es",
            initial_prompt=_INITIAL_PROMPT,
            fp16=False,
        )
        texto   = resultado.get("text", "").strip()
        comando = _texto_a_comando(texto)
        return texto, comando
    except Exception as e:
        print(f"  [Whisper] Error: {e}")
        return "", "DESCONOCIDO"


# ---- Servidor WebSocket ----

async def _manejar_cliente(websocket):
    addr = websocket.remote_address
    print(f"  [WS] Cliente conectado: {addr}")

    # Enviar mensaje READY
    await websocket.send(json.dumps({
        "tipo":              "ready",
        "whisperDisponible": _whisper_ok,
        "whisperModelo":     _whisper_modelo if _whisper_ok else None,
        "dispositivoMic":   _dispositivo_mic,
    }))

    try:
        async for mensaje in websocket:
            try:
                datos = json.loads(mensaje)
            except Exception:
                continue

            tipo = datos.get("tipo")

            if tipo == "control":
                accion = datos.get("accion")

                if accion == "PTT_INICIO":
                    if DEBUG:
                        print("  [WS] PTT_INICIO recibido")
                    ok = abrir_mic()
                    await websocket.send(json.dumps({
                        "tipo": "ptt_estado",
                        "estado": "grabando" if ok else "error_mic",
                    }))

                elif accion == "PTT_FIN":
                    if DEBUG:
                        print("  [WS] PTT_FIN recibido — transcribiendo...")
                    audio_np = cerrar_mic()
                    texto, comando = transcribir(audio_np)
                    if DEBUG:
                        print(f'  [WS] "{texto}" → {comando}')
                    await websocket.send(json.dumps({
                        "tipo":    "voz",
                        "texto":   texto,
                        "comando": comando,
                    }))

            elif tipo == "ping":
                await websocket.send(json.dumps({"tipo": "pong"}))

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        print(f"  [WS] Error con cliente {addr}: {e}")
    finally:
        # Cerrar mic si el cliente se desconecta mientras grababa
        cerrar_mic()
        print(f"  [WS] Cliente desconectado: {addr}")


async def _iniciar_servidor():
    async with websockets.serve(_manejar_cliente, WS_HOST, WS_PORT):
        print(f"  Servidor de voz escuchando en ws://{WS_HOST}:{WS_PORT}")
        await asyncio.Future()  # corre indefinidamente


# ---- Main ----

def main():
    print("\n" + "=" * 55)
    print("  SIMON DICE — Servidor de Voz (modo ESP32)")
    print("=" * 55)
    print("  Convierte PTT del browser en comandos via Whisper.")
    print(f"  WebSocket: ws://{WS_HOST}:{WS_PORT}")
    print("=" * 55 + "\n")

    cargar_whisper()

    try:
        asyncio.run(_iniciar_servidor())
    except KeyboardInterrupt:
        print("\n  Servidor detenido.\n")


if __name__ == "__main__":
    main()
