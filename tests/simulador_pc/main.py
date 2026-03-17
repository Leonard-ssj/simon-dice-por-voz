#!/usr/bin/env python3
# ============================================================
# main.py — Simulador PC (reemplaza el kit ESP32 en pruebas)
#
# Corre el juego completo Simon Dice en tu PC:
#   - Speaker del sistema (sounddevice + pyttsx3) en vez del MAX98357A
#   - LEDs simulados en la terminal con colores ANSI
#   - WebSocket activo → el Web Panel se conecta en modo Simulador
#
# Reconocimiento de voz:
#   El browser (Chrome/Edge) graba el micrófono y usa Whisper WASM.
#   Los comandos reconocidos llegan al simulador via WebSocket como JSON:
#   {"tipo": "comando", "comando": "ROJO"}
#
#   El simulador NO usa el micrófono directamente.
#   Abre el panel en http://localhost:3000 para jugar.
#
# Uso:
#   cd tests/simulador_pc
#   python main.py
#   → luego abre http://localhost:3000 en Chrome/Edge
# ============================================================

import sys
import os
import threading
import time

# Asegurar imports locales
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


# ---- Helpers de log con colores ----
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
    nueva_linea()  # no sobreescribir el panel de LEDs
    color = COLORES_ANSI.get(tipo, "")
    print(f"{color}  {msg}{COLORES_ANSI['reset']}")


# ---- Conectar callbacks del juego ----

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
    # Narrador — comentar transiciones importantes
    if estado == Estado.LISTENING:
        decir("Tu turno.", bloquear=False)
    elif estado == Estado.GAME_OVER:
        decir("Fin del juego.", bloquear=False)


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
        # Tono primero (bloqueante ~400ms), luego TTS — evita conflicto de audio en Windows
        reproducir_sonido(tipo, extra)
        decir_color(extra)
    else:
        threading.Thread(target=reproducir_sonido, args=(tipo, extra), daemon=True).start()


def _on_secuencia(seq: list):
    log(f"[Secuencia] {' → '.join(seq)}", "sistema")
    ws.enviar_secuencia(seq)
    decir("Mira la secuencia.", bloquear=False)


def _on_esperado(color: str):
    log(f"[Escuchando] Esperando: {color}", "voz")
    ws.enviar_esperado(color)


def _on_nivel(n: int):
    log(f"[Nivel] {n}", "sistema")
    ws.enviar_nivel(n)
    decir(f"¡Correcto! Nivel {n}.", bloquear=False)


def _on_puntuacion(p: int):
    ws.enviar_puntuacion(p)


def _on_resultado(r: str):
    tipo    = "ok" if r == "CORRECT" else "error"
    etiqueta = {
        "CORRECT": "✓ Correcto",
        "WRONG":   "✗ Incorrecto",
        "TIMEOUT": "⏱ Tiempo agotado",
    }.get(r, r)
    log(f"[Resultado] {etiqueta}", tipo)
    ws.enviar_resultado(r)
    if r == "WRONG":
        decir("Incorrecto.", bloquear=False)
    elif r == "TIMEOUT":
        decir("Tiempo agotado.", bloquear=False)


def _on_log(msg: str):
    log(msg, "info")
    ws.enviar_log(msg)


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

    # Comandos reconocidos por Whisper WASM en el browser → llegan via WebSocket
    ws.on_comando = _on_comando_panel


def _on_comando_panel(cmd: str):
    """Comando recibido desde el Web Panel (Whisper WASM en el browser)."""
    log(f"[Panel] Comando: {cmd}", "voz")
    juego.procesar_comando(cmd)


# ---- Hilo de tick (timeout del turno) ----

def hilo_tick():
    """Verifica el timeout del turno cada 200ms."""
    while True:
        juego.tick()
        time.sleep(0.2)


# ---- Main ----

def main():
    print("\n" + "=" * 55)
    print("  SIMON DICE POR VOZ — Simulador PC (modo TEST)")
    print("=" * 55)
    print("  Abre el panel en Chrome/Edge para jugar:")
    print("  → http://localhost:3000")
    print("")
    print("  El browser usa Whisper WASM para reconocer tu voz.")
    print("  Di EMPIEZA para comenzar cuando el panel esté conectado.")
    print("=" * 55 + "\n")

    # Inicializar TTS (narrador del juego)
    inicializar_tts()

    # Iniciar WebSocket — el panel se conecta aquí
    ws.iniciar()
    ws.enviar_ready()

    # Registrar callbacks y arrancar el motor del juego
    _registrar_callbacks()
    juego.iniciar()

    # Hilo de tick (timeout del turno)
    t_tick = threading.Thread(target=hilo_tick, daemon=True, name="tick")
    t_tick.start()

    # Bienvenida del narrador
    def _bienvenida():
        if esperar_tts(timeout=5.0):
            decir("Simulador listo. Abre el panel web para jugar.", bloquear=True)
    threading.Thread(target=_bienvenida, daemon=True, name="bienvenida").start()

    log("Simulador listo. Esperando conexión del panel web...", "sistema")
    log("Abre http://localhost:3000 en Chrome o Edge.", "sistema")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        nueva_linea()
        print("\n  Simulador detenido.\n")


if __name__ == "__main__":
    main()
