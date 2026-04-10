"""
capturar_audio.py — Captura audio del ESP32 (Test 5) y guarda como WAV.

Uso:
  1. Cerrar el Serial Monitor del Arduino IDE
  2. Correr este script: python capturar_audio.py
  3. Cuando diga "Listo. Enviando '5'...", el script envia el comando automaticamente
  4. Hablar al microfono durante 10 segundos
  5. Se guarda grabacion.wav y se abre automaticamente

Requisitos:
  pip install pyserial
"""

import serial
import serial.tools.list_ports
import wave
import struct
import sys
import os
import time

# ─── Configuracion ─────────────────────────────────────────────────────────────
BAUD_RATE    = 921600
SAMPLE_RATE  = 8000   # debe coincidir con SAMPLE_RATE del firmware
CHANNELS     = 1
SAMPWIDTH    = 2          # 16-bit = 2 bytes
OUTPUT_FILE  = "grabacion.wav"
TIMEOUT_SEG  = 15         # maximo tiempo esperando AUDIO_START


def encontrar_puerto():
    """Detecta automaticamente el puerto del ESP32."""
    puertos = serial.tools.list_ports.comports()
    candidatos = []
    for p in puertos:
        desc = (p.description or "").lower()
        if any(x in desc for x in ["cp210", "ch340", "ftdi", "uart", "usb serial", "esp"]):
            candidatos.append(p.device)
    if not candidatos:
        # Si no hay candidato obvio, listar todos y pedir al usuario
        todos = [p.device for p in puertos]
        if not todos:
            print("[ERROR] No se encontro ningun puerto serial.")
            print("        Verifica que el ESP32 este conectado por USB.")
            sys.exit(1)
        return todos[0]   # tomar el primero
    return candidatos[0]


def guardar_wav(datos_pcm: bytes, ruta: str):
    """Guarda los bytes PCM raw como archivo WAV."""
    with wave.open(ruta, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPWIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(datos_pcm)


def main():
    # ── Detectar puerto ──────────────────────────────────────────────────────
    puerto = encontrar_puerto()
    print(f"[INFO] Conectando a {puerto} @ {BAUD_RATE} baud...")

    try:
        ser = serial.Serial(puerto, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir {puerto}: {e}")
        print("        Asegurate de cerrar el Serial Monitor del Arduino IDE.")
        sys.exit(1)

    time.sleep(1.5)          # esperar reset del ESP32 al abrir puerto
    ser.reset_input_buffer()

    # ── Enviar comando '5' ───────────────────────────────────────────────────
    print("[INFO] Listo. Enviando comando '5' al ESP32...")
    ser.write(b'5')

    # ── Esperar marcador AUDIO_START:N ───────────────────────────────────────
    print("[INFO] Esperando inicio de grabacion...")
    total_bytes = None
    t_inicio = time.time()

    while True:
        if time.time() - t_inicio > TIMEOUT_SEG:
            print(f"[ERROR] Timeout ({TIMEOUT_SEG}s) esperando AUDIO_START.")
            ser.close()
            sys.exit(1)

        linea = ser.readline().decode('latin-1', errors='replace').strip()
        if not linea:
            continue

        print(f"  ESP32: {linea}")

        if linea.startswith("AUDIO_START:"):
            try:
                total_bytes = int(linea.split(":")[1])
                print(f"[INFO] Grabando {total_bytes} bytes ({total_bytes//2} muestras, {SAMPLE_RATE}Hz)...")
                print("[INFO] >>> HABLA AL MICROFONO AHORA <<<")
                break
            except ValueError:
                print(f"[WARN] Formato inesperado: {linea}")

    # ── Leer exactamente total_bytes bytes de audio ──────────────────────────
    datos = bytearray()
    leidos = 0
    t_inicio = time.time()

    # El primer byte puede venir inmediatamente despues del \n del marcador;
    # leer en chunks hasta completar total_bytes.
    while leidos < total_bytes:
        faltante = total_bytes - leidos
        chunk = ser.read(min(faltante, 4096))
        if chunk:
            datos.extend(chunk)
            leidos += len(chunk)
            porcentaje = leidos / total_bytes * 100
            print(f"\r  Recibido: {leidos}/{total_bytes} bytes ({porcentaje:.0f}%)   ", end="", flush=True)
        if time.time() - t_inicio > 30:
            print("\n[ERROR] Timeout leyendo datos de audio.")
            ser.close()
            sys.exit(1)

    print()  # nueva linea tras el progreso

    # ── Esperar marcador AUDIO_END ────────────────────────────────────────────
    print("[INFO] Esperando confirmacion AUDIO_END...")
    t_inicio = time.time()
    while True:
        if time.time() - t_inicio > 5:
            print("[WARN] No llego AUDIO_END, pero los datos estan completos.")
            break
        linea = ser.readline().decode('latin-1', errors='replace').strip()
        if linea:
            print(f"  ESP32: {linea}")
        if "AUDIO_END" in linea:
            print("[INFO] Grabacion confirmada por el ESP32.")
            break

    ser.close()

    # ── Guardar WAV ───────────────────────────────────────────────────────────
    ruta_wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    guardar_wav(bytes(datos), ruta_wav)
    duracion = len(datos) / (SAMPLE_RATE * SAMPWIDTH * CHANNELS)
    print(f"[OK] Guardado: {ruta_wav}")
    print(f"     Duracion: {duracion:.2f} segundos  |  Tamano: {len(datos)} bytes")

    # ── Abrir el archivo automaticamente ─────────────────────────────────────
    print("[INFO] Abriendo el archivo de audio...")
    try:
        if sys.platform == "win32":
            os.startfile(ruta_wav)
        elif sys.platform == "darwin":
            os.system(f'open "{ruta_wav}"')
        else:
            os.system(f'xdg-open "{ruta_wav}"')
    except Exception as e:
        print(f"[WARN] No se pudo abrir automaticamente: {e}")
        print(f"       Abre manualmente: {ruta_wav}")


if __name__ == "__main__":
    main()
