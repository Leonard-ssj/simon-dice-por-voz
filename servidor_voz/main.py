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
import base64
import time
import subprocess
import queue
import io
import wave
from pathlib import Path
from datetime import datetime
import numpy as np
try:
    import msvcrt
    KEYBOARD_OK = True
except Exception:
    KEYBOARD_OK = False

sys.path.insert(0, os.path.dirname(__file__))

import websockets
from config_voz import WS_HOST, WS_PORT, SAMPLE_RATE, WHISPER_MODEL, DEBUG, SERIAL_ENABLED, SERIAL_PORT, SERIAL_BAUD, PC_TTS_ENABLED, SAVE_KIT_WAV

try:
    import serial
    import serial.tools.list_ports
    SERIAL_OK = True
except Exception:
    SERIAL_OK = False

_tts_queue: "queue.Queue[str]" = queue.Queue()
_serial_ref = None
_serial_lock = threading.Lock()
_last_space_ms = 0
_edge_loop = None
_usar_edge = False
_edge_voice = "es-MX-DaliaNeural"
_captures_dir = Path(__file__).resolve().parent / "captures"

try:
    import edge_tts
    EDGE_TTS_OK = True
except Exception:
    EDGE_TTS_OK = False

try:
    import pygame
    PYGAME_OK = True
except Exception:
    PYGAME_OK = False


def _tts_speak_blocking(texto: str) -> None:
    if not texto:
        return
    global _edge_loop, _usar_edge
    if _usar_edge:
        try:
            if _edge_loop is None or _edge_loop.is_closed():
                _edge_loop = asyncio.new_event_loop()
            async def _mk() -> bytes:
                comm = edge_tts.Communicate(texto, _edge_voice)
                data = b""
                async for chunk in comm.stream():
                    if chunk.get("type") == "audio":
                        data += chunk.get("data", b"")
                return data
            mp3 = _edge_loop.run_until_complete(_mk())
            bio = io.BytesIO(mp3)
            pygame.mixer.music.load(bio, "mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            return
        except Exception:
            _usar_edge = False
    safe = texto.replace('"', "'")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SelectVoice('Sabina') } catch {}; "
        "$s.Rate = -1; "
        f'$s.Speak("{safe}")'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def _tts_worker() -> None:
    global _usar_edge, _edge_loop
    if EDGE_TTS_OK and PYGAME_OK:
        try:
            pygame.mixer.init()
            _edge_loop = asyncio.new_event_loop()
            _usar_edge = True
            print(f"  [TTS] Voz mexicana edge-tts activa: {_edge_voice}")
        except Exception:
            _usar_edge = False
    while True:
        texto = _tts_queue.get()
        if texto is None:
            return
        _tts_speak_blocking(texto)


def _tts(texto: str) -> None:
    if not PC_TTS_ENABLED:
        return
    try:
        _tts_queue.put_nowait(texto)
    except Exception:
        pass

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
    "rojo verde azul amarillo "
    "di rojo di verde di azul di amarillo "
    "el color es rojo es verde es azul es amarillo "
    "empieza inicia comienza jugar arranca vamos ya "
    "para pausa espera para el juego "
    "repite otra vez de nuevo "
    "reinicia reset volver empezar de nuevo "
    "simon dice por voz"
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
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.0,
            no_speech_threshold=0.35,
            logprob_threshold=-1.2,
        )
        texto   = resultado.get("text", "").strip()
        comando = _texto_a_comando(texto)
        return texto, comando
    except Exception as e:
        print(f"  [Whisper] Error: {e}")
        return "", "DESCONOCIDO"


def _serial_auto_port() -> str | None:
    if not SERIAL_OK:
        return None
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    ranked: list[tuple[int, str]] = []
    for p in ports:
        d = f"{p.device} {p.description} {p.hwid}".upper()
        score = 0
        if "USB" in d:
            score += 1
        if "CP210" in d:
            score += 3
        if "CH340" in d:
            score += 3
        if "ESP32" in d:
            score += 5
        ranked.append((score, p.device))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1] if ranked else None


