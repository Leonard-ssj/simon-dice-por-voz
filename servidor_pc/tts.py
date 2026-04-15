# ============================================================
# tts.py — Narrador TTS + tonos del juego (laptop)
#
# Toda la salida de audio del presentador sale por la laptop.
# El ESP32 NO reproduce TTS — toda la salida de audio es por la laptop.
#
# TTS — cascada de prioridades:
#   1. edge-tts + pygame  → voz neural es-MX-DaliaNeural (requiere internet)
#   2. PowerShell SAPI    → voz española instalada en Windows (sin internet)
#
# Instalar para máxima calidad:
#   pip install edge-tts pygame
# ============================================================

import asyncio
import io
import subprocess
import threading
import time
import queue
import numpy as np
import sounddevice as sd

from config import SAMPLE_RATE, VOLUMEN_TONOS, DEBUG

# ─── Importar edge-tts / pygame si están disponibles ─────────────────────────
try:
    import edge_tts as _edge_tts_mod
    _EDGE_TTS_OK = True
    EDGE_TTS_VOZ = "es-MX-DaliaNeural"
except ImportError:
    _EDGE_TTS_OK = False
    EDGE_TTS_VOZ = ""

try:
    import pygame as _pygame
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

# ─── Frecuencias de los tonos del juego ──────────────────────────────────────
_FREQ_COLOR = {
    "ROJO":     262,   # Do4
    "VERDE":    330,   # Mi4
    "AZUL":     392,   # Sol4
    "AMARILLO": 494,   # Si4
}

_FREQ_ESPECIAL = {
    "correcto": [1047, 1319],          # Do6–Mi6 ascendente
    "error":    [196, 165],            # Sol3–Mi3 descendente (grave)
    "inicio":   [262, 330, 392, 523],  # Do-Mi-Sol-Do fanfarria
    "gameover": [523, 440, 349, 262],  # Do-La-Fa-Do descendente
}

# ─── Cola y estado del hilo TTS ──────────────────────────────────────────────
_tts_queue:  queue.Queue      = queue.Queue()
_tts_listo   = threading.Event()
_tts_activo  = threading.Event()   # set mientras el worker está hablando o hay items en cola
_voz_nombre  = ""
_usar_edge   = False
_edge_loop: asyncio.AbstractEventLoop | None = None


# ─── Detección de voz SAPI en español ────────────────────────────────────────

def _detectar_voz_espanol() -> str:
    patrones = [
        "es-mx", "es-es", "es-us", "es-ar",
        "sabina", "helena", "pablo", "jorge", "maria",
        "spanish", "español", "espanol",
        "mstts_v110_esmx", "mstts_v110_eses",
    ]
    try:
        import pyttsx3
        engine = pyttsx3.init()
        for voice in engine.getProperty("voices"):
            vid = voice.id.lower()
            vnm = voice.name.lower()
            if any(p in vid or p in vnm for p in patrones):
                print(f"[TTS] Voz SAPI en español: {voice.name}")
                try:
                    engine.stop()
                except Exception:
                    pass
                return voice.name
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as e:
        if DEBUG:
            print(f"[TTS] No se pudo detectar voces: {e}")
    return ""


def _nombre_corto(nombre: str) -> str:
    """Extrae el nombre personal de la voz para SelectVoice de PowerShell."""
    excluir = {"microsoft", "desktop", "mobile", "online", "speech", "neural"}
    for palabra in nombre.split():
        limpia = palabra.strip("(),-.").lower()
        if limpia not in excluir and limpia and palabra[0].isupper():
            return palabra.strip("(),-.")
    return nombre


# ─── Backends de TTS ─────────────────────────────────────────────────────────

def _hablar_powershell(texto: str):
    """Habla con SAPI via PowerShell. Bloquea hasta que termina."""
    safe = texto.replace('"', "'")
    voz_cmd = ""
    if _voz_nombre:
        nc = _nombre_corto(_voz_nombre)
        voz_cmd = (
            f'try {{ $s.SelectVoice("{nc}") }} '
            f'catch {{ try {{ $s.SelectVoice("{_voz_nombre}") }} catch {{}} }}; '
        )
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"{voz_cmd}"
        "$s.Rate = -1; "
        f'$s.Speak("{safe}")'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        if DEBUG:
            print(f"[TTS] Timeout: {texto!r}")
    except Exception as e:
        if DEBUG:
            print(f"[TTS] Error PowerShell: {e}")


async def _edge_generar_mp3(texto: str) -> bytes:
    communicate = _edge_tts_mod.Communicate(texto, EDGE_TTS_VOZ)
    data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return data


def _hablar_edge(texto: str):
    """Habla con Microsoft Edge TTS Neural. Bloquea hasta que termina."""
    global _edge_loop
    try:
        if _edge_loop is None or _edge_loop.is_closed():
            _edge_loop = asyncio.new_event_loop()
        mp3_data = _edge_loop.run_until_complete(_edge_generar_mp3(texto))
        mp3_io = io.BytesIO(mp3_data)
        _pygame.mixer.music.load(mp3_io, "mp3")
        _pygame.mixer.music.play()
        while _pygame.mixer.music.get_busy():
            time.sleep(0.05)
    except Exception as e:
        if DEBUG:
            print(f"[TTS] edge-tts error: {e} — usando SAPI")
        _hablar_powershell(texto)


