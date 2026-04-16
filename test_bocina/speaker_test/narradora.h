/**
 * narradora.h — AUTO-GENERADO por generar_header.py
 * NO EDITAR MANUALMENTE.
 *
 * 75 frases  |  22050 Hz  16-bit mono  LittleFS
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
    VOZ_CORRECTOS_15 = 29,
    VOZ_CORRECTOS_16 = 30,
    VOZ_CORRECTOS_17 = 31,
    VOZ_CORRECTOS_18 = 32,
    VOZ_CORRECTOS_19 = 33,
    VOZ_CORRECTOS_20 = 34,
    VOZ_NIVEL_02 = 35,
    VOZ_NIVEL_03 = 36,
    VOZ_NIVEL_04 = 37,
    VOZ_NIVEL_05 = 38,
    VOZ_NIVEL_06 = 39,
    VOZ_NIVEL_07 = 40,
    VOZ_NIVEL_08 = 41,
    VOZ_NIVEL_09 = 42,
    VOZ_NIVEL_10 = 43,
    VOZ_NIVEL_11 = 44,
    VOZ_NIVEL_12 = 45,
    VOZ_NIVEL_13 = 46,
    VOZ_NIVEL_14 = 47,
    VOZ_NIVEL_15 = 48,
    VOZ_NIVEL_16 = 49,
    VOZ_NIVEL_17 = 50,
    VOZ_NIVEL_18 = 51,
    VOZ_NIVEL_19 = 52,
    VOZ_NIVEL_20 = 53,
    VOZ_FIN_00 = 54,
    VOZ_FIN_01 = 55,
    VOZ_FIN_02 = 56,
    VOZ_FIN_03 = 57,
    VOZ_FIN_04 = 58,
    VOZ_FIN_05 = 59,
    VOZ_FIN_06 = 60,
    VOZ_FIN_07 = 61,
    VOZ_FIN_08 = 62,
    VOZ_FIN_09 = 63,
    VOZ_FIN_10 = 64,
    VOZ_FIN_11 = 65,
    VOZ_FIN_12 = 66,
    VOZ_FIN_13 = 67,
    VOZ_FIN_14 = 68,
    VOZ_FIN_15 = 69,
    VOZ_FIN_16 = 70,
    VOZ_FIN_17 = 71,
    VOZ_FIN_18 = 72,
    VOZ_FIN_19 = 73,
    VOZ_FIN_20 = 74,
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
    "/correctos_15.pcm",
    "/correctos_16.pcm",
    "/correctos_17.pcm",
    "/correctos_18.pcm",
    "/correctos_19.pcm",
    "/correctos_20.pcm",
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
    "/nivel_16.pcm",
    "/nivel_17.pcm",
    "/nivel_18.pcm",
    "/nivel_19.pcm",
    "/nivel_20.pcm",
    "/fin_00.pcm",
    "/fin_01.pcm",
    "/fin_02.pcm",
    "/fin_03.pcm",
    "/fin_04.pcm",
    "/fin_05.pcm",
    "/fin_06.pcm",
    "/fin_07.pcm",
    "/fin_08.pcm",
    "/fin_09.pcm",
    "/fin_10.pcm",
    "/fin_11.pcm",
    "/fin_12.pcm",
    "/fin_13.pcm",
    "/fin_14.pcm",
    "/fin_15.pcm",
    "/fin_16.pcm",
    "/fin_17.pcm",
    "/fin_18.pcm",
    "/fin_19.pcm",
    "/fin_20.pcm",
};

// --- Helpers para IDs variables ---

// vozNivel(n)  ->  VOZ_NIVEL_XX  para n = 2..20
inline VozID vozNivel(int n) {
    if (n < 2)  n = 2;
    if (n > 20) n = 20;
    return (VozID)(35 + (n - 2));
}

// vozCorrectos(n)  ->  VOZ_CORRECTOS_XX  para n = 2..20
inline VozID vozCorrectos(int n) {
    if (n < 2)  n = 2;
    if (n > 20) n = 20;
    return (VozID)(16 + (n - 2));
}

// vozFin(puntos)  ->  VOZ_FIN_XX  para puntos = 0..20
inline VozID vozFin(int puntos) {
    if (puntos < 0)  puntos = 0;
    if (puntos > 20) puntos = 20;
    return (VozID)(54 + puntos);
}
