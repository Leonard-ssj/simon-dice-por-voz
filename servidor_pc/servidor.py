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
    inicializar_tts, tts_hablando, cancelar_tts,
    activar_voz_esp32, notificar_voz_fin, esperar_voz_fin, cancelar_voz_esp32,
)
from ws_server     import ServidorWS
from serial_bridge import SerialBridge
from whisper_engine import WhisperEngine

# Reutilizar la máquina de estados del simulador (sin cambios)
# Agregamos sys.path para poder importarla directamente
_SIM_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "simulador_pc")
sys.path.insert(0, os.path.abspath(_SIM_PATH))
from juego_sim import JuegoSimulador, Estado
from validador import texto_a_colores


# ─── Instancias globales ──────────────────────────────────────────────────────
from config import (
    TIMEOUT_RESPUESTA as _TIMEOUT_MS,
    DURACION_LED_SIM  as _LED_MS,
    PAUSA_ENTRE_LEDS  as _PAUSA_MS,
    WHISPER_TIMEOUT   as _WHISPER_TIMEOUT_S,
)
juego   = JuegoSimulador(
    timeout_ms=_TIMEOUT_MS,         # 60s — config.py, no config_test.py (30s)
    duracion_led_ms=_LED_MS,        # 800ms — evita importar de config_test.py
    pausa_leds_ms=_PAUSA_MS,        # 300ms
)
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
# None = dinámico, generado por _oled_juego_info()
_OLED_ESTADO = {
    Estado.IDLE:             ("Simon Dice",    "Di EMPIEZA",     "para comenzar"),
    Estado.SHOWING_SEQUENCE: ("MOSTRANDO",     "secuencia",      ""),
    Estado.LISTENING:        None,             # dinámico: nivel + puntos + posición
    Estado.EVALUATING:       ("Procesando...", "Whisper",        ""),
    Estado.CORRECT:          ("CORRECTO!",     "",               ""),
    Estado.LEVEL_UP:         ("NIVEL UP!",     "",               ""),
    Estado.WRONG:            ("INCORRECTO",    "",               ""),
    Estado.GAME_OVER:        ("GAME OVER",     "",               "Di EMPIEZA"),
    Estado.PAUSA:            ("PAUSA",         "Di EMPIEZA",     "para continuar"),
}


def _oled_juego_info() -> tuple:
    """OLED dinámico para LISTENING: nivel, puntos y posición en secuencia."""
    n   = juego.nivel
    p   = juego.puntuacion
    pos = juego.pos_escuchar
    tot = n
    return ("TU TURNO", f"Nv{n} Pts:{p} {pos+1}/{tot}", "Presiona ESPACIO")


# ─── Callbacks del juego ─────────────────────────────────────────────────────

def _on_estado(estado: Estado):
    global _estado_previo, _primer_turno_juego
    nombre_es = _ESTADO_ES.get(estado, estado.value)
    log(f"[Estado] {nombre_es}", "estado")

    # Actualizar panel web
    ws.enviar_estado(estado.value)

    # Actualizar OLED del ESP32 — None en el dict = dinámico
    oled = _OLED_ESTADO.get(estado, (estado.value, "", ""))
    if oled is None:
        oled = _oled_juego_info()
    serial.enviar_oled(*oled)

    # Narración por estado — toda la voz sale por la bocina del ESP32.
    if estado == Estado.SHOWING_SEQUENCE:
        serial.enviar_voz("mira_escucha")
        activar_voz_esp32()

    elif estado == Estado.LISTENING:
        if _estado_previo == Estado.EVALUATING:
            # Color(es) correcto(s) pero quedan más en la secuencia
            if _ultimos_aceptados > 1:
                serial.enviar_voz(f"correctos_{_ultimos_aceptados:02d}")
            else:
                serial.enviar_voz("correcto_turno")
            activar_voz_esp32()
        elif _primer_turno_juego:
            # Primer turno de la partida → orientar al jugador
            serial.enviar_voz("turno_primero")
            activar_voz_esp32()
            _primer_turno_juego = False
        else:
            # Turno normal (post-nivel, post-repite, etc.)
            serial.enviar_voz("turno")
            activar_voz_esp32()

    elif estado == Estado.CORRECT:
        # Secuencia completa → LEVEL_UP vendrá enseguida; solo confirmar
        serial.enviar_voz("correcto")
        activar_voz_esp32()

    elif estado == Estado.IDLE:
        _primer_turno_juego = True   # nueva partida: resetear orientación

    elif estado == Estado.PAUSA:
        serial.enviar_voz("pausado")
        activar_voz_esp32()

    elif estado == Estado.GAME_OVER:
        pts = juego.puntuacion

        def _narrar():
            time.sleep(0.3)
            serial.enviar_voz(f"fin_{pts:04d}")
            activar_voz_esp32()
            esperar_voz_fin(timeout=8.0)    # espera a que termine antes del segundo audio
            serial.enviar_voz("di_volver")
            activar_voz_esp32()

        threading.Thread(target=_narrar, daemon=True).start()

    _estado_previo = estado


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


