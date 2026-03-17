# ============================================================
# ws_server.py — Servidor WebSocket del simulador
#
# Bidireccional:
#   simulador → panel: eventos del juego (STATE, LED, SEQUENCE, etc.)
#   panel → simulador: comandos reconocidos por Whisper WASM en el browser
#                      {"tipo": "comando", "comando": "ROJO"}
#
# Cuando hay clientes conectados (hay_clientes=True), el browser
# hace el reconocimiento de voz — el hilo Python cede el control.
# Thread-safe. Compatible con websockets >= 14.
# ============================================================

import asyncio
import json
import threading
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from config_test import WS_HOST, WS_PORT, DEBUG

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
        self.on_comando = None   # callback(str) — llamado cuando el panel manda un comando

    @property
    def hay_clientes(self) -> bool:
        return len(self._clientes) > 0

    def iniciar(self):
        """Arranca el servidor WebSocket en un hilo de background."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ws-server")
        self._thread.start()
        # Esperar hasta que el servidor esté realmente escuchando
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
        # El servidor empieza DENTRO del async with → _listo se setea después de bind()
        async with _ws_server.serve(
            self._manejar_cliente,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=60,
        ):
            self._listo.set()   # ← servidor ya está escuchando
            await self._broadcast_loop()

    async def _manejar_cliente(self, websocket):
        # Compatibilidad websockets v10–v16
        path = getattr(websocket, "path", "/")
        self._clientes.add(websocket)
        if DEBUG:
            print(f"[WS] Cliente conectado ({path}). Total: {len(self._clientes)}")
        try:
            async for mensaje in websocket:
                # El panel puede mandar comandos reconocidos por Whisper
                try:
                    data = json.loads(mensaje)
                    if data.get("tipo") == "comando" and self.on_comando:
                        self.on_comando(data["comando"])
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
                # Limpiar clientes que ya no responden
                for ws, res in zip(list(self._clientes), resultados):
                    if isinstance(res, Exception):
                        self._clientes.discard(ws)

    def enviar(self, mensaje: dict):
        """Thread-safe. Encola un mensaje JSON para todos los clientes."""
        if self._loop and self._cola and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._cola.put_nowait,
                {**mensaje, "ts": int(time.time() * 1000)}
            )

    # ---- Helpers del protocolo ----

    def enviar_ready(self):
        self.enviar({"tipo": "ready", "raw": "READY"})

    def enviar_estado(self, estado: str):
        self.enviar({"tipo": "state", "estado": estado, "raw": f"STATE:{estado}"})

    def enviar_detectado(self, palabra: str):
        self.enviar({"tipo": "detected", "palabra": palabra, "raw": f"DETECTED:{palabra}"})

    def enviar_resultado(self, resultado: str):
        self.enviar({"tipo": "result", "resultado": resultado, "raw": f"RESULT:{resultado}"})

    def enviar_secuencia(self, secuencia: list):
        self.enviar({
            "tipo": "sequence",
            "secuencia": secuencia,
            "raw": "SEQUENCE:" + ",".join(secuencia),
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
        self.enviar({"tipo": "voz", "texto": texto, "comando": comando})

    def enviar_led_activo(self, color):
        """Notifica al panel qué LED está encendido en este momento (None = apagado)."""
        self.enviar({"tipo": "led", "color": color, "raw": f"LED:{color or 'OFF'}"})

    def enviar_log(self, mensaje: str):
        self.enviar({"tipo": "log", "raw": mensaje})