def _serial_candidate_ports() -> list[str]:
    if not SERIAL_OK:
        return []
    ports = list(serial.tools.list_ports.comports())
    ranked: list[tuple[int, str]] = []
    for p in ports:
        d = f"{p.device} {p.description} {p.hwid}".upper()
        score = 0
        if "USB" in d:
            score += 1
        if "CP210" in d:
            score += 3
        if "CH340" in d:
            score += 3
        if "ESP32" in d:
            score += 5
        ranked.append((score, p.device))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in ranked]


def _serial_send_line(ser, txt: str) -> None:
    ser.write((txt + "\n").encode("utf-8"))


def _serial_send_global(txt: str) -> bool:
    global _serial_ref
    with _serial_lock:
        if _serial_ref is None:
            return False
        try:
            _serial_send_line(_serial_ref, txt)
            return True
        except Exception:
            return False


def _beep_fin() -> None:
    if not SOUNDDEVICE_OK:
        return
    try:
        t = np.linspace(0, 0.12, int(SAMPLE_RATE * 0.12), endpoint=False, dtype=np.float32)
        tone = (0.20 * np.sin(2 * np.pi * 880.0 * t)).astype(np.float32)
        sd.play(tone, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception:
        pass


def _save_kit_wav(audio_np: np.ndarray, tag: str = "kit") -> None:
    if not SAVE_KIT_WAV:
        return
    try:
        _captures_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        wav_path = _captures_dir / f"{tag}_{ts}.wav"
        pcm16 = np.clip(audio_np * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm16.tobytes())
        print(f"  [SERIAL] WAV_GUARDADO {wav_path}")
    except Exception as e:
        print(f"  [SERIAL] WAV_ERROR {e}")


def _keyboard_space_loop() -> None:
    global _last_space_ms
    if not KEYBOARD_OK:
        return
    while True:
        try:
            if not msvcrt.kbhit():
                time.sleep(0.03)
                continue
            c = msvcrt.getch()
            if c == b' ':
                now = int(time.time() * 1000)
                if now - _last_space_ms < 350:
                    continue
                _last_space_ms = now
                ok = _serial_send_global("SPACE")
                if ok:
                    print("  [KBD] SPACE -> SPACE")
                else:
                    print("  [KBD] SPACE sin serial activa")
            elif c in (b'l', b'L'):
                ok = _serial_send_global("MICL")
                if ok:
                    print("  [KBD] L -> MICL")
            elif c in (b'r', b'R'):
                ok = _serial_send_global("MICR")
                if ok:
                    print("  [KBD] R -> MICR")
            elif c == b'1':
                ok = _serial_send_global("PINA")
                if ok:
                    print("  [KBD] 1 -> PINA")
            elif c == b'2':
                ok = _serial_send_global("PINB")
                if ok:
                    print("  [KBD] 2 -> PINB")
            elif c in (b'p', b'P'):
                ok = _serial_send_global("PINSTAT")
                if ok:
                    print("  [KBD] P -> PINSTAT")
            elif c == b'8':
                ok = _serial_send_global("SHIFT8")
                if ok:
                    print("  [KBD] 8 -> SHIFT8")
            elif c == b'9':
                ok = _serial_send_global("SHIFT11")
                if ok:
                    print("  [KBD] 9 -> SHIFT11")
            elif c == b'0':
                ok = _serial_send_global("SHIFT14")
                if ok:
                    print("  [KBD] 0 -> SHIFT14")
        except Exception:
            time.sleep(0.2)


def _serial_handle_audio(ser, b64_lines: list[str], expected_bytes: int) -> None:
    b64_clean = re.sub(r"[^A-Za-z0-9+/=]", "", "".join(b64_lines))
    if not b64_clean:
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return
    try:
        raw = base64.b64decode(b64_clean, validate=False)
    except Exception:
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return
    if expected_bytes > 0 and abs(len(raw) - expected_bytes) > 16:
        print(f"  [SERIAL] AUDIO_CORRUPTO esperado={expected_bytes} recibido={len(raw)}")
        _serial_send_line(ser, "WS_TEXT:audio incompleto")
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return
    if len(raw) < 2:
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return
    if len(raw) % 2 == 1:
        raw = raw[:-1]
    audio_i16 = np.frombuffer(raw, dtype=np.int16)
    audio_np = audio_i16.astype(np.float32) / 32768.0
    if len(audio_np) == 0:
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return
    _save_kit_wav(audio_np, "kit_raw")

    dur_s = len(audio_np) / float(SAMPLE_RATE)
    audio_np = audio_np - float(np.mean(audio_np))
    rms = float(np.sqrt(np.mean(audio_np * audio_np)))
    peak = float(np.max(np.abs(audio_np)))
    clip_ratio = float(np.mean(np.abs(audio_np) >= 0.98))
    print(f"  [SERIAL] AUDIO_STATS dur={dur_s:.2f}s n={len(audio_np)} rms={rms:.5f} peak={peak:.5f} clip={clip_ratio:.4f}")

    if peak < 0.004 or rms < 0.001:
        print("  [SERIAL] Señal de micrófono muy baja")
        _save_kit_wav(audio_np, "kit_proc")
        _serial_send_line(ser, "WS_TEXT:senal baja")
        _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
        return

    gain = 0.035 / max(rms, 1e-6)
    if gain > 8.0:
        gain = 8.0
    if gain < 0.05:
        gain = 0.05
    audio_np = np.clip(audio_np * gain, -1.0, 1.0)
    audio_np = np.append(audio_np[0], audio_np[1:] - 0.97 * audio_np[:-1]).astype(np.float32)

    thr = max(0.012, min(0.06, float(np.sqrt(np.mean(audio_np * audio_np))) * 1.8))
    idx = np.where(np.abs(audio_np) > thr)[0]
    if len(idx) > 0:
        a = max(0, int(idx[0]) - int(0.15 * SAMPLE_RATE))
        b = min(len(audio_np), int(idx[-1]) + int(0.15 * SAMPLE_RATE))
        if b - a >= int(0.2 * SAMPLE_RATE):
            audio_np = audio_np[a:b]

    _save_kit_wav(audio_np, "kit_proc")
    texto, comando = transcribir(audio_np)
    print(f'  [SERIAL] "{texto}" → {comando}')
    if texto:
        _tts(f"Dijiste: {texto}")
    else:
        _tts("No te entendí")
    if texto:
        _serial_send_line(ser, f"WS_TEXT:{texto}")
    _serial_send_line(ser, f"WS_CMD:{comando}")
    if comando != "DESCONOCIDO":
        _tts(f"Comando: {comando}")
        _serial_send_line(ser, comando)


def _serial_bridge_loop() -> None:
    global _serial_ref
    if not SERIAL_ENABLED:
        return
    if not SERIAL_OK:
        print("  [SERIAL] pyserial no disponible")
        return

    while True:
        candidates = [SERIAL_PORT] if SERIAL_PORT else _serial_candidate_ports()
        if not candidates:
            print("  [SERIAL] No se encontró puerto serie")
            time.sleep(1.0)
            continue

        ser = None
        for port in candidates:
            print(f"  [SERIAL] Conectando a {port} @ {SERIAL_BAUD}")
            try:
                tmp = serial.Serial(port=None, baudrate=SERIAL_BAUD, timeout=0.2, rtscts=False, dsrdtr=False)
                tmp.dtr = False
                tmp.rts = False
                tmp.port = port
                tmp.open()
                ser = tmp
                break
            except PermissionError:
                print(f"  [SERIAL] Puerto ocupado: {port}. Cierra Serial Monitor/IDE y reintenta.")
            except Exception as e:
                print(f"  [SERIAL] Error abriendo {port}: {e}")
        if ser is None:
            time.sleep(1.0)
            continue

        with _serial_lock:
            _serial_ref = ser
        time.sleep(0.8)
        _serial_send_line(ser, "WON")
        _serial_send_line(ser, "SPACEONLYON")
        _serial_send_line(ser, "MICAUTO")
        _serial_send_line(ser, "LVLON")
        _serial_send_line(ser, "PINSTAT")

        audio_mode = False
        audio_expected_bytes = 0
        audio_lines: list[str] = []
        try:
            while True:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not line:
                    continue
                if line.startswith("AUDIO:START:"):
                    try:
                        exp = int(line.split(":")[-1])
                    except Exception:
                        exp = -1
                    print(f"  [SERIAL] AUDIO_START bytes={exp}")
                    audio_expected_bytes = exp
                    audio_mode = True
                    audio_lines = []
                    continue
                if line == "AUDIO:END":
                    audio_mode = False
                    total_chars = sum(len(x) for x in audio_lines)
                    print(f"  [SERIAL] AUDIO_END b64_lines={len(audio_lines)} b64_chars={total_chars}")
                    _beep_fin()
                    _serial_handle_audio(ser, audio_lines, audio_expected_bytes)
                    audio_lines = []
                    audio_expected_bytes = 0
                    continue
                if line == "AUDIO:VACIO":
                    _serial_send_line(ser, "WS_CMD:DESCONOCIDO")
                    continue
                if line.startswith("MICLVL:"):
                    print(f"  [SERIAL] {line}")
                    continue
                if audio_mode:
                    audio_lines.append(line)
                    continue
                if DEBUG:
                    print(f"  [SERIAL] {line}")
        except Exception as e:
            print(f"  [SERIAL] Error en bridge: {e}")
        finally:
            try:
                ser.close()
            except Exception:
                pass
            with _serial_lock:
                _serial_ref = None
            time.sleep(1.0)


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

            elif tipo == "audio_float32":
                # Audio enviado desde el botón físico ESP32 (INMP441 → base64 → browser → aquí)
                datos_lista = datos.get("datos", [])
                if datos_lista:
                    audio_np = np.array(datos_lista, dtype=np.float32)
                    if DEBUG:
                        print(f"  [WS] audio_float32: {len(audio_np)} muestras de INMP441")
                    texto, comando = transcribir(audio_np)
                    if DEBUG:
                        print(f'  [WS] "{texto}" → {comando}')
                    await websocket.send(json.dumps({
                        "tipo":    "voz",
                        "texto":   texto,
                        "comando": comando,
                    }))
                else:
                    await websocket.send(json.dumps({"tipo": "voz", "texto": "", "comando": "DESCONOCIDO"}))

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
    print("  Convierte audio a comandos via Whisper.")
    print(f"  WebSocket: ws://{WS_HOST}:{WS_PORT}")
    if SERIAL_ENABLED:
        if SERIAL_PORT:
            print(f"  Serial: {SERIAL_PORT} @ {SERIAL_BAUD}")
        else:
            print(f"  Serial: auto @ {SERIAL_BAUD}")
    print("=" * 55 + "\n")

    cargar_whisper()
    if PC_TTS_ENABLED:
        tts_thread = threading.Thread(target=_tts_worker, daemon=True)
        tts_thread.start()
        _tts("Servidor de voz listo")
    if SERIAL_ENABLED:
        t = threading.Thread(target=_serial_bridge_loop, daemon=True)
        t.start()
    if SERIAL_ENABLED and KEYBOARD_OK:
        k = threading.Thread(target=_keyboard_space_loop, daemon=True)
        k.start()

    try:
        asyncio.run(_iniciar_servidor())
    except KeyboardInterrupt:
        print("\n  Servidor detenido.\n")


if __name__ == "__main__":
    main()
