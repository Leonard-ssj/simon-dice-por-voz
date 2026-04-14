#!/usr/bin/env python3
# ============================================================
# servidor.py — Orquestador principal del juego
#
# Conecta todos los módulos:
#   - serial_bridge  → comunicación con ESP32
#   - whisper_engine → pipeline de audio + transcripción
#   - juego          → máquina de estados del Simon Dice
#   - ws_server      → WebSocket para el panel web
#   - tts            → narrador de voz en laptop
#
# Uso:
#   cd servidor_pc
#   python servidor.py
#
#   Luego en otra terminal:
#   cd web-panel && npm run dev
#   Abrir Chrome/Edge en http://localhost:3000
#   Seleccionar "Simulador — WebSocket" y conectar.
#
# PTT:
#   - Botón físico SW1 (GPIO0) en el ESP32
#   - Barra espaciadora en el panel web (Chrome/Edge)
# ============================================================

import sys
import os
import threading
import time

# Asegurar que los módulos del paquete sean encontrables
sys.path.insert(0, os.path.dirname(__file__))

from config import DEBUG
from tts import (
    inicializar_tts, esperar_tts,
    decir, decir_color, reproducir_sonido,
)
from ws_server     import ServidorWS
from serial_bridge import SerialBridge
from whisper_engine import WhisperEngine

# Reutilizar la máquina de estados del simulador (sin cambios)
# Agregamos sys.path para poder importarla directamente
_SIM_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "simulador_pc")
sys.path.insert(0, os.path.abspath(_SIM_PATH))
from juego_sim import JuegoSimulador, Estado


# ─── Instancias globales ──────────────────────────────────────────────────────
from config import TIMEOUT_RESPUESTA as _TIMEOUT_MS
juego   = JuegoSimulador(timeout_ms=_TIMEOUT_MS)  # usa config.py (60s), no config_test.py (30s)
ws      = ServidorWS()
serial  = SerialBridge()
whisper = WhisperEngine()


# ─── Colores ANSI para la terminal ───────────────────────────────────────────
C = {
    "info":    "\033[37m",
    "ok":      "\033[32m",
    "error":   "\033[31m",
    "estado":  "\033[36m",
    "voz":     "\033[34m",
    "sistema": "\033[33m",
    "reset":   "\033[0m",
}


def log(msg: str, tipo: str = "info"):
    color = C.get(tipo, "")
    print(f"{color}  {msg}{C['reset']}")


# ─── Nombres de estado en español ────────────────────────────────────────────
_ESTADO_ES = {
    Estado.IDLE:             "Esperando",
    Estado.SHOWING_SEQUENCE: "Mostrando secuencia",
    Estado.LISTENING:        "Escuchando",
    Estado.EVALUATING:       "Procesando",
    Estado.CORRECT:          "Correcto",
    Estado.LEVEL_UP:         "Nivel superado",
    Estado.WRONG:            "Incorrecto",
    Estado.GAME_OVER:        "Fin del juego",
    Estado.PAUSA:            "Pausa",
}

# ─── Mensajes OLED por estado ─────────────────────────────────────────────────
_OLED_ESTADO = {
    Estado.IDLE:             ("Simon Dice",    "Di EMPIEZA",     "para comenzar"),
    Estado.SHOWING_SEQUENCE: ("MOSTRANDO",     "secuencia",      ""),
    Estado.LISTENING:        ("TU TURNO",      "Presiona boton", "y habla"),
    Estado.EVALUATING:       ("Procesando...", "Whisper",        ""),
    Estado.CORRECT:          ("CORRECTO!",     "",               ""),
    Estado.LEVEL_UP:         ("NIVEL UP!",     "",               ""),
    Estado.WRONG:            ("INCORRECTO",    "",               ""),
    Estado.GAME_OVER:        ("GAME OVER",     "",               "Di EMPIEZA"),
    Estado.PAUSA:            ("PAUSA",         "Di EMPIEZA",     "para continuar"),
}


# ─── Callbacks del juego ─────────────────────────────────────────────────────

