#!/usr/bin/env python3
# ============================================================
# main.py — Simulador PC (reemplaza el kit ESP32 en pruebas)
#
# Corre el juego completo Simon Dice en tu PC:
#   - Speaker del sistema (sounddevice + pyttsx3) en vez del MAX98357A
#   - LEDs simulados en la terminal con colores ANSI
#   - WebSocket activo → el Web Panel se conecta en modo Simulador
#
# Reconocimiento de voz (preferido — Whisper local):
#   El browser graba audio PTT y envía frames binarios Float32 PCM 16kHz.
#   Python transcribe con Whisper local y devuelve el comando al panel.
#
# Reconocimiento de voz (fallback — Whisper WASM):
#   Si Whisper no cargó, el browser usa Whisper WASM y manda texto:
#   {"tipo": "comando", "comando": "ROJO"}
#
# Uso:
#   cd tests/simulador_pc
#   pip install -r requirements_test.txt
#   python main.py
#   → luego abre http://localhost:3000 en Chrome o Edge
#   → conecta al modo "Simulador WebSocket"
# ============================================================

import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from config_test import DEBUG
from juego_sim import JuegoSimulador, Estado
from audio_pc import (
    reproducir_sonido,
    inicializar_tts, esperar_tts, decir_color, decir,
)
from leds_sim import led_encender, led_apagar, leds_apagar_todos, nueva_linea
from ws_server import ServidorWS


# ---- Instancias globales ----
juego = JuegoSimulador()
ws    = ServidorWS()


# ---- Helpers de log con colores ANSI ----
COLORES_ANSI = {
    "info":    "\033[37m",
    "ok":      "\033[32m",
    "error":   "\033[31m",
    "estado":  "\033[36m",
    "voz":     "\033[34m",
    "sistema": "\033[33m",
    "reset":   "\033[0m",
}

def log(msg: str, tipo: str = "info"):
    nueva_linea()
    color = COLORES_ANSI.get(tipo, "")
    print(f"{color}  {msg}{COLORES_ANSI['reset']}")


# ---- Callbacks del juego ----