def _on_sonido(tipo: str, _extra=None):
    if tipo == "color":
        pass   # El LED:COLOR ya dispara tono + voz del color en el ESP32 automáticamente
    else:
        # Fanfarria de tonos (correcto, error, inicio, gameover) → bocina ESP32
        serial.enviar_sonido(tipo)


def _on_secuencia(seq: list):
    log(f"[Secuencia] {' → '.join(seq)}", "sistema")
    ws.enviar_secuencia(seq)


def _on_esperado(color: str):
    log(f"[Escuchando] Esperando: {color}", "voz")
    ws.enviar_esperado(color)


def _on_nivel(n: int):
    log(f"[Nivel] {n}", "sistema")
    ws.enviar_nivel(n)
    pts = juego.puntuacion
    serial.enviar_oled(f"NIVEL {n}!", f"Puntos: {pts}", "Bien hecho!")
    if n > 1:
        def _narrar_nivel():
            serial.enviar_voz(f"nivel_{n:02d}")
            activar_voz_esp32()
        threading.Thread(target=_narrar_nivel, daemon=True).start()


def _on_puntuacion(p: int):
    ws.enviar_puntuacion(p)


def _on_resultado(r: str):
    tipo = "ok" if r == "CORRECT" else "error"
    etiqueta = {"CORRECT": "Correcto", "WRONG": "Incorrecto", "TIMEOUT": "Tiempo agotado"}.get(r, r)
    log(f"[Resultado] {etiqueta}", tipo)
    ws.enviar_resultado(r)

    if r == "CORRECT":
        pass   # la voz la maneja _on_estado(LISTENING) o _on_estado(CORRECT)

    elif r == "WRONG":
        def _narrar_wrong():
            time.sleep(0.2)
            serial.enviar_voz("incorrecto")
            activar_voz_esp32()
            esperar_voz_fin(timeout=5.0)
            serial.enviar_voz("di_empieza")
            activar_voz_esp32()
        threading.Thread(target=_narrar_wrong, daemon=True).start()

    elif r == "TIMEOUT":
        def _narrar_timeout():
            time.sleep(0.2)
            serial.enviar_voz("tiempo_agotado")
            activar_voz_esp32()
            esperar_voz_fin(timeout=5.0)
            serial.enviar_voz("di_empieza")
            activar_voz_esp32()
        threading.Thread(target=_narrar_timeout, daemon=True).start()


def _on_log(msg: str):
    log(msg, "info")
    ws.enviar_log(msg)


_juego_iniciado       = False   # el juego arranca solo cuando el panel conecta por primera vez
_whisper_procesando   = False   # True mientras Whisper transcribe — el tick NO dispara timeout
_whisper_hilo_activo: threading.Thread | None = None  # hilo Whisper activo — evita concurrencia
_ptt_spacebar_activo  = False   # True SOLO cuando spacebar inició el PTT — descarta todo lo demás
_estado_previo        = None    # Estado anterior — detecta de dónde viene LISTENING
_primer_turno_juego   = True    # True en el primer turno de cada partida (TTS orientativo)
_ultimos_aceptados    = 0       # Colores aceptados en el último multi-color (para TTS informativo)