def _on_estado(estado: Estado):
    nombre_es = _ESTADO_ES.get(estado, estado.value)
    log(f"[Estado] {nombre_es}", "estado")

    # Actualizar panel web
    ws.enviar_estado(estado.value)

    # Actualizar OLED del ESP32
    oled = _OLED_ESTADO.get(estado, (estado.value, "", ""))
    serial.enviar_oled(*oled)

    # Narración TTS por estado — _reservar_ventana_tts() bloquea el PTT
    # durante la narración para que el MAX4466 no capture la voz del narrador.
    if estado == Estado.SHOWING_SEQUENCE:
        _reservar_ventana_tts("Mira y escucha.")
        decir("Mira y escucha.", bloquear=False)

    elif estado == Estado.LISTENING:
        _reservar_ventana_tts("Tu turno. Presiona ESPACIO para hablar.")
        decir("Tu turno. Presiona ESPACIO para hablar.", bloquear=False)

    elif estado == Estado.PAUSA:
        _reservar_ventana_tts("Juego pausado.")
        decir("Juego pausado.", bloquear=False)

    elif estado == Estado.GAME_OVER:
        pts = juego.puntuacion
        _reservar_ventana_tts(f"Fin del juego. Obtuviste {pts} puntos. Di empieza para volver a jugar.")

        def _narrar():
            time.sleep(0.3)
            decir(f"Fin del juego. Obtuviste {pts} puntos.", bloquear=False)
            decir("Di empieza para volver a jugar.", bloquear=False)

        threading.Thread(target=_narrar, daemon=True).start()


def _on_led_encender(color: str):
    log(f"[LED] Encender: {color}", "sistema")
    serial.enviar_led(color)
    ws.enviar_led_activo(color)


def _on_led_apagar(color: str):
    serial.enviar_led("OFF")
    ws.enviar_led_activo(None)


def _on_leds_apagar():
    serial.enviar_led("OFF")
    ws.enviar_led_activo(None)


def _on_sonido(tipo: str, extra=None):
    threading.Thread(
        target=reproducir_sonido,
        args=(tipo, extra),
        daemon=True,
    ).start()

    if tipo == "color" and extra:
        # TTS del color (bloqueante — sincroniza con el LED visual).
        # También reserva ventana: el nombre del color suena mientras el LED
        # está encendido → el usuario no debería grabar en ese momento.
        _reservar_ventana_tts(extra.lower(), extra_seg=1.5)
        decir_color(extra)


def _on_secuencia(seq: list):
    log(f"[Secuencia] {' → '.join(seq)}", "sistema")
    ws.enviar_secuencia(seq)


def _on_esperado(color: str):
    log(f"[Escuchando] Esperando: {color}", "voz")
    ws.enviar_esperado(color)


def _on_nivel(n: int):
    log(f"[Nivel] {n}", "sistema")
    ws.enviar_nivel(n)
    # OLED: nivel actual
    serial.enviar_oled(f"NIVEL {n}", "Bien hecho!", "")
    if n > 1:
        _reservar_ventana_tts(f"Nivel {n}.")
        threading.Thread(
            target=lambda: decir(f"Nivel {n}.", bloquear=False),
            daemon=True,
        ).start()


def _on_puntuacion(p: int):
    ws.enviar_puntuacion(p)


def _on_resultado(r: str):
    tipo = "ok" if r == "CORRECT" else "error"
    etiqueta = {"CORRECT": "Correcto", "WRONG": "Incorrecto", "TIMEOUT": "Tiempo agotado"}.get(r, r)
    log(f"[Resultado] {etiqueta}", tipo)
    ws.enviar_resultado(r)

    if r == "CORRECT":
        _reservar_ventana_tts("Correcto.")
        decir("Correcto.", bloquear=False)

    elif r == "WRONG":
        _reservar_ventana_tts("Incorrecto. Di empieza para intentar de nuevo.")
        def _narrar():
            time.sleep(0.2)
            decir("Incorrecto.", bloquear=False)
            decir("Di empieza para intentar de nuevo.", bloquear=False)
        threading.Thread(target=_narrar, daemon=True).start()

    elif r == "TIMEOUT":
        _reservar_ventana_tts("Tiempo agotado. Di empieza para intentar de nuevo.")
        def _narrar():
            time.sleep(0.2)
            decir("Tiempo agotado.", bloquear=False)
            decir("Di empieza para intentar de nuevo.", bloquear=False)
        threading.Thread(target=_narrar, daemon=True).start()


def _on_log(msg: str):
    log(msg, "info")
    ws.enviar_log(msg)


