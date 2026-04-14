# ============================================================
# ws_server.py — Servidor WebSocket para el panel web
#
# Broadcast bidireccional:
#   Servidor → Panel: eventos del juego (STATE, LED, SEQUENCE, etc.)
#   Panel → Servidor: señales de control PTT (spacebar) + fallback WASM
#
# El audio NO pasa por WebSocket. Cuando el panel envía PTT_INICIO,
# el servidor llama a serial_bridge.iniciar_ptt_remoto() que envía
# 'R' al ESP32 → ESP32 captura audio → envía por Serial → Whisper en Python.
#
# Compatible con websockets >= 14.
# ============================================================

import asyncio
import json
import threading
import time
import sys

from config import WS_HOST, WS_PORT, DEBUG

try:
    import websockets.asyncio.server as _ws_server
except ImportError:
    raise ImportError("Instalar websockets >= 14: pip install 'websockets>=14'")


class ServidorWS:
    def __init__(self):
        self._clientes: set = set()
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread         | None = None
        self._cola:   asyncio.Queue            | None = None
        self._listo   = threading.Event()

        # ── Callbacks (asignar desde servidor.py) ────────────────────────────
        self.on_ptt_inicio        = None   # ()  → serial_bridge.iniciar_ptt_remoto
        self.on_ptt_fin           = None   # ()  → serial_bridge.detener_ptt_remoto
        self.on_pausar_timeout    = None   # ()  → juego.pausar_timeout (previene race condition)
        self.on_comando           = None   # (str) → fallback WASM: panel mandó texto directo
        self.on_cliente_conectado = None   # ()  → bienvenida TTS

    # ── Arranque ──────────────────────────────────────────────────────────────

    def iniciar(self):
        """Arranca el servidor WebSocket en un hilo background."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ws-server")
        self._thread.start()
        if not self._listo.wait(timeout=10):
            print("[WS] WARN: El servidor tardó demasiado en iniciar.")
            return
        if DEBUG:
            print(f"[WS] Servidor listo en ws://{WS_HOST}:{WS_PORT}")

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

    # ── Manejo de clientes ────────────────────────────────────────────────────

    async def _enviar_ready(self, websocket):
        """Envía READY directamente al cliente recién conectado."""
        from config import TIMEOUT_RESPUESTA as _TIMEOUT_MS, WHISPER_MODEL as _WM
        msg = {
            "tipo":              "ready",
            "raw":               "READY",
            "ts":                int(time.time() * 1000),
            # Le dice al panel que Whisper corre en Python local.
            # Sin este campo (o con False) el panel activa el fallback WASM
            # y empieza a mandar comandos basura como "WHISPER_PROCESANDO".
            "whisperDisponible": True,
            "whisperModelo":     _WM,
            # Timeout del turno en ms — el panel puede mostrar una barra de progreso
            # sincronizada con el servidor. El timer del servidor se pausa durante
            # Whisper, así que la barra del panel también debe pausarse al grabar.
            "tiempoTimeout":     _TIMEOUT_MS,
        }
        await websocket.send(json.dumps(msg, ensure_ascii=False))

    async def _manejar_cliente(self, websocket):
        self._clientes.add(websocket)
        if DEBUG:
            print(f"[WS] Cliente conectado. Total: {len(self._clientes)}")

        await self._enviar_ready(websocket)

        if self.on_cliente_conectado:
            threading.Thread(
                target=self.on_cliente_conectado,
                daemon=True,
                name="bienvenida",
            ).start()

        try:
            async for mensaje in websocket:
                if isinstance(mensaje, bytes):
                    continue   # el audio no pasa por WebSocket — viene del ESP32 por Serial

                try:
                    data = json.loads(mensaje)
                    tipo = data.get("tipo", "")

                    if tipo == "control":
                        accion = data.get("accion", "")

                        if accion == "PTT_INICIO":
                            # Pausar timer AQUÍ (hilo asyncio) antes de spawnear
                            # hilo — elimina la race condition con tick().
                            if self.on_pausar_timeout:
                                self.on_pausar_timeout()
                            if self.on_ptt_inicio:
                                threading.Thread(
                                    target=self.on_ptt_inicio,
                                    daemon=True,
                                    name="ptt-inicio",
                                ).start()

                        elif accion == "PTT_FIN":
                            if self.on_ptt_fin:
                                threading.Thread(
                                    target=self.on_ptt_fin,
                                    daemon=True,
                                    name="ptt-fin",
                                ).start()

                    elif tipo == "comando" and self.on_comando:
                        # Fallback WASM: el browser transcribió y manda texto
                        threading.Thread(
                            target=self.on_comando,
                            args=(data.get("comando", ""),),
                            daemon=True,
                            name="cmd-wasm",
                        ).start()

                except Exception:
                    pass

        except Exception:
            pass
        finally:
            self._clientes.discard(websocket)
            if DEBUG:
                print(f"[WS] Cliente desconectado. Total: {len(self._clientes)}")

    # ── Broadcast loop ────────────────────────────────────────────────────────

    async def _broadcast_loop(self):
        while True:
            msg = await self._cola.get()
            if not self._clientes:
                continue
            texto = json.dumps(msg, ensure_ascii=False)
            resultados = await asyncio.gather(
                *[ws.send(texto) for ws in list(self._clientes)],
                return_exceptions=True,
            )
            for ws, res in zip(list(self._clientes), resultados):
                if isinstance(res, Exception):
                    self._clientes.discard(ws)

    # ── API de envío ─────────────────────────────────────────────────────────

    def enviar(self, mensaje: dict):
        """Thread-safe. Encola un mensaje JSON para todos los clientes."""
        if self._loop and self._cola and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._cola.put_nowait,
                {**mensaje, "ts": int(time.time() * 1000)},
            )

    # ── Helpers del protocolo (espejo del simulador) ──────────────────────────

    def enviar_estado(self, estado: str):
        self.enviar({"tipo": "state", "estado": estado, "raw": f"STATE:{estado}"})

    def enviar_led_activo(self, color):
        self.enviar({"tipo": "led", "color": color, "raw": f"LED:{color or 'OFF'}"})

    def enviar_secuencia(self, secuencia: list):
        self.enviar({
            "tipo":      "sequence",
            "secuencia": secuencia,
            "raw":       "SEQUENCE:" + ",".join(secuencia),
        })

    def enviar_esperado(self, color: str):
        self.enviar({"tipo": "expected", "esperado": color, "raw": f"EXPECTED:{color}"})

    def enviar_nivel(self, nivel: int):
        self.enviar({"tipo": "level", "nivel": nivel, "raw": f"LEVEL:{nivel}"})

    def enviar_puntuacion(self, pts: int):
        self.enviar({"tipo": "score", "puntuacion": pts, "raw": f"SCORE:{pts}"})

    def enviar_resultado(self, resultado: str):
        self.enviar({"tipo": "result", "resultado": resultado, "raw": f"RESULT:{resultado}"})

    def enviar_voz(self, texto: str, comando: str):
        self.enviar({"tipo": "voz", "texto": texto, "comando": comando})

    def enviar_gameover(self):
        self.enviar({"tipo": "gameover", "raw": "GAMEOVER"})

    def enviar_log(self, mensaje: str):
        self.enviar({"tipo": "log", "raw": mensaje, "mensaje": mensaje})

    def hay_clientes(self) -> bool:
        """Retorna True si hay al menos un cliente WebSocket conectado."""
        return bool(self._clientes)