# ─── Hilo TTS ─────────────────────────────────────────────────────────────────

def _tts_worker():
    global _voz_nombre, _usar_edge, _edge_loop

    _voz_nombre = _detectar_voz_espanol()

    if _EDGE_TTS_OK and _PYGAME_OK:
        try:
            _pygame.mixer.init()
            _edge_loop = asyncio.new_event_loop()
            _usar_edge = True
            print(f"[TTS] Edge TTS activo — voz neural: {EDGE_TTS_VOZ}")
        except Exception as e:
            print(f"[TTS] Edge TTS no disponible ({e}), usando SAPI")
    else:
        if not _EDGE_TTS_OK:
            print("[TTS] Tip: instala 'edge-tts pygame' para voz neural mexicana")

    _tts_listo.set()

    while True:
        texto = _tts_queue.get()
        if texto is None:
            break
        _tts_activo.set()
        try:
            if _usar_edge:
                _hablar_edge(texto)
            else:
                _hablar_powershell(texto)
        except Exception as e:
            if DEBUG:
                print(f"[TTS] Error inesperado: {e}")
        finally:
            _tts_queue.task_done()
            if _tts_queue.empty():
                # Buffer de eco: esperar 0.6s después de que el narrador termina.
                # El sonido del altavoz de la laptop tarda ~0.3-0.5s en disiparse.
                # Sin este buffer, el micrófono MAX4466 puede capturar el eco y
                # Whisper lo transcribe como un comando (ej: "Ba-ra-ve" en lugar de
                # el silencio esperado). Solo se aplica si la cola sigue vacía.
                time.sleep(0.6)
                if _tts_queue.empty():
                    _tts_activo.clear()


# ─── API pública ─────────────────────────────────────────────────────────────

def inicializar_tts():
    """Lanza el hilo de TTS. Llamar una sola vez al inicio."""
    t = threading.Thread(target=_tts_worker, daemon=True, name="tts")
    t.start()


def esperar_tts(timeout: float = 5.0) -> bool:
    """Bloquea hasta que el motor TTS esté listo."""
    return _tts_listo.wait(timeout=timeout)


def tts_hablando() -> bool:
    """True si el narrador está hablando, tiene items pendientes, o está en buffer de eco."""
    return _tts_activo.is_set() or not _tts_queue.empty()


def cancelar_tts():
    """
    Vacía la cola del TTS inmediatamente. Los items pendientes no se hablan.
    Usar en REINICIAR, STOP o desconexión del panel para que el narrador
    no siga hablando del estado anterior del juego.
    """
    vaciados = 0
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
            _tts_queue.task_done()
            vaciados += 1
        except Exception:
            break
    _tts_activo.clear()
    if vaciados and DEBUG:
        print(f"[TTS] Cola cancelada ({vaciados} items descartados)")


def decir(texto: str, bloquear: bool = True):
    """Encola texto para ser hablado. bloquear=True espera a que termine."""
    if not _tts_listo.is_set():
        return
    _tts_activo.set()   # marcar como activo antes de encolar (evita ventana entre put y get)
    _tts_queue.put(texto)
    if bloquear:
        _tts_queue.join()
        if _tts_queue.empty():
            _tts_activo.clear()


_NOMBRES_COLOR = {
    "ROJO":     "rojo",
    "VERDE":    "verde",
    "AZUL":     "azul",
    "AMARILLO": "amarillo",
}


def decir_color(color: str):
    """Dice el nombre del color en voz alta (bloqueante)."""
    decir(_NOMBRES_COLOR.get(color, color.lower()), bloquear=True)


# ─── Tonos del juego ──────────────────────────────────────────────────────────

def _generar_tono(hz: float, ms: int) -> np.ndarray:
    t    = np.linspace(0, ms / 1000, int(SAMPLE_RATE * ms / 1000), endpoint=False)
    tono = np.sin(2 * np.pi * hz * t).astype(np.float32)
    fade = int(SAMPLE_RATE * 0.01)
    if len(tono) > 2 * fade:
        tono[:fade]  *= np.linspace(0, 1, fade)
        tono[-fade:] *= np.linspace(1, 0, fade)
    return tono * VOLUMEN_TONOS


def reproducir_tono(hz: float, ms: int):
    sd.play(_generar_tono(hz, ms), samplerate=SAMPLE_RATE)
    sd.wait()


def reproducir_sonido(tipo: str, extra: str = None):
    """
    Reproduce el sonido de un evento del juego.
    tipo: "color" | "correcto" | "error" | "inicio" | "gameover"
    extra: nombre del color si tipo="color"
    """
    if tipo == "color" and extra:
        hz = _FREQ_COLOR.get(extra.upper(), 440)
        reproducir_tono(hz, 400)

    elif tipo in _FREQ_ESPECIAL:
        for hz in _FREQ_ESPECIAL[tipo]:
            reproducir_tono(hz, 150 if tipo != "error" else 250)
            time.sleep(0.04 if tipo != "error" else 0.08)