_juego_iniciado        = False   # el juego arranca solo cuando el panel conecta por primera vez
_ignorar_proximo_audio = False   # True si el PTT llegó antes del panel o durante ventana de boot
_ignorar_ptt_hasta     = 0.0    # time.time() límite — ignora PTT durante ventana de boot
_bloqueo_tts_hasta     = 0.0    # time.time() límite — ignora PTT mientras TTS está narrando
_whisper_procesando    = False   # True mientras Whisper transcribe — el tick NO dispara timeout


def _reservar_ventana_tts(texto: str, extra_seg: float = 2.5):
    """
    Registra que el TTS va a hablar 'texto' y bloquea el PTT durante
    la duración estimada + margen.

    Llámalo ANTES de decir() o del thread que va a hablar, para que
    cualquier spacebar que el usuario pulse durante la narración sea ignorado
    (el MAX4466 captaría la voz del narrador y Whisper lo transcribiría).

    Fórmula: 0.5s por palabra + extra_seg de margen (latencia TTS + eco mic).
    """
    global _bloqueo_tts_hasta
    palabras   = len(texto.split())
    duracion   = palabras * 0.5 + extra_seg
    nuevo_fin  = time.time() + duracion
    if nuevo_fin > _bloqueo_tts_hasta:
        _bloqueo_tts_hasta = nuevo_fin

def _on_cliente_conectado():
    """
    Callback cuando el panel web abre la conexión WebSocket.

    La primera vez: inicializa el motor del juego y narra la bienvenida.
    Reconexiones posteriores: solo narra bienvenida (el juego ya está corriendo).

    Ventana de arranque: durante 10s post-conexión cualquier PTT del ESP32 se descarta.
    Esto evita que la grabación de GPIO0 (que queda LOW en boot) capture la voz del TTS
    o que una pulsación accidental durante la bienvenida procese audio con Whisper.
    """
    global _juego_iniciado, _ignorar_ptt_hasta

    # Activar ventana de 10s durante la cual se descartan PTT del ESP32.
    # El MAX4466 capta la voz del TTS de la laptop — el usuario no ha dicho nada.
    _ignorar_ptt_hasta = time.time() + 10.0

    if not _juego_iniciado:
        _juego_iniciado = True
        log("[Panel] Primer cliente conectado — iniciando juego", "sistema")
        juego.iniciar()     # transiciona a IDLE y registra los callbacks de estado

    time.sleep(0.5)
    log("[Panel] Cliente conectado — narrando bienvenida", "sistema")
    _reservar_ventana_tts("Simon Dice listo. Presiona ESPACIO para comenzar.")
    decir("Simon Dice listo. Presiona ESPACIO para comenzar.", bloquear=False)


# ─── Callbacks del Serial / audio ────────────────────────────────────────────

def _on_esp32_ready():
    """ESP32 envió READY — sistema de hardware listo."""
    log("[ESP32] READY — hardware listo", "sistema")
    serial.enviar_oled("Simon Dice", "Conectado al PC", "")


def _on_ptt_start():
    """ESP32 empezó a grabar (Serial 'R' — spacebar del panel)."""
    global _ignorar_proximo_audio

    # Caso A: sin panel conectado todavía
    if not ws.hay_clientes():
        _ignorar_proximo_audio = True
        log("[PTT] Sin panel — grabación descartada (pre-conexión)", "sistema")
        return

    # Caso B: ventana de arranque — TTS de bienvenida puede estar sonando.
    if time.time() < _ignorar_ptt_hasta:
        _ignorar_proximo_audio = True
        restante = round(_ignorar_ptt_hasta - time.time(), 1)
        log(f"[PTT] Ignorado — ventana de arranque ({restante}s restantes)", "sistema")
        return

    # Caso C: TTS narrando — el MAX4466 captaría la voz del narrador.
    # Si el usuario pulsa ESPACIO mientras la voz habla, el audio grabado
    # contendría la narración y Whisper la transcribiría como comando.
    if time.time() < _bloqueo_tts_hasta:
        _ignorar_proximo_audio = True
        restante = round(_bloqueo_tts_hasta - time.time(), 1)
        log(f"[PTT] Ignorado — narrador hablando ({restante}s restantes)", "sistema")
        ws.enviar_log(f"Espera {restante:.0f}s al narrador antes de hablar…")
        serial.enviar_oled("Espera...", "Narrador", "hablando")
        return

    _ignorar_proximo_audio = False
    log("[PTT] Grabación iniciada", "voz")
    juego.pausar_timeout()
    ws.enviar_log("🔴 Grabando...")


