#!/usr/bin/env python3
"""
tts_server.py — Servidor TTS offline para ESP32-S3
====================================================
Usa Piper TTS con voz es_MX-claude-high (español mexicano).
El ESP32 hace un POST con el texto y recibe audio PCM 16-bit mono
listo para escribir directo al I2S / MAX98357A.

Uso:
    python tts_server.py

Requisitos:
    pip install -r requirements.txt
    python descargar_modelo.py   (solo la primera vez)
"""

import os
import sys
import subprocess
from flask import Flask, request, Response

# ─── CONFIGURACION ────────────────────────────────────────
MODEL_PATH  = os.path.join("models", "es_MX-claude-high.onnx")
SAMPLE_RATE = 22050   # Hz — el modelo claude-high usa 22050
HOST        = "0.0.0.0"
PORT        = 8080
# ──────────────────────────────────────────────────────────

app = Flask(__name__)


def texto_a_pcm(texto: str) -> bytes:
    """
    Llama a piper en modo --output-raw y retorna bytes PCM.
    PCM: 16-bit con signo, mono, SAMPLE_RATE Hz, little-endian.
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "piper",
            "--model",        MODEL_PATH,
            "--output-raw",
            "--noise-scale",  "0.667",   # variacion de voz
            "--length-scale", "1.0",     # velocidad (1.0 = normal)
            "--noise-w",      "0.8",
        ],
        input=texto.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace")
        raise RuntimeError(f"Piper fallo (codigo {proc.returncode}): {err}")
    return proc.stdout


# ─── RUTAS ────────────────────────────────────────────────

@app.route("/tts", methods=["POST"])
def tts():
    """
    POST /tts
    Body: texto plano UTF-8 (maximo 500 chars recomendado)
    Respuesta: audio/pcm raw 16-bit mono 22050 Hz
    Headers de respuesta utiles para el ESP32:
        X-Sample-Rate, X-Channels, X-Bits
    """
    texto = request.data.decode("utf-8").strip()
    if not texto:
        return "Sin texto en el body", 400
    if len(texto) > 1000:
        return "Texto demasiado largo (max 1000 chars)", 413

    preview = texto[:60] + ("..." if len(texto) > 60 else "")
    print(f"[TTS] '{preview}'  ({len(texto)} chars)")

    try:
        pcm = texto_a_pcm(texto)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return str(e), 500

    duracion_s = len(pcm) / 2 / SAMPLE_RATE
    print(f"[TTS] {len(pcm)} bytes  |  {duracion_s:.1f} s  |  {SAMPLE_RATE} Hz")

    return Response(
        pcm,
        mimetype="application/octet-stream",
        headers={
            "X-Sample-Rate":  str(SAMPLE_RATE),
            "X-Channels":     "1",
            "X-Bits":         "16",
            "Content-Length": str(len(pcm)),
        },
    )


@app.route("/ping", methods=["GET"])
def ping():
    """El ESP32 puede llamar esto para verificar que el servidor esta vivo."""
    return f"OK modelo={os.path.basename(MODEL_PATH)} rate={SAMPLE_RATE}", 200


# ─── MAIN ─────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Servidor TTS — Piper es_MX (español mexicano)")
    print("=" * 55)

    # Verificar modelo
    if not os.path.exists(MODEL_PATH):
        print(f"\n[FALLO] No se encontro el modelo:")
        print(f"        {os.path.abspath(MODEL_PATH)}")
        print(f"\n  Ejecuta primero:  python descargar_modelo.py\n")
        sys.exit(1)

    json_path = MODEL_PATH + ".json"
    if not os.path.exists(json_path):
        print(f"\n[FALLO] Falta el archivo de configuracion:")
        print(f"        {os.path.abspath(json_path)}")
        print(f"\n  Ejecuta primero:  python descargar_modelo.py\n")
        sys.exit(1)

    print(f"  Modelo : {os.path.abspath(MODEL_PATH)}")
    print(f"  Rate   : {SAMPLE_RATE} Hz  |  16-bit mono")
    print(f"  URL    : http://<TU_IP>:{PORT}/tts")
    print(f"\n  Para saber tu IP en la red local ejecuta:")
    print(f"    Windows: ipconfig")
    print(f"    Linux  : ip addr")
    print()

    app.run(host=HOST, port=PORT, threaded=False)
