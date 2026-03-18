# ============================================================
# audio_pc.py — Tonos del juego + TTS
#
# Usado por el simulador (tests/simulador_pc/main.py).
# Reemplaza el hardware del ESP32 (MAX98357A speaker) en pruebas.
#
# TTS — orden de preferencia:
#   1. edge-tts + pygame: voz neural "es-MX-DaliaNeural" (Microsoft Edge, requiere
#      internet). Sonido natural, acento mexicano real.
#      Instalar: pip install edge-tts pygame
#   2. PowerShell SAPI (fallback): voz local instalada en Windows.
#      Calidad variable según las voces instaladas.
#
# Funciones públicas:
#   reproducir_sonido()  — tonos de eventos del juego
#   decir() / decir_color() — narrador TTS
#   inicializar_tts()    — arranca el hilo dedicado de TTS
#   esperar_tts()        — espera a que el TTS esté listo
# ============================================================

import asyncio
import io
import subprocess
import numpy as np
import sounddevice as sd
import sys
import os
import time
import queue
import threading

# ---- Intentar importar edge-tts + pygame (voz neural mexicana) ----
try:
    import edge_tts as _edge_tts_mod
    _EDGE_TTS_DISPONIBLE = True
    EDGE_TTS_VOZ = "es-MX-DaliaNeural"   # voz neural femenina mexicana
except ImportError:
    _EDGE_TTS_DISPONIBLE = False
    EDGE_TTS_VOZ = ""

try:
    import pygame as _pygame_mod
    _PYGAME_DISPONIBLE = True
except ImportError:
    _PYGAME_DISPONIBLE = False

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
_voz_nombre   = ""     # nombre de la voz SAPI en español (siempre se detecta para fallback)
_usar_edge    = False   # True cuando edge-tts + pygame están listos
_edge_loop: "asyncio.AbstractEventLoop | None" = None  # loop persistente del hilo TTS


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
        if DEBUG:
            print("[TTS] SUGERENCIA: Instala voces neurales en español:")
            print("[TTS]   Configuración → Hora e idioma → Voz → Agregar voces")
            print("[TTS]   Busca: 'Paulina' o 'Jorge' (México) o 'Elena' (España)")
    except Exception as e:
        if DEBUG:
            print(f"[TTS] Error al detectar voces: {e}")
    return ""


def _nombre_corto_voz(nombre: str) -> str:
    """
    Extrae el nombre personal de la voz para usar con SelectVoice.
    SelectVoice hace matching parcial: "Sabina" coincide con
    "Microsoft Sabina Desktop - Spanish (Mexico)".
    Usar el nombre completo falla en PowerShell por los guiones y paréntesis.

    Ejemplos:
      "Microsoft Sabina Desktop - Spanish (Mexico)" → "Sabina"
      "Microsoft Helena Desktop" → "Helena"
      "Microsoft Pablo Desktop" → "Pablo"
    """
    excluir = {"microsoft", "desktop", "mobile", "online", "speech", "neural"}
    for palabra in nombre.split():
        limpia = palabra.strip("(),-.").lower()
        if limpia not in excluir and limpia and palabra[0].isupper():
            return palabra.strip("(),-.")
    return nombre


def _hablar_powershell(texto: str) -> None:
    """
    Habla 'texto' usando PowerShell + System.Speech (SAPI).
    Bloquea hasta que la frase termina.
    """
    # Escapar comillas para no romper el script de PowerShell
    safe = texto.replace('"', "'")

    if _voz_nombre:
        # Usar nombre corto: SelectVoice("Sabina") en lugar del nombre completo
        # que incluye paréntesis y guiones que pueden fallar en PowerShell.
        nombre_corto = _nombre_corto_voz(_voz_nombre)
        voz_cmd = (
            f'try {{ $s.SelectVoice("{nombre_corto}") }} '
            f'catch {{ try {{ $s.SelectVoice("{_voz_nombre}") }} catch {{}} }}; '
        )
    else:
        voz_cmd = ""

    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"{voz_cmd}"
        "$s.Rate = -1; "         # -1 = ligeramente más lento, más natural en español
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


async def _edge_generar_mp3(texto: str) -> bytes:
    """Genera audio MP3 con edge-tts (voz neural mexicana)."""
    communicate = _edge_tts_mod.Communicate(texto, EDGE_TTS_VOZ)
    data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return data