def _on_ptt_stop():
    """ESP32 detuvo la grabación."""
    log("[PTT] Grabación detenida — procesando audio", "voz")
    # El firmware muestra "Procesando... Whisper espera ~30s" en el OLED
    # en cuanto el botón se suelta (hardcoded en detener_y_enviar()).
    # Si el panel aún no está conectado, ese mensaje quedaría fijo para siempre.
    # Lo reemplazamos con un mensaje neutral inmediatamente.
    if not ws.hay_clientes():
        serial.enviar_oled("Simon Dice", "Conecta el panel", "web para jugar")


def _on_audio_recibido(pcm_bytes: bytes):
    """
    Recibe los bytes PCM del ESP32 y los procesa con Whisper.
    Se ejecuta en un hilo separado (spawneado por serial_bridge).
    """
    global _ignorar_proximo_audio, _whisper_procesando

    # Caso 1: audio capturado en ventana de boot/bienvenida/TTS — descartar silenciosamente
    if _ignorar_proximo_audio:
        _ignorar_proximo_audio = False
        _whisper_procesando    = False
        log("[Audio] Grabación descartada (boot / narrador / bienvenida)", "sistema")
        juego.reanudar_timeout()
        # Resetear OLED — el firmware lo dejó en "Procesando... espera..."
        serial.enviar_oled("Simon Dice", "Di EMPIEZA", "para comenzar")
        return

    # Caso 2: panel se desconectó justo antes de recibir el audio
    if not ws.hay_clientes():
        _whisper_procesando = False
        log("[Audio] Sin panel web conectado — audio ignorado", "sistema")
        juego.reanudar_timeout()
        # Resetear OLED
        serial.enviar_oled("Simon Dice", "Conecta el panel", "web para jugar")
        return

    # Pausar el timer AQUÍ, no solo en PTT_START.
    # Si el PTT llegó durante SHOWING_SEQUENCE, pausar_timeout() no hizo nada
    # porque el juego aún no estaba en LISTENING. Cuando pasó a LISTENING el
    # timer arrancó ya con Whisper corriendo → TIMEOUT.
    # Pausa defensiva: si ya estaba pausado, no hace daño volver a pausar.
    juego.pausar_timeout()

    # Flag global: el hilo de tick no llama juego.tick() mientras Whisper procesa.
    # Esto evita que el timeout expire si el estado LISTENING comenzó DURANTE la
    # transcripción (ej: PTT pulsado en SHOWING, Whisper tarda 20s, LISTENING empieza
    # y el timer lleva ventaja antes de que podamos pausarlo).
    _whisper_procesando = True

    duracion = len(pcm_bytes) / (8000 * 2)
    log(f"[Audio] Recibido {len(pcm_bytes)} bytes ({duracion:.1f}s)", "voz")

    # Transcribir con Whisper (pipeline completo)
    texto, comando = whisper.transcribir(pcm_bytes)

    # Reanudar timer ANTES de procesar el comando y limpiar el flag global
    _whisper_procesando = False
    juego.reanudar_timeout()

    # Informar al panel web — siempre, con o sin texto
    ws.enviar_voz(texto, comando)

    if texto:
        log(f'[Voz] Whisper: "{texto}" → {comando}', "voz")
        # Mostrar en el log del panel para que el usuario vea qué captó Whisper
        ws.enviar_log(f'Whisper: "{texto}" → {comando}')
    else:
        log("[Voz] Whisper: sin habla detectada", "info")
        ws.enviar_log("Whisper: sin habla detectada (intenta de nuevo)")

    # Procesar en el motor del juego
    if comando != "DESCONOCIDO":
        juego.procesar_comando(comando)


def _on_audio_corto():
    """Grabación demasiado corta."""
    log("[PTT] Audio muy corto — ignorado", "info")
    juego.reanudar_timeout()
    ws.enviar_log("PTT muy corto — habla más tiempo.")


def _on_comando_panel(cmd: str):
    """Fallback WASM: el panel mandó el comando como texto."""
    log(f"[Panel/WASM] Comando: {cmd}", "voz")
    ws.enviar_log(f"Comando (WASM): {cmd}")
    juego.procesar_comando(cmd)


