#!/usr/bin/env python3
"""
generar_audio.py
=================
Genera los 59 archivos PCM de la narradora usando Piper TTS
(es_MX-claude-high) y los guarda en vocabulario/audio/
y en speaker_test/data/ (listo para subir con subir_audio.py).

Formato de salida:
  16-bit con signo, mono, 22050 Hz, little-endian
  (listo para escribir directo al I2S del ESP32)

Uso:
    python generar_audio.py
"""

import os, sys, subprocess, shutil

MODEL_PATH  = os.path.join("models", "es_MX-claude-high.onnx")
DESTINO     = os.path.join("vocabulario", "audio")
DATA_DIR    = os.path.join("speaker_test", "data")
SAMPLE_RATE = 22050

# ─── TABLA DE FRASES ──────────────────────────────────────────
# (nombre_archivo_sin_extension, texto_a_pronunciar)
FRASES = [
    # ── Arranque ──────────────────────────────────────────────
    ("srv_listo",       "Servidor listo. Abre el panel web y conecta."),
    ("simon_listo",     "Simón Dice listo. Presiona espacio para comenzar."),

    # ── Inicio de partida ─────────────────────────────────────
    ("mira_escucha",    "Mira y escucha."),

    # ── Colores ───────────────────────────────────────────────
    ("color_rojo",      "rojo"),
    ("color_verde",     "verde"),
    ("color_azul",      "azul"),
    ("color_amarillo",  "amarillo"),

    # ── Turno del jugador ─────────────────────────────────────
    ("turno_primero",   "Tu turno. Presiona espacio para hablar."),
    ("turno",           "Tu turno."),
    ("correcto_turno",  "Correcto. Tu turno."),

    # ── Acierto / Error ───────────────────────────────────────
    ("correcto",        "Correcto."),
    ("incorrecto",      "Incorrecto."),
    ("di_empieza",      "Di empieza para intentar de nuevo."),

    # ── Tiempo ────────────────────────────────────────────────
    ("tiempo_agotado",  "Tiempo agotado."),

    # ── Pausa ─────────────────────────────────────────────────
    ("pausado",         "Juego pausado."),

    # ── Fin del juego ─────────────────────────────────────────
    ("di_volver",       "Di empieza para volver a jugar."),
]

# "N colores correctos. Tu turno."  N = 2..14
for n in range(2, 15):
    FRASES.append((f"correctos_{n:02d}", f"{n} colores correctos. Tu turno."))

# "Nivel N."  N = 2..15
for n in range(2, 16):
    FRASES.append((f"nivel_{n:02d}", f"Nivel {n}."))

# "Fin del juego. Obtuviste N puntos."
# Solo los 16 valores posibles del sistema de puntuacion
PUNTOS_POSIBLES = [0, 10, 30, 60, 100, 150, 210, 280,
                   360, 450, 550, 660, 780, 910, 1050, 1200]
for pts in PUNTOS_POSIBLES:
    palabra = "punto" if pts == 1 else "puntos"
    FRASES.append((f"fin_{pts:04d}", f"Fin del juego. Obtuviste {pts} {palabra}."))

# ──────────────────────────────────────────────────────────────


def encontrar_python_piper():
    """Devuelve el ejecutable de Python que tiene piper instalado."""
    candidatos = [sys.executable]
    for nombre in ["python", "python3", "py", "python3.12", "python3.11"]:
        exe = shutil.which(nombre)
        if exe and exe not in candidatos:
            candidatos.append(exe)
    import glob
    for patron in [r"C:\Python3*\python.exe",
                   r"C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe"]:
        for exe in sorted(glob.glob(patron), reverse=True):
            if exe not in candidatos:
                candidatos.append(exe)
    for exe in candidatos:
        try:
            r = subprocess.run([exe, "-c", "import piper"], capture_output=True)
            if r.returncode == 0:
                return exe
        except Exception:
            pass
    return sys.executable  # fallback


def generar_pcm(texto: str, python_exe: str) -> bytes:
    proc = subprocess.run(
        [
            python_exe, "-m", "piper",
            "--model",        MODEL_PATH,
            "--output-raw",
            "--noise-scale",  "0.667",
            "--length-scale", "1.0",
            "--noise-w",      "0.8",
        ],
        input=texto.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip())
    return proc.stdout


def main():
    print("=" * 60)
    print("  Generador de audio — Narradora Simon Dice")
    print("  Modelo: es_MX-claude-high  |  22050 Hz  16-bit mono")
    print(f"  Total frases: {len(FRASES)}")
    print("=" * 60)

    if not os.path.exists(MODEL_PATH):
        print(f"\n[FALLO] Modelo no encontrado: {MODEL_PATH}")
        print("  Ejecuta primero: python descargar_modelo.py\n")
        sys.exit(1)

    python_exe = encontrar_python_piper()
    print(f"\n  Python piper : {python_exe}")

    os.makedirs(DESTINO, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    total    = len(FRASES)
    nuevos   = 0
    saltados = 0
    errores  = []

    print(f"  Destino audio : {os.path.abspath(DESTINO)}")
    print(f"  Destino data  : {os.path.abspath(DATA_DIR)}")
    print(f"  Archivos      : {total}\n")

    for idx, (nombre, texto) in enumerate(FRASES, 1):
        ruta = os.path.join(DESTINO, f"{nombre}.pcm")
        ruta_data = os.path.join(DATA_DIR, f"{nombre}.pcm")

        if os.path.exists(ruta):
            # Copiar a data/ si no existe alli
            if not os.path.exists(ruta_data):
                shutil.copy2(ruta, ruta_data)
            ms = os.path.getsize(ruta) // 2 * 1000 // SAMPLE_RATE
            print(f"  [{idx:3}/{total}] SKIP  {nombre}.pcm  ({ms} ms)")
            saltados += 1
            continue

        preview = texto if len(texto) <= 48 else texto[:45] + "..."
        print(f"  [{idx:3}/{total}] '{preview}'", end="", flush=True)

        try:
            pcm = generar_pcm(texto, python_exe)
            with open(ruta, "wb") as f:
                f.write(pcm)
            shutil.copy2(ruta, ruta_data)
            ms = len(pcm) // 2 * 1000 // SAMPLE_RATE
            print(f"  -> {len(pcm) // 1024:3d} KB  ({ms} ms)  OK")
            nuevos += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            errores.append(nombre)

    # ── Resumen ───────────────────────────────────────────────
    print()
    print("=" * 60)
    if errores:
        print(f"  [!] Errores en {len(errores)} archivos: {errores}")
    else:
        archivos_ok = [
            os.path.join(DESTINO, f"{n}.pcm")
            for n, _ in FRASES
            if os.path.exists(os.path.join(DESTINO, f"{n}.pcm"))
        ]
        total_kb = sum(os.path.getsize(p) for p in archivos_ok) // 1024
        total_ms = sum(os.path.getsize(p) // 2 * 1000 // SAMPLE_RATE
                       for p in archivos_ok)
        print(f"  Nuevos  : {nuevos}")
        print(f"  Saltados: {saltados}")
        print(f"  Total   : {len(archivos_ok)} archivos")
        print(f"  Tamano  : {total_kb} KB  ({total_ms // 1000} s de audio)")
        print()
        print("  Siguiente paso:")
        print("    python generar_header.py   (actualiza narradora.h)")
    print("=" * 60)


if __name__ == "__main__":
    main()
