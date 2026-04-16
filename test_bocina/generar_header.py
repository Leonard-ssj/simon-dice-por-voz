#!/usr/bin/env python3
"""
generar_header.py
==================
Genera speaker_test/narradora.h con:
  - enum VozID  (un ID por archivo PCM)
  - array VOZ_ARCHIVOS[]  (ruta LittleFS de cada ID)
  - helpers: vozNivel(n), vozCorrectos(n), vozFin(puntos)

Uso:
    python generar_header.py
"""

import os

AUDIO_DIR = os.path.join("vocabulario", "audio")
DESTINO   = os.path.join("speaker_test", "narradora.h")

# ─── MISMA TABLA QUE generar_audio.py ─────────────────────────
NOMBRES = [
    "srv_listo",
    "simon_listo",
    "mira_escucha",
    "color_rojo",
    "color_verde",
    "color_azul",
    "color_amarillo",
    "turno_primero",
    "turno",
    "correcto_turno",
    "correcto",
    "incorrecto",
    "di_empieza",
    "tiempo_agotado",
    "pausado",
    "di_volver",
]

# correctos_02 .. correctos_14
for n in range(2, 15):
    NOMBRES.append(f"correctos_{n:02d}")

# nivel_02 .. nivel_15
for n in range(2, 16):
    NOMBRES.append(f"nivel_{n:02d}")

# fin_XXXX — los 16 valores de puntuacion posibles
PUNTOS_POSIBLES = [0, 10, 30, 60, 100, 150, 210, 280,
                   360, 450, 550, 660, 780, 910, 1050, 1200]
for pts in PUNTOS_POSIBLES:
    NOMBRES.append(f"fin_{pts:04d}")

# ──────────────────────────────────────────────────────────────


def nombre_a_enum(nombre: str) -> str:
    """srv_listo -> VOZ_SRV_LISTO"""
    return "VOZ_" + nombre.upper()


def generar():
    # Verificar que existen los PCM
    faltantes = [n for n in NOMBRES
                 if not os.path.exists(os.path.join(AUDIO_DIR, f"{n}.pcm"))]
    if faltantes:
        print(f"[AVISO] Faltan {len(faltantes)} archivos PCM:")
        for f in faltantes:
            print(f"  {f}.pcm")
        print("  Ejecuta primero: python generar_audio.py\n")

    total = len(NOMBRES)
    lineas = []

    lineas.append("/**")
    lineas.append(" * narradora.h — AUTO-GENERADO por generar_header.py")
    lineas.append(" * NO EDITAR MANUALMENTE.")
    lineas.append(" *")
    lineas.append(f" * {total} frases  |  22050 Hz  16-bit mono  LittleFS")
    lineas.append(" *")
    lineas.append(" * Frases fijas   : 16")
    lineas.append(" * correctos_02..14 : 13  (N colores correctos. Tu turno.)")
    lineas.append(" * nivel_02..15   : 14  (Nivel N.)")
    lineas.append(" * fin_XXXX       : 16  (Fin del juego. Obtuviste N puntos.)")
    lineas.append(" */")
    lineas.append("")
    lineas.append("#pragma once")
    lineas.append("")

    # ── enum VozID ──────────────────────────────────────────
    lineas.append("// Identificadores de frase")
    lineas.append("typedef enum {")
    for idx, nombre in enumerate(NOMBRES):
        lineas.append(f"    {nombre_a_enum(nombre)} = {idx},")
    lineas.append("    VOZ_COUNT")
    lineas.append("} VozID;")
    lineas.append("")

    # ── tabla de rutas LittleFS ─────────────────────────────
    lineas.append("// Ruta de cada frase en LittleFS")
    lineas.append(f"static const char* const VOZ_ARCHIVOS[VOZ_COUNT] = {{")
    for nombre in NOMBRES:
        lineas.append(f'    "/{nombre}.pcm",')
    lineas.append("};")
    lineas.append("")

    # ── helpers ─────────────────────────────────────────────
    idx_nivel_02     = NOMBRES.index("nivel_02")
    idx_correctos_02 = NOMBRES.index("correctos_02")
    idx_fin_base     = NOMBRES.index("fin_0000")

    lineas.append("// --- Helpers para IDs variables ---")
    lineas.append("")

    lineas.append("// vozNivel(n)  ->  VOZ_NIVEL_XX  para n = 2..15")
    lineas.append("inline VozID vozNivel(int n) {")
    lineas.append("    if (n < 2)  n = 2;")
    lineas.append("    if (n > 15) n = 15;")
    lineas.append(f"    return (VozID)({idx_nivel_02} + (n - 2));")
    lineas.append("}")
    lineas.append("")

    lineas.append("// vozCorrectos(n)  ->  VOZ_CORRECTOS_XX  para n = 2..14")
    lineas.append("inline VozID vozCorrectos(int n) {")
    lineas.append("    if (n < 2)  n = 2;")
    lineas.append("    if (n > 14) n = 14;")
    lineas.append(f"    return (VozID)({idx_correctos_02} + (n - 2));")
    lineas.append("}")
    lineas.append("")

    # vozFin usa lookup table con los 16 valores exactos
    scores_str = ", ".join(str(p) for p in PUNTOS_POSIBLES)
    lineas.append("// vozFin(puntos)  ->  VOZ_FIN_XXXX")
    lineas.append("// Acepta cualquier valor; devuelve el audio del puntaje mas cercano.")
    lineas.append("inline VozID vozFin(int puntos) {")
    lineas.append(f"    static const int SCORES[16] = {{{scores_str}}};")
    lineas.append("    int best = 0;")
    lineas.append("    int bestDist = abs(puntos - SCORES[0]);")
    lineas.append("    for (int i = 1; i < 16; i++) {")
    lineas.append("        int d = abs(puntos - SCORES[i]);")
    lineas.append("        if (d < bestDist) { bestDist = d; best = i; }")
    lineas.append("    }")
    lineas.append(f"    return (VozID)({idx_fin_base} + best);")
    lineas.append("}")
    lineas.append("")

    contenido = "\n".join(lineas)
    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write(contenido)

    print(f"[OK] Generado: {os.path.abspath(DESTINO)}")
    print(f"     {total} entradas en VozID")
    print(f"     vozNivel(2..15)  vozCorrectos(2..14)  vozFin(0..1200)")


if __name__ == "__main__":
    generar()
