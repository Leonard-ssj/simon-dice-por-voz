# ============================================================
# audio_pc.py — Tonos del juego + TTS
#
# Usado por el simulador (tests/simulador_pc/main.py).
# Reemplaza el hardware del ESP32 (MAX98357A speaker) en pruebas.
#
# Funciones:
#   reproducir_tono()    — genera y reproduce un tono con sounddevice
#   reproducir_sonido()  — tonos de eventos del juego (correcto, error, etc.)
#   decir() / decir_color() — narrador TTS con pyttsx3
#   inicializar_tts()    — arranca el hilo dedicado de TTS
#   esperar_tts()        — espera a que el motor TTS esté listo
#
# El reconocimiento de voz lo hace el browser (Whisper WASM).
# Este archivo NO contiene lógica de micrófono ni Whisper.
# ============================================================

import numpy as np
import sounddevice as sd
import sys
import os
import time
import queue
import threading

sys.path.insert(0, os.path.dirname(__file__))
from config_test import (
    SAMPLE_RATE,
    VOLUMEN_TONOS,
    DEBUG,
)

# Frecuencias de los tonos del juego (igual que sound_control.cpp del firmware)
FRECUENCIAS_COLOR = {
    "ROJO":     262,
    "VERDE":    330,
    "AZUL":     392,
    "AMARILLO": 494,
}

FRECUENCIAS_ESPECIALES = {
    "correcto": [1047, 1319],
    "error":    [196, 165],
    "inicio":   [262, 330, 392, 523],
    "gameover": [523, 440, 349, 262],
}


# ---- TTS (Text-to-Speech) ----
# Usa pyttsx3 para narrar el juego en voz alta.
# Corre en hilo propio para no bloquear sounddevice.

_tts_queue: queue.Queue = queue.Queue()
_tts_listo = threading.Event()   # se activa cuando el motor está inicializado


def _tts_worker():
    """Hilo dedicado al TTS. Lee la cola y habla uno a uno."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 130)      # velocidad de habla (palabras/min)
        engine.setProperty("volume", 0.95)

        # Buscar voz en español — patrones para Windows y otros sistemas
        PATRONES_ES = [
            "es-mx", "es-es", "es-us", "es-ar", "es-cl", "es-co",
            "es_mx", "es_es",
            "sabina", "helena", "pablo", "jorge", "maria",
            "spanish", "español", "espanol",
            "mstts_v110_eses", "mstts_v110_esmx",  # Windows OneCore
        ]
        voz_encontrada = False
        for voice in engine.getProperty("voices"):
            vid   = voice.id.lower()
            vname = voice.name.lower()
            if any(p in vid or p in vname for p in PATRONES_ES):
                engine.setProperty("voice", voice.id)
                if DEBUG:
                    print(f"[TTS] Voz en español: {voice.name}")
                voz_encontrada = True
                break

        if not voz_encontrada:
            if DEBUG:
                print("[TTS] No se encontró voz en español.")
                print("[TTS] Instala el paquete de voz en español:")
                print("[TTS]   Configuración > Hora e idioma > Voz > Agregar voces")
                print("[TTS] Voces disponibles en el sistema:")
                for v in engine.getProperty("voices"):
                    print(f"[TTS]   {v.name!r}  ({v.id})")

        _tts_listo.set()   # señalizar que el motor está listo

        while True:
            texto = _tts_queue.get()
            if texto is None:
                break
            try:
                engine.say(texto)
                engine.runAndWait()
            except Exception:
                pass
            finally:
                _tts_queue.task_done()

    except ImportError:
        print("[TTS] pyttsx3 no instalado. Instala: pip install pyttsx3")
        _tts_listo.set()
    except Exception as e:
        print(f"[TTS] Error al inicializar: {e}")
        _tts_listo.set()


def inicializar_tts() -> None:
    """Lanza el hilo de TTS. Llamar una sola vez al inicio."""
    t = threading.Thread(target=_tts_worker, daemon=True, name="tts")
    t.start()


def esperar_tts(timeout: float = 5.0) -> bool:
    """Bloquea hasta que el motor TTS esté listo (o timeout en segundos). Retorna True si listo."""
    return _tts_listo.wait(timeout=timeout)


def decir(texto: str, bloquear: bool = True) -> None:
    """
    Dice el texto en voz alta.
    bloquear=True espera a que termine antes de retornar (para la secuencia).
    """
    if not _tts_listo.is_set():
        return
    _tts_queue.put(texto)
    if bloquear:
        _tts_queue.join()


# Nombres en español para decir en voz alta
_NOMBRES_COLOR = {
    "ROJO":     "rojo",
    "VERDE":    "verde",
    "AZUL":     "azul",
    "AMARILLO": "amarillo",
}


def decir_color(color: str) -> None:
    """Dice el nombre del color en voz alta (bloqueante)."""
    nombre = _NOMBRES_COLOR.get(color, color.lower())
    decir(nombre, bloquear=True)


# ---- Generación y reproducción de tonos ----

def _generar_tono(frecuencia_hz: float, duracion_ms: int) -> np.ndarray:
    t = np.linspace(0, duracion_ms / 1000, int(SAMPLE_RATE * duracion_ms / 1000), endpoint=False)
    tono = np.sin(2 * np.pi * frecuencia_hz * t).astype(np.float32)
    fade = int(SAMPLE_RATE * 0.01)
    if len(tono) > 2 * fade:
        tono[:fade]  *= np.linspace(0, 1, fade)
        tono[-fade:] *= np.linspace(1, 0, fade)
    return tono * VOLUMEN_TONOS


def reproducir_tono(frecuencia_hz: float, duracion_ms: int) -> None:
    tono = _generar_tono(frecuencia_hz, duracion_ms)
    sd.play(tono, samplerate=SAMPLE_RATE)
    sd.wait()


def reproducir_sonido_color(color: str) -> None:
    freq = FRECUENCIAS_COLOR.get(color, 440)
    reproducir_tono(freq, 400)


def reproducir_sonido(tipo: str, extra=None) -> None:
    """Reproduce el sonido de un evento del juego."""
    if tipo == "color" and extra:
        reproducir_sonido_color(extra)
    elif tipo == "correcto":
        for freq in FRECUENCIAS_ESPECIALES["correcto"]:
            reproducir_tono(freq, 150)
            time.sleep(0.04)
    elif tipo == "error":
        for freq in FRECUENCIAS_ESPECIALES["error"]:
            reproducir_tono(freq, 250)
            time.sleep(0.08)
    elif tipo == "inicio":
        for freq in FRECUENCIAS_ESPECIALES["inicio"]:
            reproducir_tono(freq, 150)
            time.sleep(0.03)
    elif tipo == "gameover":
        for freq in FRECUENCIAS_ESPECIALES["gameover"]:
            reproducir_tono(freq, 250)
            time.sleep(0.05)
