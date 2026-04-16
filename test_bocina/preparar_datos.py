#!/usr/bin/env python3
"""
preparar_datos.py
==================
Copia todos los archivos PCM de vocabulario/audio/
a speaker_test/data/ para que el plugin de Arduino IDE
(LittleFS Upload) los suba al ESP32.

Uso:
    python preparar_datos.py
"""

import os
import shutil

ORIGEN  = os.path.join("vocabulario", "audio")
DESTINO = os.path.join("speaker_test", "data")


def main():
    print("=" * 55)
    print("  Preparando carpeta data/ para LittleFS Upload")
    print("=" * 55)

    if not os.path.isdir(ORIGEN):
        print(f"\n[FALLO] No existe: {ORIGEN}")
        print("  Ejecuta primero: python generar_audio.py\n")
        return

    os.makedirs(DESTINO, exist_ok=True)

    archivos = sorted(f for f in os.listdir(ORIGEN) if f.endswith(".pcm"))
    if not archivos:
        print(f"\n[FALLO] Sin archivos .pcm en {ORIGEN}")
        print("  Ejecuta primero: python generar_audio.py\n")
        return

    total_kb = 0
    for nombre in archivos:
        src = os.path.join(ORIGEN, nombre)
        dst = os.path.join(DESTINO, nombre)
        shutil.copy2(src, dst)
        kb = os.path.getsize(dst) // 1024
        total_kb += kb
        print(f"  {nombre:<35}  {kb:4d} KB")

    print()
    print(f"  Copiados : {len(archivos)} archivos")
    print(f"  Total    : {total_kb} KB  ({total_kb / 1024:.1f} MB)")
    print(f"  Destino  : {os.path.abspath(DESTINO)}")
    print()
    print("  Siguiente paso en Arduino IDE:")
    print("  1. Herramientas -> Partition Scheme:")
    print("     Selecciona 'Custom' (usa partitions.csv del sketch)")
    print("  2. Herramientas -> ESP32 LittleFS Data Upload")
    print("     (requiere plugin: arduino-littlefs-upload)")
    print()
    print("  Plugin (si no lo tienes):")
    print("  https://github.com/earlephilhower/arduino-littlefs-upload")
    print("=" * 55)


if __name__ == "__main__":
    main()
