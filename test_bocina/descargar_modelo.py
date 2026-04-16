#!/usr/bin/env python3
"""
descargar_modelo.py
====================
Descarga el modelo de voz es_MX-claude-high de Piper TTS
(español mexicano) desde Hugging Face y lo guarda en ./models/

Solo necesitas ejecutarlo UNA vez.
    python descargar_modelo.py
"""

import os
import sys
import urllib.request

# ─── URL del modelo en Hugging Face ───────────────────────
BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/es/es_MX/claude/high"
)
ARCHIVOS = {
    "es_MX-claude-high.onnx":      f"{BASE}/es_MX-claude-high.onnx",
    "es_MX-claude-high.onnx.json": f"{BASE}/es_MX-claude-high.onnx.json",
}
DESTINO = "models"
# ──────────────────────────────────────────────────────────


def barra(bloque, tam_bloque, total):
    """Callback de progreso para urllib.request.urlretrieve"""
    if total > 0:
        pct = min(bloque * tam_bloque / total * 100, 100)
        mb_descargado = bloque * tam_bloque / 1_048_576
        mb_total = total / 1_048_576
        print(
            f"\r  {pct:5.1f}%  {mb_descargado:.1f} / {mb_total:.1f} MB",
            end="",
            flush=True,
        )


def descargar():
    os.makedirs(DESTINO, exist_ok=True)

    print("=" * 55)
    print("  Descarga modelo Piper TTS — es_MX-claude-high")
    print("  (español mexicano, 22050 Hz, ~65 MB)")
    print("=" * 55)

    todos_ok = True
    for nombre, url in ARCHIVOS.items():
        ruta = os.path.join(DESTINO, nombre)

        if os.path.exists(ruta):
            tam = os.path.getsize(ruta)
            print(f"\n  [OK] Ya existe: {nombre} ({tam/1_048_576:.1f} MB)")
            continue

        print(f"\n  Descargando: {nombre}")
        print(f"  Desde: {url}")
        try:
            urllib.request.urlretrieve(url, ruta, reporthook=barra)
            print()  # nueva linea tras la barra de progreso
            tam = os.path.getsize(ruta)
            print(f"  [OK] Guardado en {ruta} ({tam/1_048_576:.1f} MB)")
        except Exception as e:
            print(f"\n  [FALLO] {e}")
            # Borrar archivo incompleto
            if os.path.exists(ruta):
                os.remove(ruta)
            todos_ok = False

    print()
    if todos_ok:
        print("  Listo. Ahora ejecuta:  python tts_server.py")
    else:
        print("  Hubo errores. Revisa tu conexion a internet e intenta de nuevo.")
        sys.exit(1)


if __name__ == "__main__":
    descargar()