# ─── Registro de callbacks ───────────────────────────────────────────────────

def _registrar_callbacks():
    # Juego → mundo exterior
    juego.on_estado_cambio = _on_estado
    juego.on_mostrar_led   = _on_led_encender
    juego.on_apagar_led    = _on_led_apagar
    juego.on_apagar_todos  = _on_leds_apagar
    juego.on_sonido        = _on_sonido
    juego.on_secuencia     = _on_secuencia
    juego.on_esperado      = _on_esperado
    juego.on_nivel         = _on_nivel
    juego.on_puntuacion    = _on_puntuacion
    juego.on_resultado     = _on_resultado
    juego.on_log           = _on_log

    # ESP32 Serial → servidor
    serial.on_ready          = _on_esp32_ready
    serial.on_ptt_start      = _on_ptt_start
    serial.on_ptt_stop       = _on_ptt_stop
    serial.on_audio_recibido = _on_audio_recibido
    serial.on_audio_corto    = _on_audio_corto
    serial.on_log            = _on_log

    # Panel web → servidor
    ws.on_ptt_inicio        = serial.iniciar_ptt_remoto    # spacebar → 'R' al ESP32
    ws.on_ptt_fin           = serial.detener_ptt_remoto    # soltar   → 'T' al ESP32
    ws.on_pausar_timeout    = juego.pausar_timeout          # pre-pausa (evita race condition)
    ws.on_comando           = _on_comando_panel             # fallback WASM
    ws.on_cliente_conectado = _on_cliente_conectado


# ─── Hilo de tick (timeout del turno) ────────────────────────────────────────

def _hilo_tick():
    """
    Llama a juego.tick() cada 200ms para verificar timeout.
    Se salta el tick si Whisper está procesando (_whisper_procesando=True):
    el timeout del turno no debe expirar mientras el modelo está transcribiendo.
    """
    while True:
        if not _whisper_procesando:
            juego.tick()
        time.sleep(0.2)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 58)
    print("   SIMON DICE POR VOZ — Servidor PC")
    print("=" * 58)
    print("  1. El ESP32 debe estar conectado por USB.")
    print("  2. Abrir Chrome o Edge en:")
    print("     http://localhost:3000")
    print("  3. Seleccionar el tab  'Servidor PC'")
    print("  4. Hacer clic en 'Conectar'  ← el juego inicia aquí")
    print("  5. Presionar ESPACIO y hablar (el botón físico también funciona)")
    print("=" * 58)
    print()

    # 1. Inicializar TTS (hilo background)
    inicializar_tts()

    # 2. Cargar Whisper (bloquea ~5-8s la primera vez que el modelo ya está cacheado)
    print("[1/4] Cargando Whisper...")
    if not whisper.cargar():
        print("[ERROR] No se pudo cargar Whisper.")
        print("        Instalar: pip install openai-whisper")
        sys.exit(1)

    # 3. Conectar al ESP32 por Serial
    print("[2/4] Conectando al ESP32...")
    if not serial.conectar():
        print("[ERROR] No se pudo conectar al ESP32.")
        print("        Verificar: USB conectado, drivers CH340/CP210x instalados.")
        sys.exit(1)

    # 4. Iniciar servidor WebSocket
    print("[3/4] Iniciando servidor WebSocket...")
    ws.iniciar()

    # 5. Registrar callbacks (el juego arranca cuando el panel conecta)
    print("[4/4] Registrando callbacks — esperando conexión del panel web...")
    _registrar_callbacks()
    # juego.iniciar() lo llama _on_cliente_conectado() la primera vez que el panel conecta.
    # Así evitamos procesar audio antes de que el operador haya abierto el panel.

    # Hilo de tick para timeouts
    threading.Thread(target=_hilo_tick, daemon=True, name="tick").start()

    # TTS de bienvenida
    def _bienvenida():
        if esperar_tts(timeout=5.0):
            decir("Servidor listo. Abre el panel web y conecta.", bloquear=True)

    threading.Thread(target=_bienvenida, daemon=True, name="bienvenida").start()

    log("Servidor listo. Esperando conexión del panel web...", "sistema")
    print()

    # Loop principal
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("  Servidor detenido.")
        serial.desconectar()
        print()


if __name__ == "__main__":
    main()
