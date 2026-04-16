#!/usr/bin/env python3
"""
subir_audio.py
===============
Crea la imagen LittleFS con los 75 archivos PCM
y la sube directamente al ESP32-S3 via esptool.

No necesita ningun plugin de Arduino IDE.

Uso:
    python subir_audio.py

Requisitos:
    pip install littlefs-python esptool pyserial
"""

import os
import sys
import subprocess
import shutil
import littlefs
import serial.tools.list_ports


def encontrar_python_esptool():
    """Devuelve el ejecutable de Python que tiene esptool instalado."""
    candidatos = [sys.executable]
    # Agregar otros Python conocidos en Windows
    for nombre in ["python", "python3", "py", "python3.12", "python3.11", "python3.10"]:
        exe = shutil.which(nombre)
        if exe and exe not in candidatos:
            candidatos.append(exe)
    # Buscar en rutas comunes de Windows
    import glob
    for patron in [r"C:\Python3*\python.exe", r"C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe"]:
        for exe in sorted(glob.glob(patron), reverse=True):
            if exe not in candidatos:
                candidatos.append(exe)
    for exe in candidatos:
        try:
            r = subprocess.run([exe, "-c", "import esptool"], capture_output=True)
            if r.returncode == 0:
                return exe
        except Exception:
            pass
    return None

# ─── PARAMETROS DE LA PARTICION (deben coincidir con partitions.csv) ──
LFS_OFFSET     = 0x310000       # offset de la particion littlefs
LFS_SIZE       = 0xCE0000       # 13.5 MB
LFS_BLOCK_SIZE = 4096
LFS_BLOCK_COUNT = LFS_SIZE // LFS_BLOCK_SIZE   # 3296 bloques

DATA_DIR  = os.path.join("speaker_test", "data")
IMG_PATH  = "littlefs.bin"
# ───────────────────────────────────────────────────────────────────────


def listar_puertos():
    puertos = list(serial.tools.list_ports.comports())
    if not puertos:
        print("\n  [FALLO] No se encontro ningun puerto COM.")
        print("  Verifica que el ESP32 este conectado por USB.\n")
        sys.exit(1)
    return puertos


def elegir_puerto(puertos):
    # Auto-seleccionar si solo hay uno que parezca ESP32
    usb_puertos = [p for p in puertos if "USB" in p.description.upper()
                   or "CP210" in p.description.upper()
                   or "CH340" in p.description.upper()
                   or "JTAG" in p.description.upper()]
    if len(usb_puertos) == 1:
        p = usb_puertos[0]
        print(f"  Puerto ESP32 detectado: {p.device} — {p.description}")
        return p.device

    if len(puertos) == 1:
        print(f"  Puerto detectado: {puertos[0].device} — {puertos[0].description}")
        return puertos[0].device

    print("\n  Puertos disponibles:")
    for i, p in enumerate(puertos):
        print(f"    [{i}]  {p.device}  —  {p.description}")
    print()
    while True:
        try:
            entrada = input("  Escribe el NUMERO del indice [0,1,2...] o el nombre (COM8): ").strip()
            # Aceptar nombre de puerto directo (COM8, /dev/ttyUSB0, etc.)
            for p in puertos:
                if entrada.upper() == p.device.upper():
                    return p.device
            # Aceptar indice numerico
            idx = int(entrada)
            if 0 <= idx < len(puertos):
                return puertos[idx].device
        except (ValueError, KeyboardInterrupt):
            pass
        print("  Escribe el indice (ej: 1) o el nombre (ej: COM8)")


def crear_imagen():
    archivos = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".pcm"))
    if not archivos:
        print(f"[FALLO] No hay archivos .pcm en {DATA_DIR}")
        print("  Ejecuta primero: python preparar_datos.py\n")
        sys.exit(1)

    print(f"  Creando imagen LittleFS ({LFS_SIZE // 1024 // 1024} MB)...")
    print(f"  Archivos a incluir: {len(archivos)}")

    fs = littlefs.LittleFS(block_size=LFS_BLOCK_SIZE, block_count=LFS_BLOCK_COUNT)

    total_bytes = 0
    for nombre in archivos:
        ruta = os.path.join(DATA_DIR, nombre)
        with open(ruta, "rb") as f:
            datos = f.read()
        with fs.open(f"/{nombre}", "wb") as dst:
            dst.write(datos)
        total_bytes += len(datos)
        print(f"    + {nombre}  ({len(datos) // 1024} KB)")

    imagen = fs.context.buffer
    with open(IMG_PATH, "wb") as f:
        f.write(imagen)

    print(f"\n  Imagen creada: {IMG_PATH}")
    print(f"  Tamano imagen : {len(imagen) // 1024 // 1024} MB")
    print(f"  Audio incluido: {total_bytes // 1024} KB  ({len(archivos)} archivos)")
    return IMG_PATH


def subir_imagen(puerto):
    print(f"\n  Subiendo al ESP32 en {puerto}...")
    print(f"  Offset: 0x{LFS_OFFSET:X}  |  Tamano: {LFS_SIZE // 1024 // 1024} MB")
    print(f"  (esto puede tardar ~30-60 segundos)\n")

    python_exe = encontrar_python_esptool()
    if not python_exe:
        print("[FALLO] No se encontro esptool en ninguna instalacion de Python.")
        print("  Ejecuta:  pip install esptool")
        return False
    print(f"  Usando: {python_exe}\n")

    cmd = [
        python_exe, "-m", "esptool",
        "--chip",  "esp32s3",
        "--port",  puerto,
        "--baud",  "921600",
        "write_flash",
        f"0x{LFS_OFFSET:X}",
        IMG_PATH,
    ]

    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    print("=" * 60)
    print("  Subidor de audio LittleFS — ESP32-S3-N16R8")
    print("=" * 60)

    # 1 — Verificar carpeta de datos
    if not os.path.isdir(DATA_DIR):
        print(f"\n[FALLO] No existe: {DATA_DIR}")
        print("  Ejecuta primero: python preparar_datos.py\n")
        sys.exit(1)

    # 2 — Crear imagen LittleFS
    print()
    crear_imagen()

    # 3 — Elegir puerto COM
    print("\n  Buscando puertos COM...")
    puertos = listar_puertos()
    puerto = elegir_puerto(puertos)

    # 4 — Subir
    print()
    ok = subir_imagen(puerto)

    # 5 — Resultado
    print()
    print("=" * 60)
    if ok:
        print("  [OK] Audio subido correctamente al ESP32.")
        print()
        print("  Siguiente paso:")
        print("  1. Compila y sube el sketch en Arduino IDE (Ctrl+U)")
        print("  2. Abre Serial Monitor a 115200 baudios")
        print("  3. Presiona D para reproducir el vocabulario")
    else:
        print("  [FALLO] Revisa:")
        print("  - Que el ESP32 este conectado y en modo flash")
        print("  - Que el Serial Monitor este cerrado")
        print("  - Que el puerto COM sea el correcto")
    print("=" * 60)


if __name__ == "__main__":
    main()