_NOMBRES_ESTADO_ES = {
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


def _on_estado(estado: Estado):
    nombre    = estado.value
    nombre_es = _NOMBRES_ESTADO_ES.get(estado, nombre)
    log(f"[Estado] {nombre_es}", "estado")
    ws.enviar_estado(nombre)

    if estado == Estado.SHOWING_SEQUENCE:
        decir("Mira y escucha.", bloquear=False)

    elif estado == Estado.LISTENING:
        decir("Tu turno.", bloquear=False)

    elif estado == Estado.EVALUATING:
        log("Procesando respuesta...", "info")
        ws.enviar_log("Procesando respuesta...")

    elif estado == Estado.PAUSA:
        decir("Juego pausado.", bloquear=False)

    elif estado == Estado.GAME_OVER:
        pts = getattr(juego, "puntuacion", 0)
        def _narrar_game_over():
            time.sleep(0.3)
            decir(f"Fin del juego. Obtuviste {pts} puntos.", bloquear=False)
            decir("Di empieza para volver a jugar.", bloquear=False)
        threading.Thread(target=_narrar_game_over, daemon=True).start()


def _on_led_encender(color: str):
    led_encender(color)
    ws.enviar_led_activo(color)


def _on_led_apagar(color: str):
    led_apagar(color)
    ws.enviar_led_activo(None)


def _on_leds_apagar():
    leds_apagar_todos()
    nueva_linea()


def _on_sonido(tipo: str, extra=None):
    if tipo == "color" and extra:
        # Tono primero (~400ms), luego TTS — evita conflicto de audio en Windows
        reproducir_sonido(tipo, extra)
        decir_color(extra)
    else:
        threading.Thread(target=reproducir_sonido, args=(tipo, extra), daemon=True).start()


def _on_secuencia(seq: list):
    log(f"[Secuencia] {' → '.join(seq)}", "sistema")
    ws.enviar_secuencia(seq)


def _on_esperado(color: str):
    log(f"[Escuchando] Esperando: {color}", "voz")
    ws.enviar_esperado(color)


def _on_nivel(n: int):
    log(f"[Nivel] {n}", "sistema")
    ws.enviar_nivel(n)
    def _narrar_nivel():
        decir("Correcto.", bloquear=False)
        if n > 1:
            decir(f"Nivel {n}.", bloquear=False)
    threading.Thread(target=_narrar_nivel, daemon=True).start()


def _on_puntuacion(p: int):
    ws.enviar_puntuacion(p)


def _on_resultado(r: str):
    tipo     = "ok" if r == "CORRECT" else "error"
    etiqueta = {
        "CORRECT": "Correcto",
        "WRONG":   "Incorrecto",
        "TIMEOUT": "Tiempo agotado",
    }.get(r, r)
    log(f"[Resultado] {etiqueta}", tipo)
    ws.enviar_resultado(r)

    if r == "WRONG":
        def _narrar_wrong():
            time.sleep(0.2)
            decir("Incorrecto.", bloquear=False)
            decir("Di empieza para intentar de nuevo.", bloquear=False)
        threading.Thread(target=_narrar_wrong, daemon=True).start()

    elif r == "TIMEOUT":
        def _narrar_timeout():
            time.sleep(0.2)
            decir("Tiempo agotado.", bloquear=False)
            decir("Di empieza para intentar de nuevo.", bloquear=False)
        threading.Thread(target=_narrar_timeout, daemon=True).start()


def _on_log(msg: str):
    log(msg, "info")
    ws.enviar_log(msg)


def _on_cliente_conectado():
    """Bienvenida y reglas cuando el panel web se conecta."""
    time.sleep(0.8)  # esperar que la conexion se establezca en el browser
    log("[Panel] Cliente conectado — narrando bienvenida", "sistema")
    # bloquear=False: encola todas las frases y el hilo TTS las procesa en orden.
    # Evita que dos hilos llamen a queue.join() al mismo tiempo y se bloqueen.
    decir("Panel conectado.", bloquear=False)
    decir("Bienvenido a Simon Dice por Voz.", bloquear=False)
    decir("El sistema mostrara una secuencia de colores.", bloquear=False)
    decir("Cuando sea tu turno, di el color en voz alta.", bloquear=False)
    decir("Di empieza para comenzar.", bloquear=False)


def _on_audio_recibido(audio_bytes: bytes):
    """
    Audio PCM Float32 16kHz enviado desde el browser en modo PTT.
    Python transcribe con Whisper local, procesa el comando y notifica al panel.
    """
    juego.pausar_timeout()  # pausar timer mientras Whisper infiere (~1s)
    texto, comando = ws.transcribir(audio_bytes)
    juego.reanudar_timeout()

    # Informar al panel del texto transcripto y el comando resultante
    ws.enviar_voz(texto, comando)

    if texto:
        log(f'[Voz] "{texto}" → {comando}', "voz")
    else:
        log("[Voz] No se detectó habla.", "info")

    if comando != "DESCONOCIDO":
        juego.procesar_comando(comando)


def _on_comando_panel(cmd: str):
    """
    Fallback: comando de texto enviado por el browser cuando usa Whisper WASM
    (solo ocurre si Whisper local no está disponible en el servidor).
    """
    log(f"[Panel/WASM] Comando: {cmd}", "voz")
    ws.enviar_log(f"Comando recibido (WASM): {cmd}")
    juego.procesar_comando(cmd)


def _registrar_callbacks():
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

    ws.on_audio             = _on_audio_recibido
    ws.on_comando           = _on_comando_panel
    ws.on_cliente_conectado = _on_cliente_conectado


# ---- Hilo de tick (timeout del turno) ----

def hilo_tick():
    while True:
        juego.tick()
        time.sleep(0.2)


# ---- Main ----

def main():
    print("\n" + "=" * 55)
    print("  SIMON DICE POR VOZ — Simulador PC (modo TEST)")
    print("=" * 55)
    print("  1. Abre Chrome o Edge en:")
    print("     http://localhost:3000")
    print("")
    print("  2. Selecciona 'Simulador — WebSocket'")
    print("  3. Haz clic en 'Conectar'")
    print("  4. Presiona ESPACIO y di EMPIEZA")
    print("=" * 55 + "\n")

    inicializar_tts()

    # Cargar Whisper local antes de iniciar el servidor WebSocket.
    # Con modelo cacheado (~74MB) tarda 2-3 segundos.
    # Si falla, el browser usará Whisper WASM automáticamente.
    ws.cargar_whisper()

    ws.iniciar()
    ws.enviar_ready()

    _registrar_callbacks()
    juego.iniciar()

    t_tick = threading.Thread(target=hilo_tick, daemon=True, name="tick")
    t_tick.start()

    # Mensaje de voz inicial cuando el TTS esté listo
    def _bienvenida_inicio():
        if esperar_tts(timeout=5.0):
            decir("Simulador listo. Abre el panel web y conecta al simulador.", bloquear=True)
    threading.Thread(target=_bienvenida_inicio, daemon=True, name="bienvenida").start()

    log("Simulador listo. Esperando conexion del panel web...", "sistema")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        nueva_linea()
        print("\n  Simulador detenido.\n")


if __name__ == "__main__":
    main()
