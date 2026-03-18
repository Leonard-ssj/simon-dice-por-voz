# ============================================================
# ws_server.py — Servidor WebSocket del simulador
#
# Bidireccional:
#   simulador → panel: eventos del juego (STATE, LED, SEQUENCE, etc.)
#   panel → simulador: audio PCM binario (PTT) o comando texto (fallback WASM)
#
# Reconocimiento de voz:
#   PREFERIDO: el browser envía audio Float32 PCM 16kHz como frame binario.
#              Python transcribe con Whisper local y devuelve el resultado.
#   FALLBACK:  si Whisper no cargó, el browser usa Whisper WASM y envía
#              texto como {"tipo": "comando", "comando": "ROJO"}.
#
# Thread-safe. Compatible con websockets >= 14.
# ============================================================

import asyncio
import json
import threading
import time
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config_test import WS_HOST, WS_PORT, DEBUG, WHISPER_MODEL

try:
    import websockets.asyncio.server as _ws_server
    import websockets.asyncio.client  # noqa — verifica que el paquete está completo
except ImportError:
    raise ImportError("Instalar websockets >= 14: pip install websockets")


class ServidorWS:
    def __init__(self):
        self._clientes: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._cola: asyncio.Queue | None = None
        self._listo = threading.Event()

        # Callbacks
        self.on_comando           = None  # callback(str)  — fallback: panel manda texto
        self.on_audio             = None  # callback(bytes) — audio PCM para transcribir
        self.on_cliente_conectado = None  # callback()     — un cliente se conectó

        # Whisper local
        self._whisper_model      = None
        self._whisper_disponible = False
        self._whisper_lock       = threading.Lock()

    # ---- Carga de Whisper ----

    def cargar_whisper(self) -> bool:
        """
        Carga el modelo Whisper de forma sincrónica.
        Llamar ANTES de iniciar() para garantizar que el primer
        mensaje READY ya incluya whisperDisponible=True.
        """
        try:
            import whisper as _whisper
            print(f"[WS] Cargando Whisper '{WHISPER_MODEL}'...")
            self._whisper_model      = _whisper.load_model(WHISPER_MODEL)
            self._whisper_disponible = True
            print(f"[WS] Whisper '{WHISPER_MODEL}' listo.")
            return True
        except Exception as e:
            print(f"[WS] Whisper no disponible (usando WASM como fallback): {e}")
            self._whisper_disponible = False
            return False

    def transcribir(self, audio_bytes: bytes) -> tuple[str, str]:
        """
        Transcribe audio PCM Float32 16kHz enviado desde el browser.
        El browser captura con AudioContext({ sampleRate: 16000 }) y envía
        la concatenación de muestras Float32 como frame binario WebSocket.

        Retorna (texto_raw, comando_canonico).
        """
        if not self._whisper_disponible or self._whisper_model is None:
            return "", "DESCONOCIDO"

        audio_np = np.frombuffer(audio_bytes, dtype=np.float32)

        if len(audio_np) < 1600:  # < 0.1s de audio — ignorar
            if DEBUG:
                print(f"[WS] Audio demasiado corto ({len(audio_np)} muestras), ignorando.")
            return "", "DESCONOCIDO"

        try:
            with self._whisper_lock:
                result = self._whisper_model.transcribe(
                    audio_np,
                    language="es",
                    fp16=False,
                    task="transcribe",
                )
            texto = result["text"].strip()

            from validador import texto_a_comando
            comando = texto_a_comando(texto)

            if DEBUG:
                print(f'[WS] Whisper: "{texto}" → {comando}')
            return texto, comando

        except Exception as e:
            print(f"[WS] Error en Whisper: {e}")
            return "", "DESCONOCIDO"

    # ---- Ciclo principal ----

    def iniciar(self):
        """Arranca el servidor WebSocket en un hilo de background."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ws-server")
        self._thread.start()
        if not self._listo.wait(timeout=10):
            print("[WS] ⚠ El servidor tardó demasiado en iniciar.")
            return
        if DEBUG:
            print(f"[WS] Servidor en ws://{WS_HOST}:{WS_PORT}")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._cola = asyncio.Queue()
        try:
            self._loop.run_until_complete(self._servidor())
        except Exception as e:
            print(f"[WS] Error en servidor: {e}")

    async def _servidor(self):
        async with _ws_server.serve(
            self._manejar_cliente,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=60,
        ):
            self._listo.set()
            await self._broadcast_loop()

    async def _manejar_cliente(self, websocket):
        path = getattr(websocket, "path", "/")
        self._clientes.add(websocket)
        if DEBUG:
            print(f"[WS] Cliente conectado ({path}). Total: {len(self._clientes)}")

        if self.on_cliente_conectado:
            threading.Thread(
                target=self.on_cliente_conectado, daemon=True, name="bienvenida-panel"
            ).start()

        try:
            async for mensaje in websocket:
                if isinstance(mensaje, bytes):
                    # Audio PCM enviado por el browser en modo Whisper local
                    if self.on_audio:
                        threading.Thread(
                            target=self.on_audio,
                            args=(mensaje,),
                            daemon=True,
                            name="whisper-infer",
                        ).start()
                else:
                    # Texto JSON — fallback WASM o comandos de control
                    try:
                        data = json.loads(mensaje)
                        if data.get("tipo") == "comando" and self.on_comando:
                            threading.Thread(
                                target=self.on_comando,
                                args=(data["comando"],),
                                daemon=True,
                                name="cmd",
                            ).start()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self._clientes.discard(websocket)
            if DEBUG:
                print(f"[WS] Cliente desconectado. Total: {len(self._clientes)}")

    async def _broadcast_loop(self):
        while True:
            msg = await self._cola.get()
            if self._clientes:
                texto = json.dumps(msg, ensure_ascii=False)
                resultados = await asyncio.gather(
                    *[ws.send(texto) for ws in list(self._clientes)],
                    return_exceptions=True,
                )
                for ws, res in zip(list(self._clientes), resultados):
                    if isinstance(res, Exception):
                        self._clientes.discard(ws)

    def enviar(self, mensaje: dict):
        """Thread-safe. Encola un mensaje JSON para todos los clientes."""
        if self._loop and self._cola and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._cola.put_nowait,
                {**mensaje, "ts": int(time.time() * 1000)},
            )

    # ---- Helpers del protocolo ----

    def enviar_ready(self):
        self.enviar({
            "tipo":             "ready",
            "raw":              "READY",
            "whisperDisponible": self._whisper_disponible,
        })

    def enviar_estado(self, estado: str):
        self.enviar({"tipo": "state", "estado": estado, "raw": f"STATE:{estado}"})

    def enviar_detectado(self, palabra: str):
        self.enviar({"tipo": "detected", "palabra": palabra, "raw": f"DETECTED:{palabra}"})

    def enviar_resultado(self, resultado: str):
        self.enviar({"tipo": "result", "resultado": resultado, "raw": f"RESULT:{resultado}"})

    def enviar_secuencia(self, secuencia: list):
        self.enviar({
            "tipo":     "sequence",
            "secuencia": secuencia,
            "raw":      "SEQUENCE:" + ",".join(secuencia),
        })

    def enviar_esperado(self, color: str):
        self.enviar({"tipo": "expected", "esperado": color, "raw": f"EXPECTED:{color}"})

    def enviar_nivel(self, nivel: int):
        self.enviar({"tipo": "level", "nivel": nivel, "raw": f"LEVEL:{nivel}"})

    def enviar_puntuacion(self, puntuacion: int):
        self.enviar({"tipo": "score", "puntuacion": puntuacion, "raw": f"SCORE:{puntuacion}"})

    def enviar_gameover(self):
        self.enviar({"tipo": "gameover", "raw": "GAMEOVER"})

    def enviar_voz(self, texto: str, comando: str):
        """Resultado de Whisper local — el browser actualiza UI con texto + comando."""
        self.enviar({"tipo": "voz", "texto": texto, "comando": comando})

    def enviar_led_activo(self, color):
        self.enviar({"tipo": "led", "color": color, "raw": f"LED:{color or 'OFF'}"})

    def enviar_log(self, mensaje: str):
        self.enviar({"tipo": "log", "raw": mensaje})