def _hablar_edge(texto: str) -> None:
    """
    Habla usando Microsoft Edge TTS Neural (es-MX-DaliaNeural).
    Requiere internet. Bloquea hasta que termina.
    Reutiliza el mismo event loop del hilo TTS para evitar el error
    "Event loop is closed" de asyncio.ProactorBasePipeTransport en Windows.
    Si falla, usa PowerShell SAPI como fallback.
    """
    global _edge_loop
    try:
        if _edge_loop is None or _edge_loop.is_closed():
            _edge_loop = asyncio.new_event_loop()
        mp3_data = _edge_loop.run_until_complete(_edge_generar_mp3(texto))
        mp3_io = io.BytesIO(mp3_data)
        _pygame_mod.mixer.music.load(mp3_io, "mp3")
        _pygame_mod.mixer.music.play()
        while _pygame_mod.mixer.music.get_busy():
            time.sleep(0.05)
    except Exception as e:
        if DEBUG:
            print(f"[TTS] edge-tts error: {e} — usando SAPI")
        _hablar_powershell(texto)


def _tts_worker():
    """Hilo dedicado. Inicializa TTS y procesa la cola de frases."""
    global _voz_nombre, _usar_edge, _edge_loop

    # Siempre detectar voz SAPI — se usa como fallback cuando edge-tts falla
    _voz_nombre = _detectar_voz_espanol()

    # Intentar activar edge-tts + pygame (voz neural mexicana)
    if _EDGE_TTS_DISPONIBLE and _PYGAME_DISPONIBLE:
        try:
            _pygame_mod.mixer.init()
            # Crear el loop persistente aquí — se reutiliza en cada llamada a _hablar_edge
            # para evitar el error "Event loop is closed" de ProactorBasePipeTransport
            _edge_loop = asyncio.new_event_loop()
            _usar_edge = True
            print(f"[TTS] Edge TTS activo — voz neural: {EDGE_TTS_VOZ}")
        except Exception as e:
            print(f"[TTS] pygame/edge init falló ({e}), usando SAPI")
    else:
        if not _EDGE_TTS_DISPONIBLE:
            print("[TTS] Instala 'edge-tts' y 'pygame' para voz neural mexicana")

    _tts_listo.set()

    while True:
        texto = _tts_queue.get()
        if texto is None:
            break
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


# ---- Grabación del micrófono (para Whisper local) ----
#
# Python captura el micrófono del sistema directamente con sounddevice.
# El browser NO necesita permisos de micrófono cuando usa Whisper local.
# El browser solo envía señales PTT_INICIO / PTT_FIN via WebSocket.

_mic_stream: "sd.InputStream | None" = None
_mic_muestras: list = []
_mic_grabando = False


def iniciar_grabacion_mic() -> None:
    """
    Abre el micrófono del sistema y empieza a grabar a 16kHz mono float32.
    Llamar detener_grabacion_mic() para parar y obtener el audio.
    """
    global _mic_stream, _mic_muestras, _mic_grabando

    _mic_muestras = []
    _mic_grabando = True

    def _callback(indata, _frames, _time_info, _status):
        if _mic_grabando:
            # indata tiene forma (frames, channels) — tomamos canal 0
            _mic_muestras.append(indata[:, 0].copy())

    _mic_stream = sd.InputStream(
        samplerate=SAMPLE_RATE,  # 16000 Hz — mismo que Whisper espera
        channels=1,
        dtype="float32",
        callback=_callback,
        blocksize=4096,
    )
    _mic_stream.start()
    if DEBUG:
        print("[MIC] Grabando...")


def detener_grabacion_mic() -> np.ndarray:
    """
    Para la grabación y devuelve el audio como numpy float32 array 16kHz.
    Retorna array vacío si no se grabó nada.
    """
    global _mic_stream, _mic_grabando

    _mic_grabando = False
    if _mic_stream:
        _mic_stream.stop()
        _mic_stream.close()
        _mic_stream = None

    if not _mic_muestras:
        return np.array([], dtype=np.float32)

    audio = np.concatenate(_mic_muestras)
    if DEBUG:
        print(f"[MIC] Grabados {len(audio) / SAMPLE_RATE:.1f}s de audio ({len(audio)} muestras)")
    return audio


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