def _on_cliente_conectado():
    """
    Callback cuando el panel web abre la conexión WebSocket.
    La primera vez: inicializa el motor del juego y narra la bienvenida.
    Reconexiones posteriores: solo narra bienvenida.
    El guard de spacebar (_ptt_spacebar_activo) ya garantiza que ningún audio
    del ESP32 se procese hasta que el usuario presione spacebar.
    """
    global _juego_iniciado

    if not _juego_iniciado:
        _juego_iniciado = True
        log("[Panel] Primer cliente conectado — iniciando juego", "sistema")
        juego.iniciar()

    time.sleep(0.5)
    log("[Panel] Cliente conectado — narrando bienvenida", "sistema")
    serial.enviar_voz("simon_listo")
    activar_voz_esp32()


# ─── Callbacks del Serial / audio ────────────────────────────────────────────

def _on_esp32_ready():
    """ESP32 envió READY — sistema de hardware listo."""
    log("[ESP32] READY — hardware listo", "sistema")
    serial.enviar_oled("Simon Dice", "Conectado al PC", "")


def _verificar_condiciones_ptt() -> bool:
    """
    Comprueba si el PTT (spacebar) debe aceptarse en este momento.
    Solo se llama desde _iniciar_ptt_con_check (spacebar).
    Retorna True si está bien grabar, False si debe ignorarse.
    """
    if not ws.hay_clientes():
        juego.reanudar_timeout()
        log("[PTT] Sin panel — ignorado", "sistema")
        return False

    if tts_hablando():
        # NO reanudar_timeout() — _hilo_tick ya no avanza el timer mientras tts_hablando()
        # El timer se reanudará solo cuando el narrador termine
        log("[PTT] Ignorado — narrador hablando", "sistema")
        ws.enviar_log("Espera al narrador antes de hablar…")
        serial.enviar_oled("Espera...", "Narrador", "hablando")
        return False

    if juego.estado == Estado.SHOWING_SEQUENCE:
        juego.reanudar_timeout()
        log("[PTT] Ignorado — mostrando secuencia", "sistema")
        serial.enviar_oled("Espera...", "Mira la", "secuencia")
        return False

    return True


def _iniciar_ptt_con_check():
    """
    Callback para ws.on_ptt_inicio (spacebar del panel).
    Única vía autorizada para iniciar una grabación.
    El ESP32 puede mandar PTT_START solo (botón físico, firmware de test en bucle),
    pero ese audio NUNCA se procesa — solo se procesa si spacebar lo inició.
    """
    global _ptt_spacebar_activo
    if not _verificar_condiciones_ptt():
        # El panel ya puso rawGrabando=True al enviar PTT_INICIO.
        # Como no vamos a grabar nada, enviamos "voz" vacío para que el panel
        # limpie rawGrabando/rawProcesando antes de que llegue PTT_FIN.
        ws.enviar_voz("", "DESCONOCIDO")
        return
    _ptt_spacebar_activo = True   # autorizar el próximo bloque de audio
    log("[PTT] Grabación iniciada (spacebar)", "voz")
    ws.enviar_log("🔴 Grabando...")
    serial.iniciar_ptt_remoto()


