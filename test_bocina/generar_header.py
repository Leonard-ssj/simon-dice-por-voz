#!/usr/bin/env python3
"""
generar_header.py
==================
Genera speaker_test/narradora.h con:
  - enum VozID  (un ID por archivo PCM)
  - array VOZ_ARCHIVOS[]  (ruta SPIFFS de cada ID)
  - helpers: vozNivel(n), vozFin(puntos), vozCorrectos(n)

Uso:
    python generar_header.py
"""

import os

AUDIO_DIR = os.path.join("vocabulario", "audio")
DESTINO   = os.path.join("speaker_test", "narradora.h")

# Misma tabla que generar_audio.py (nombre_archivo, texto)
# Solo necesitamos los nombres de archivo en el mismo orden.
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

# correctos_02 .. correctos_20
for n in range(2, 21):
    NOMBRES.append(f"correctos_{n:02d}")

# nivel_02 .. nivel_20
for n in range(2, 21):
    NOMBRES.append(f"nivel_{n:02d}")

# fin_00 .. fin_20
for n in range(0, 21):
    NOMBRES.append(f"fin_{n:02d}")


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
    lineas.append(" */")
    lineas.append("")
    lineas.append("#pragma once")
    lineas.append("")

    # ── enum VozID ──────────────────────────────────────────
    lineas.append("// Identificadores de frase")
    lineas.append("typedef enum {")
    for idx, nombre in enumerate(NOMBRES):
        coma = "," if idx < total - 1 else ","
        lineas.append(f"    {nombre_a_enum(nombre)} = {idx}{coma}")
    lineas.append("    VOZ_COUNT")
    lineas.append("} VozID;")
    lineas.append("")

    # ── tabla de rutas SPIFFS ───────────────────────────────
    lineas.append("// Ruta de cada frase en LittleFS")
    lineas.append(f"static const char* const VOZ_ARCHIVOS[VOZ_COUNT] = {{")
    for nombre in NOMBRES:
        lineas.append(f'    "/{nombre}.pcm",')
    lineas.append("};")
    lineas.append("")

    # ── helpers para IDs variables ──────────────────────────
    # Indice base de nivel_02 en el enum
    idx_nivel_02 = NOMBRES.index("nivel_02")
    idx_correctos_02 = NOMBRES.index("correctos_02")
    idx_fin_00 = NOMBRES.index("fin_00")

    lineas.append("// --- Helpers para IDs variables ---")
    lineas.append("")
    lineas.append("// vozNivel(n)  ->  VOZ_NIVEL_XX  para n = 2..20")
    lineas.append("inline VozID vozNivel(int n) {")
    lineas.append(f"    if (n < 2)  n = 2;")
    lineas.append(f"    if (n > 20) n = 20;")
    lineas.append(f"    return (VozID)({idx_nivel_02} + (n - 2));")
    lineas.append("}")
    lineas.append("")
    lineas.append("// vozCorrectos(n)  ->  VOZ_CORRECTOS_XX  para n = 2..20")
    lineas.append("inline VozID vozCorrectos(int n) {")
    lineas.append(f"    if (n < 2)  n = 2;")
    lineas.append(f"    if (n > 20) n = 20;")
    lineas.append(f"    return (VozID)({idx_correctos_02} + (n - 2));")
    lineas.append("}")
    lineas.append("")
    lineas.append("// vozFin(puntos)  ->  VOZ_FIN_XX  para puntos = 0..20")
    lineas.append("inline VozID vozFin(int puntos) {")
    lineas.append(f"    if (puntos < 0)  puntos = 0;")
    lineas.append(f"    if (puntos > 20) puntos = 20;")
    lineas.append(f"    return (VozID)({idx_fin_00} + puntos);")
    lineas.append("}")
    lineas.append("")

    contenido = "\n".join(lineas)
    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write(contenido)

    print(f"[OK] Generado: {os.path.abspath(DESTINO)}")
    print(f"     {total} entradas en VozID")
    print(f"     Helpers: vozNivel(2..20)  vozCorrectos(2..20)  vozFin(0..20)")


if __name__ == "__main__":
    generar()
