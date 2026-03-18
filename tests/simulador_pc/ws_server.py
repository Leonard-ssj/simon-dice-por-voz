# ============================================================
# ws_server.py — Servidor WebSocket del simulador (Fase 1)
#
# Bidireccional:
#   simulador → panel: eventos del juego (STATE, LED, SEQUENCE, etc.)
#   panel → simulador: señales de control PTT + comandos fallback WASM
#
# Reconocimiento de voz:
#   PREFERIDO (Whisper local):
#     Browser envía {"tipo":"control","accion":"PTT_INICIO"} al presionar PTT.
#     Python abre el micrófono del sistema (sounddevice) y empieza a grabar.
#     Browser envía {"tipo":"control","accion":"PTT_FIN"} al soltar PTT.
#     Python para la grabación, transcribe con Whisper local, procesa el comando
#     y devuelve {"tipo":"voz","texto":"...","comando":"..."} al browser.
#     El browser NO necesita permisos de micrófono en este modo.
#
#   FALLBACK (Whisper WASM):
#     Si Whisper no cargó, el browser usa Whisper WASM y envía texto:
#     {"tipo": "comando", "comando": "ROJO"}
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

# Contexto de vocabulario para guiar a Whisper.
# Mismo prompt que usa el browser (whisper.worker.ts) para consistencia.
# Debe estar en minúsculas — el modelo fue entrenado con texto mixto, no ALL CAPS.
INITIAL_PROMPT = (
    "rojo verde azul amarillo "
    "di rojo di verde di azul di amarillo "
    "el color es rojo es verde es azul es amarillo "
    "empieza inicia comienza jugar arranca vamos ya "
    "para pausa espera para el juego "
    "repite otra vez de nuevo "
    "reinicia reset volver empezar de nuevo "
    "simon dice simon dice por voz nivel uno dos tres cuatro cinco "
    "correcto incorrecto fin del juego sí no"
)

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
        self.on_ptt_inicio        = None  # callback() — usuario presionó PTT (abrir mic)
        self.on_ptt_fin           = None  # callback() — usuario soltó PTT (grabar+transcribir)
        self.on_pausar_timeout    = None  # callback() — pausar timer ANTES de spawnear hilo
        self.on_comando           = None  # callback(str) — fallback WASM: panel manda texto
        self.on_cliente_conectado = None  # callback() — un cliente se conectó

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

    def transcribir(self, audio: "bytes | np.ndarray") -> tuple[str, str]:
        """
        Transcribe audio PCM Float32 16kHz grabado por Python (sounddevice).
        Acepta numpy array (de detener_grabacion_mic) o bytes como fallback.
        Retorna (texto_raw, comando_canonico).
        """
        if not self._whisper_disponible or self._whisper_model is None:
            return "", "DESCONOCIDO"

        if isinstance(audio, bytes):
            audio_np = np.frombuffer(audio, dtype=np.float32)
        else:
            audio_np = np.asarray(audio, dtype=np.float32)

        if len(audio_np) < 1600:  # < 0.1s de audio — ignorar
            if DEBUG:
                print(f"[WS] Audio demasiado corto ({len(audio_np)} muestras), ignorando.")
            return "", "DESCONOCIDO"

        try:
            with self._whisper_lock:
                result = self._whisper_model.transcribe(
                    audio_np,
                    language="es",
                    fp16=False,      # True si tienes GPU NVIDIA con CUDA
                    task="transcribe",
                    initial_prompt=INITIAL_PROMPT,
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
                # Solo mensajes de texto JSON — ya no recibimos frames binarios.
                # El micrófono lo abre Python directamente (sounddevice).
                if isinstance(mensaje, bytes):
                    continue  # ignorar (no debería llegar en Fase 1)

                try:
                    data = json.loads(mensaje)
                    tipo = data.get("tipo", "")

                    if tipo == "control":
                        accion = data.get("accion", "")

                        if accion == "PTT_INICIO":
                            # Pausar timer AQUÍ (hilo asyncio, antes de spawnear)
                            # para eliminar la race condition con tick().
                            if self.on_pausar_timeout:
                                self.on_pausar_timeout()
                            # Abrir micrófono en hilo separado (sounddevice bloqueante)
                            if self.on_ptt_inicio:
                                threading.Thread(
                                    target=self.on_ptt_inicio,
                                    daemon=True,
                                    name="ptt-inicio",
                                ).start()

                        elif accion == "PTT_FIN":
                            # Detener grabación, transcribir y procesar comando
                            if self.on_ptt_fin:
                                threading.Thread(
                                    target=self.on_ptt_fin,
                                    daemon=True,
                                    name="ptt-fin",
                                ).start()

                    elif tipo == "comando" and self.on_comando:
                        # Fallback WASM: browser transcribió localmente y manda texto
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