def _on_ptt_start():
    pass   # el audio se acepta/descarta en _on_audio_recibido según _ptt_spacebar_activo


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
    global _whisper_procesando, _whisper_hilo_activo, _ptt_spacebar_activo

    # Caso 0: audio NO iniciado por spacebar — descartar silenciosamente.
    # El ESP32 puede mandar bloques en bucle (firmware de test, botón físico).
    # No enviamos nada al panel porque nunca estuvo en estado "procesando".
    if not _ptt_spacebar_activo:
        if DEBUG:
            log("[Audio] Descartado — no iniciado por spacebar", "sistema")
        return

    _ptt_spacebar_activo = False   # consumir el token

    # Caso 1: panel se desconectó justo antes de recibir el audio
    if not ws.hay_clientes():
        _whisper_procesando = False
        log("[Audio] Sin panel web conectado — audio ignorado", "sistema")
        juego.reanudar_timeout()
        serial.enviar_oled("Simon Dice", "Conecta el panel", "web para jugar")
        return

    # Caso 3: Whisper aún está corriendo del turno anterior (timeout no lo mató).
    # WhisperEngine no es thread-safe — evitar llamada concurrente.
    if _whisper_hilo_activo is not None and _whisper_hilo_activo.is_alive():
        log("[Audio] Whisper aún ocupado — audio descartado", "error")
        ws.enviar_log("Whisper aún procesando — intenta de nuevo en un momento")
        ws.enviar_voz("", "DESCONOCIDO")
        juego.reanudar_timeout()
        return

    # Pausar el timer AQUÍ, no solo en PTT_START.
    # Si el PTT llegó durante SHOWING_SEQUENCE, pausar_timeout() no hizo nada
    # porque el juego aún no estaba en LISTENING. Cuando pasó a LISTENING el
    # timer arrancó ya con Whisper corriendo → TIMEOUT.
    # Pausa defensiva: si ya estaba pausado, no hace daño volver a pausar.
    juego.pausar_timeout()

    # Flag global: el hilo de tick no llama juego.tick() mientras Whisper procesa.
    _whisper_procesando = True

    duracion = len(pcm_bytes) / (8000 * 2)
    log(f"[Audio] Recibido {len(pcm_bytes)} bytes ({duracion:.1f}s)", "voz")

    # Transcribir con Whisper — con timeout para evitar bloqueos largos.
    _resultado = [None, None]

    def _transcribir():
        _resultado[0], _resultado[1] = whisper.transcribir(pcm_bytes)

    hilo_whisper = threading.Thread(target=_transcribir, daemon=True, name="whisper-transcribe")
    _whisper_hilo_activo = hilo_whisper
    hilo_whisper.start()
    hilo_whisper.join(timeout=_WHISPER_TIMEOUT_S)

    if hilo_whisper.is_alive():
        _whisper_procesando  = False
        _whisper_hilo_activo = None   # liberar — el hilo daemon morirá solo; permite reintentar
        juego.reanudar_timeout()
        log(f"[Audio] Whisper tardó más de {_WHISPER_TIMEOUT_S}s — descartando", "error")
        ws.enviar_log(f"Whisper tardó demasiado ({_WHISPER_TIMEOUT_S}s) — intenta de nuevo")
        ws.enviar_voz("", "DESCONOCIDO")   # resetear panel
        serial.enviar_oled("Intenta", "de nuevo", "")
        return

    texto   = _resultado[0] or ""
    comando = _resultado[1] or "DESCONOCIDO"

    # Reanudar timer ANTES de procesar el comando y limpiar el flag global
    _whisper_procesando = False
    juego.reanudar_timeout()

    # Informar al panel web — siempre, con o sin texto
    ws.enviar_voz(texto, comando)

    if texto:
        log(f'[Voz] Whisper: "{texto}" → {comando}', "voz")
        ws.enviar_log(f'Whisper: "{texto}" → {comando}')
    else:
        log("[Voz] Whisper: sin habla detectada", "info")
        ws.enviar_log("Whisper: sin habla detectada (intenta de nuevo)")

    # Cancelar audio pendiente si el comando es REINICIAR o PARA
    if comando in ("REINICIAR", "PARA"):
        cancelar_tts()
        cancelar_voz_esp32()

    # ── Detección multi-color ──────────────────────────────────────────────
    # Si el audio contiene 2+ colores reconocibles → modo multi-color.
    # Si contiene 0-1 colores → camino normal con procesar_comando().
    # texto_a_colores para en la primera palabra no reconocida como color.
    global _ultimos_aceptados
    colores_detectados = texto_a_colores(texto) if texto else []

    if len(colores_detectados) >= 2 and juego.estado == Estado.LISTENING:
        n = len(colores_detectados)
        log(f"[Multi] {n} colores detectados: {' → '.join(colores_detectados)}", "voz")
        ws.enviar_log(f"Multi-color: {' → '.join(colores_detectados)}")
        _ultimos_aceptados = juego.procesar_colores_multiples(colores_detectados)
        log(f"[Multi] {_ultimos_aceptados}/{n} aceptados", "ok" if _ultimos_aceptados else "error")
    elif comando != "DESCONOCIDO":
        _ultimos_aceptados = 0
        juego.procesar_comando(comando)


