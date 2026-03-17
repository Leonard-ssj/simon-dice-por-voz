#!/usr/bin/env python3
# ============================================================
# run.py — Switch entre modo TEST (sin hardware) y HARDWARE (con ESP32)
#
# Uso:
#   python run.py test       → Simulador PC (sin hardware, micrófono del sistema)
#   python run.py hardware   → Servidor real (ESP32 + Whisper + WebSocket)
#   python run.py            → Pregunta qué modo usar
# ============================================================

import sys
import os
import subprocess


MODOS = {
    "test":     ("tests/simulador_pc/main.py",    "Simulador PC (sin hardware)"),
    "hardware": ("servidor_pc/servidor.py",        "Servidor real (requiere ESP32 conectado)"),
}


def mostrar_menu():
    print("\n" + "=" * 50)
    print("  SIMON DICE POR VOZ — Selector de modo")
    print("=" * 50)
    print()
    print("  [1] test     — Simulador PC (sin hardware)")
    print("              Usa tu micrófono y speaker del sistema")
    print("              LEDs simulados en terminal")
    print("              Ideal para desarrollar sin el kit")
    print()
    print("  [2] hardware — Servidor real con ESP32")
    print("              Requiere el kit OKYN-G5806 conectado")
    print("              Ajustar puerto COM en servidor_pc/config.py")
    print()
    eleccion = input("  Elegir modo (1/2): ").strip()
    if eleccion == "1":
        return "test"
    elif eleccion == "2":
        return "hardware"
    else:
        print("  Opción no válida.")
        return None


def main():
    # Leer modo desde argumento de línea de comandos
    modo = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in MODOS:
            modo = arg
        else:
            print(f"  Modo desconocido: '{arg}'")
            print(f"  Modos válidos: {', '.join(MODOS.keys())}")
            sys.exit(1)

    # Si no se pasó argumento, mostrar menú interactivo
    if modo is None:
        modo = mostrar_menu()
        if modo is None:
            sys.exit(1)

    script, descripcion = MODOS[modo]
    ruta_script = os.path.join(os.path.dirname(__file__), script)

    if not os.path.exists(ruta_script):
        print(f"\n  Error: no se encontró '{script}'")
        sys.exit(1)

    print(f"\n  Iniciando: {descripcion}")
    print(f"  Script:    {script}")
    print()

    # Ejecutar el script en el directorio correcto
    directorio = os.path.dirname(ruta_script)
    subprocess.run([sys.executable, ruta_script], cwd=directorio)


if __name__ == "__main__":
    main()
