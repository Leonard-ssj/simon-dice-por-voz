# ============================================================
# audio_pc.py — Tonos del juego + TTS
#
# Usado por el simulador (tests/simulador_pc/main.py).
# Reemplaza el hardware del ESP32 (MAX98357A speaker) en pruebas.
#
# TTS: PowerShell + System.Speech.SpeechSynthesizer (Windows SAPI).
#   Garantiza que la voz suene aunque pyttsx3.runAndWait() se bloquee,
#   que es un bug conocido de pyttsx3 en hilos de Windows.
#   pyttsx3 se usa SOLO para detectar el nombre de la voz en español.
#
# Funciones públicas:
#   reproducir_sonido()  — tonos de eventos del juego
#   decir() / decir_color() — narrador TTS
#   inicializar_tts()    — arranca el hilo dedicado de TTS
#   esperar_tts()        — espera a que el TTS esté listo
# ============================================================

import subprocess
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


# ---- TTS — PowerShell SAPI ----
# Cada frase corre en un subprocess de PowerShell que llama a
# System.Speech.SpeechSynthesizer.Speak().
# Esto evita el bug de pyttsx3 donde runAndWait() se bloquea en hilos de Windows.

_tts_queue: queue.Queue = queue.Queue()
_tts_listo  = threading.Event()
_voz_nombre = ""   # nombre de la voz en español (encontrada durante inicialización)


def _detectar_voz_espanol() -> str:
    """
    Usa pyttsx3 SOLO para enumerar las voces del sistema y encontrar
    una en español. Devuelve el nombre de la voz (str) o "" si no hay.
    No llama a runAndWait() — solo enumera voces.
    """
    PATRONES_ES = [
        "es-mx", "es-es", "es-us", "es-ar", "es-cl", "es-co",
        "es_mx", "es_es",
        "sabina", "helena", "pablo", "jorge", "maria",
        "spanish", "español", "espanol",
        "mstts_v110_eses", "mstts_v110_esmx",
    ]
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voces  = engine.getProperty("voices")
        for voice in voces:
            vid   = voice.id.lower()
            vname = voice.name.lower()
            if any(p in vid or p in vname for p in PATRONES_ES):
                print(f"[TTS] Voz en español encontrada: {voice.name}")
                try:
                    engine.stop()
                except Exception:
                    pass
                return voice.name

        # Sin voz en español
        if DEBUG:
            print("[TTS] No se encontró voz en español.")
            print("[TTS] Voces disponibles:")
            for v in voces:
                print(f"[TTS]   {v.name!r}  ({v.id})")
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as e:
        if DEBUG:
            print(f"[TTS] Error al detectar voces: {e}")
    return ""


def _hablar_powershell(texto: str) -> None:
    """
    Habla 'texto' usando PowerShell + System.Speech (SAPI).
    Bloquea hasta que la frase termina.
    """
    # Escapar comillas para no romper el script de PowerShell
    safe = texto.replace('"', "'")
    voz_cmd = f'$s.SelectVoice("{_voz_nombre}"); ' if _voz_nombre else ""

    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"{voz_cmd}"
        "$s.Rate = -1; "          # -10..10 : -1 = ligeramente lento, natural
        f'$s.Speak("{safe}")'
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        if DEBUG:
            print(f"[TTS] Timeout hablando: {texto!r}")
    except Exception as e:
        if DEBUG:
            print(f"[TTS] Error PowerShell: {e}")


def _tts_worker():
    """Hilo dedicado. Detecta la voz y luego procesa la cola de frases."""
    global _voz_nombre
    _voz_nombre = _detectar_voz_espanol()
    _tts_listo.set()   # señalizar que el TTS está listo para recibir frases

    while True:
        texto = _tts_queue.get()
        if texto is None:
            break
        try:
            _hablar_powershell(texto)
        except Exception as e:
            if DEBUG:
                print(f"[TTS] Error inesperado: {e}")
        finally:
            _tts_queue.task_done()


def inicializar_tts() -> None:
    """Lanza el hilo de TTS. Llamar una sola vez al inicio."""
    t = threading.Thread(target=_tts_worker, daemon=True, name="tts")
    t.start()


def esperar_tts(timeout: float = 5.0) -> bool:
    """Bloquea hasta que el motor TTS esté listo. Retorna True si listo."""
    return _tts_listo.wait(timeout=timeout)


def decir(texto: str, bloquear: bool = True) -> None:
    """
    Encola 'texto' para ser hablado.
    bloquear=True espera a que la frase termine antes de retornar.
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
    t    = np.linspace(0, duracion_ms / 1000,
                       int(SAMPLE_RATE * duracion_ms / 1000), endpoint=False)
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