def _on_audio_corto():
    """Grabación demasiado corta."""
    log("[PTT] Audio muy corto — ignorado", "info")
    juego.reanudar_timeout()
    ws.enviar_log("PTT muy corto — habla más tiempo.")
    ws.enviar_voz("", "DESCONOCIDO")   # resetear panel (sale de "Grabando..."/"Procesando...")


def _on_comando_panel(cmd: str):
    """Fallback WASM: el panel mandó el comando como texto."""
    log(f"[Panel/WASM] Comando: {cmd}", "voz")
    ws.enviar_log(f"Comando (WASM): {cmd}")
    if cmd in ("REINICIAR", "PARA"):
        cancelar_tts()
        cancelar_voz_esp32()
    juego.procesar_comando(cmd)


def _on_todos_desconectados():
    """Todos los clientes del panel se desconectaron — cancelar audio activo."""
    cancelar_tts()
    cancelar_voz_esp32()
    log("[Panel] Todos los clientes desconectados — audio cancelado", "sistema")


# ─── Callback VOZ_FIN ────────────────────────────────────────────────────────

def _on_voz_fin():
    """ESP32 terminó de reproducir el audio solicitado por VOZ:."""
    notificar_voz_fin()


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
    serial.on_voz_fin        = _on_voz_fin           # ESP32 terminó de hablar
    serial.on_log            = _on_log

    # Panel web → servidor
    ws.on_ptt_inicio           = _iniciar_ptt_con_check     # pre-check → 'R' al ESP32 solo si OK
    ws.on_ptt_fin              = serial.detener_ptt_remoto  # soltar   → 'T' al ESP32
    ws.on_pausar_timeout       = juego.pausar_timeout        # pre-pausa (evita race condition)
    ws.on_comando              = _on_comando_panel           # fallback WASM
    ws.on_cliente_conectado    = _on_cliente_conectado
    ws.on_todos_desconectados  = _on_todos_desconectados     # cancelar audio al desconectar


# ─── Hilo de tick (timeout del turno) ────────────────────────────────────────

_tts_activo_prev = False   # estado TTS en el tick anterior — detecta transiciones

def _hilo_tick():
    """
    Llama a juego.tick() cada 200ms para verificar timeout.

    El timer NO avanza mientras Whisper transcribe o el narrador habla.
    Cuando TTS EMPIEZA: llama pausar_timeout() para congelar el timer.
    Cuando TTS TERMINA: llama reanudar_timeout() para reanudarlo correctamente,
      descontando exactamente el tiempo que el narrador habló.
    Esto garantiza que el usuario solo "pierde" tiempo cuando PUEDE hablar.
    """
    global _tts_activo_prev
    while True:
        tts_activo = tts_hablando()

        # Detectar transición TTS inició / TTS terminó
        if tts_activo and not _tts_activo_prev:
            juego.pausar_timeout()      # TTS arrancó → congelar timer
            ws.enviar_tts(True)         # panel pausa countdown + bloquea spacebar
        elif not tts_activo and _tts_activo_prev:
            juego.reanudar_timeout()    # TTS terminó → reanudar, descontando pausa
            ws.enviar_tts(False)        # panel reanuda countdown + habilita spacebar

        _tts_activo_prev = tts_activo

        if not _whisper_procesando and not tts_activo:
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

    # Audio de bienvenida por la bocina del ESP32
    def _bienvenida():
        # Esperar a que el ESP32 envíe READY antes de pedirle que hable
        time.sleep(2.0)
        serial.enviar_voz("srv_listo")
        activar_voz_esp32()

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
