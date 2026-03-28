#pragma once

#include <cstring>   // strcmp

// ============================================================
// vocabulario.h — Fuente única del vocabulario del juego
// Agregar o quitar palabras SOLO en este archivo.
// ============================================================

// Enum con todos los comandos reconocibles
enum Comando {
    CMD_ROJO,
    CMD_VERDE,
    CMD_AZUL,
    CMD_AMARILLO,
    CMD_START,
    CMD_STOP,
    CMD_PAUSA,
    CMD_REPITE,
    CMD_REINICIAR,
    CMD_ARRIBA,
    CMD_ABAJO,
    CMD_IZQUIERDA,
    CMD_DERECHA,
    CMD_SI,
    CMD_NO,
    CMD_DESCONOCIDO,
    CMD_COUNT  // cantidad total de comandos (siempre al final)
};

// Colores válidos como secuencia del juego
const Comando COLORES_VALIDOS[] = {
    CMD_ROJO,
    CMD_VERDE,
    CMD_AZUL,
    CMD_AMARILLO
};
const int NUM_COLORES = 4;

// Nombres de cada comando (índice = valor del enum)
const char* const NOMBRES_COMANDO[CMD_COUNT] = {
    "ROJO",
    "VERDE",
    "AZUL",
    "AMARILLO",
    "START",
    "STOP",
    "PAUSA",
    "REPITE",
    "REINICIAR",
    "ARRIBA",
    "ABAJO",
    "IZQUIERDA",
    "DERECHA",
    "SI",
    "NO",
    "DESCONOCIDO"
};

// Convierte un string a Comando (retorna CMD_DESCONOCIDO si no coincide)
inline Comando stringAComando(const char* texto) {
    for (int i = 0; i < CMD_COUNT - 1; i++) {
        if (strcmp(texto, NOMBRES_COMANDO[i]) == 0) {
            return (Comando)i;
        }
    }
    return CMD_DESCONOCIDO;
}

// Convierte un Comando a su nombre en string
inline const char* comandoAString(Comando cmd) {
    if (cmd >= 0 && cmd < CMD_COUNT) {
        return NOMBRES_COMANDO[cmd];
    }
    return "DESCONOCIDO";
}

// Verifica si un comando es un color válido del juego
inline bool esColor(Comando cmd) {
    for (int i = 0; i < NUM_COLORES; i++) {
        if (COLORES_VALIDOS[i] == cmd) return true;
    }
    return false;
}
