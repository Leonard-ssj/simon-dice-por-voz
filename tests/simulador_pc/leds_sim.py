# ============================================================
# leds_sim.py — Simulación de LEDs en la terminal con colores ANSI
# Muestra un panel visual en consola que reemplaza los LEDs físicos.
# ============================================================

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from config_test import USAR_COLORES_ANSI

# Códigos ANSI de color de fondo
ANSI = {
    "ROJO":     "\033[41m",   # fondo rojo
    "VERDE":    "\033[42m",   # fondo verde
    "AZUL":     "\033[44m",   # fondo azul
    "AMARILLO": "\033[43m",   # fondo amarillo
    "RESET":    "\033[0m",
    "NEGRO":    "\033[40m",   # apagado
    "BOLD":     "\033[1m",
    "DIM":      "\033[2m",
}

# Estado interno de cada LED
_estado_leds: dict[str, bool] = {
    "ROJO":     False,
    "VERDE":    False,
    "AZUL":     False,
    "AMARILLO": False,
}

# Nombre visible con padding
_NOMBRES = {
    "ROJO":     " ROJO  ",
    "VERDE":    " VERDE ",
    "AZUL":     " AZUL  ",
    "AMARILLO": " AMAR. ",
}


def _dibujar_panel():
    """Imprime el estado actual de los 4 LEDs en una línea."""
    if not USAR_COLORES_ANSI:
        partes = []
        for color in ["ROJO", "VERDE", "AZUL", "AMARILLO"]:
            estado = "●" if _estado_leds[color] else "○"
            partes.append(f"{estado} {color}")
        print("  LEDs: " + "  |  ".join(partes), end="\r")
        return

    partes = []
    for color in ["ROJO", "VERDE", "AZUL", "AMARILLO"]:
        if _estado_leds[color]:
            bloque = f"{ANSI['BOLD']}{ANSI[color]} {_NOMBRES[color]} {ANSI['RESET']}"
        else:
            bloque = f"{ANSI['DIM']}{ANSI['NEGRO']} {_NOMBRES[color]} {ANSI['RESET']}"
        partes.append(bloque)

    linea = "  " + "  ".join(partes)
    # Limpiar línea anterior y escribir la nueva
    sys.stdout.write("\r\033[K" + linea)
    sys.stdout.flush()


def led_encender(color: str):
    """Enciende el LED del color indicado."""
    if color in _estado_leds:
        _estado_leds[color] = True
        _dibujar_panel()


def led_apagar(color: str):
    """Apaga el LED del color indicado."""
    if color in _estado_leds:
        _estado_leds[color] = False
        _dibujar_panel()


def leds_apagar_todos():
    """Apaga todos los LEDs."""
    for color in _estado_leds:
        _estado_leds[color] = False
    _dibujar_panel()


def leds_imprimir_estado():
    """Fuerza redibujar el panel (útil al inicio)."""
    _dibujar_panel()


def nueva_linea():
    """
    Imprime un salto de línea después del panel de LEDs.
    Llamar antes de imprimir otro texto para no sobreescribir el panel.
    """
    print()
