/**
 * narradora.h — AUTO-GENERADO por generar_header.py
 * NO EDITAR MANUALMENTE.
 *
 * 59 frases  |  22050 Hz  16-bit mono  LittleFS
 *
 * Frases fijas   : 16
 * correctos_02..14 : 13  (N colores correctos. Tu turno.)
 * nivel_02..15   : 14  (Nivel N.)
 * fin_XXXX       : 16  (Fin del juego. Obtuviste N puntos.)
 */

#pragma once

// Identificadores de frase
typedef enum {
    VOZ_SRV_LISTO = 0,
    VOZ_SIMON_LISTO = 1,
    VOZ_MIRA_ESCUCHA = 2,
    VOZ_COLOR_ROJO = 3,
    VOZ_COLOR_VERDE = 4,
    VOZ_COLOR_AZUL = 5,
    VOZ_COLOR_AMARILLO = 6,
    VOZ_TURNO_PRIMERO = 7,
    VOZ_TURNO = 8,
    VOZ_CORRECTO_TURNO = 9,
    VOZ_CORRECTO = 10,
    VOZ_INCORRECTO = 11,
    VOZ_DI_EMPIEZA = 12,
    VOZ_TIEMPO_AGOTADO = 13,
    VOZ_PAUSADO = 14,
    VOZ_DI_VOLVER = 15,
    VOZ_CORRECTOS_02 = 16,
    VOZ_CORRECTOS_03 = 17,
    VOZ_CORRECTOS_04 = 18,
    VOZ_CORRECTOS_05 = 19,
    VOZ_CORRECTOS_06 = 20,
    VOZ_CORRECTOS_07 = 21,
    VOZ_CORRECTOS_08 = 22,
    VOZ_CORRECTOS_09 = 23,
    VOZ_CORRECTOS_10 = 24,
    VOZ_CORRECTOS_11 = 25,
    VOZ_CORRECTOS_12 = 26,
    VOZ_CORRECTOS_13 = 27,
    VOZ_CORRECTOS_14 = 28,
    VOZ_NIVEL_02 = 29,
    VOZ_NIVEL_03 = 30,
    VOZ_NIVEL_04 = 31,
    VOZ_NIVEL_05 = 32,
    VOZ_NIVEL_06 = 33,
    VOZ_NIVEL_07 = 34,
    VOZ_NIVEL_08 = 35,
    VOZ_NIVEL_09 = 36,
    VOZ_NIVEL_10 = 37,
    VOZ_NIVEL_11 = 38,
    VOZ_NIVEL_12 = 39,
    VOZ_NIVEL_13 = 40,
    VOZ_NIVEL_14 = 41,
    VOZ_NIVEL_15 = 42,
    VOZ_FIN_0000 = 43,
    VOZ_FIN_0010 = 44,
    VOZ_FIN_0030 = 45,
    VOZ_FIN_0060 = 46,
    VOZ_FIN_0100 = 47,
    VOZ_FIN_0150 = 48,
    VOZ_FIN_0210 = 49,
    VOZ_FIN_0280 = 50,
    VOZ_FIN_0360 = 51,
    VOZ_FIN_0450 = 52,
    VOZ_FIN_0550 = 53,
    VOZ_FIN_0660 = 54,
    VOZ_FIN_0780 = 55,
    VOZ_FIN_0910 = 56,
    VOZ_FIN_1050 = 57,
    VOZ_FIN_1200 = 58,
    VOZ_COUNT
} VozID;

// Ruta de cada frase en LittleFS
static const char* const VOZ_ARCHIVOS[VOZ_COUNT] = {
    "/srv_listo.pcm",
    "/simon_listo.pcm",
    "/mira_escucha.pcm",
    "/color_rojo.pcm",
    "/color_verde.pcm",
    "/color_azul.pcm",
    "/color_amarillo.pcm",
    "/turno_primero.pcm",
    "/turno.pcm",
    "/correcto_turno.pcm",
    "/correcto.pcm",
    "/incorrecto.pcm",
    "/di_empieza.pcm",
    "/tiempo_agotado.pcm",
    "/pausado.pcm",
    "/di_volver.pcm",
    "/correctos_02.pcm",
    "/correctos_03.pcm",
    "/correctos_04.pcm",
    "/correctos_05.pcm",
    "/correctos_06.pcm",
    "/correctos_07.pcm",
    "/correctos_08.pcm",
    "/correctos_09.pcm",
    "/correctos_10.pcm",
    "/correctos_11.pcm",
    "/correctos_12.pcm",
    "/correctos_13.pcm",
    "/correctos_14.pcm",
    "/nivel_02.pcm",
    "/nivel_03.pcm",
    "/nivel_04.pcm",
    "/nivel_05.pcm",
    "/nivel_06.pcm",
    "/nivel_07.pcm",
    "/nivel_08.pcm",
    "/nivel_09.pcm",
    "/nivel_10.pcm",
    "/nivel_11.pcm",
    "/nivel_12.pcm",
    "/nivel_13.pcm",
    "/nivel_14.pcm",
    "/nivel_15.pcm",
    "/fin_0000.pcm",
    "/fin_0010.pcm",
    "/fin_0030.pcm",
    "/fin_0060.pcm",
    "/fin_0100.pcm",
    "/fin_0150.pcm",
    "/fin_0210.pcm",
    "/fin_0280.pcm",
    "/fin_0360.pcm",
    "/fin_0450.pcm",
    "/fin_0550.pcm",
    "/fin_0660.pcm",
    "/fin_0780.pcm",
    "/fin_0910.pcm",
    "/fin_1050.pcm",
    "/fin_1200.pcm",
};

// --- Helpers para IDs variables ---

// vozNivel(n)  ->  VOZ_NIVEL_XX  para n = 2..15
inline VozID vozNivel(int n) {
    if (n < 2)  n = 2;
    if (n > 15) n = 15;
    return (VozID)(29 + (n - 2));
}

// vozCorrectos(n)  ->  VOZ_CORRECTOS_XX  para n = 2..14
inline VozID vozCorrectos(int n) {
    if (n < 2)  n = 2;
    if (n > 14) n = 14;
    return (VozID)(16 + (n - 2));
}

// vozFin(puntos)  ->  VOZ_FIN_XXXX
// Acepta cualquier valor; devuelve el audio del puntaje mas cercano.
inline VozID vozFin(int puntos) {
    static const int SCORES[16] = {0, 10, 30, 60, 100, 150, 210, 280, 360, 450, 550, 660, 780, 910, 1050, 1200};
    int best = 0;
    int bestDist = abs(puntos - SCORES[0]);
    for (int i = 1; i < 16; i++) {
        int d = abs(puntos - SCORES[i]);
        if (d < bestDist) { bestDist = d; best = i; }
    }
    return (VozID)(43 + best);
}
