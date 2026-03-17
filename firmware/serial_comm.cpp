#include "serial_comm.h"
#include <Arduino.h>

// ============================================================
// serial_comm.cpp — Implementación del protocolo Serial
// ============================================================

// Mapeo de EstadoJuego a string para el protocolo
static const char* _estadoAString(EstadoJuego estado) {
    switch (estado) {
        case ESTADO_IDLE:             return "IDLE";
        case ESTADO_SHOWING_SEQUENCE: return "SHOWING";
        case ESTADO_LISTENING:        return "LISTENING";
        case ESTADO_EVALUATING:       return "EVALUATING";
        case ESTADO_CORRECT:          return "CORRECT";
        case ESTADO_LEVEL_UP:         return "LEVEL_UP";
        case ESTADO_WRONG:            return "WRONG";
        case ESTADO_GAME_OVER:        return "GAMEOVER";
        case ESTADO_PAUSA:            return "PAUSA";
        default:                      return "UNKNOWN";
    }
}

void serialInicializar() {
    Serial.begin(SERIAL_BAUD);
    while (!Serial) delay(10); // Esperar a que el puerto esté listo
}

void serialEnviar(const char* mensaje) {
    Serial.println(mensaje);
}

bool serialLeer(char* buffer, int maxLen) {
    if (!Serial.available()) return false;
    int n = Serial.readBytesUntil('\n', buffer, maxLen - 1);
    if (n <= 0) return false;
    // Quitar \r si hay
    if (n > 0 && buffer[n - 1] == '\r') n--;
    buffer[n] = '\0';
    return n > 0;
}

void serialEnviarReady() {
    serialEnviar("READY");
}

void serialEnviarEstado(EstadoJuego estado) {
    char buf[32];
    snprintf(buf, sizeof(buf), "STATE:%s", _estadoAString(estado));
    serialEnviar(buf);
}

void serialEnviarDetectado(Comando cmd) {
    char buf[32];
    snprintf(buf, sizeof(buf), "DETECTED:%s", comandoAString(cmd));
    serialEnviar(buf);
}

void serialEnviarResultado(const char* resultado) {
    char buf[32];
    snprintf(buf, sizeof(buf), "RESULT:%s", resultado);
    serialEnviar(buf);
}

void serialEnviarSecuencia(Comando* secuencia, int longitud) {
    // Formato: SEQUENCE:ROJO,VERDE,AZUL,...
    char buf[256] = "SEQUENCE:";
    for (int i = 0; i < longitud; i++) {
        strncat(buf, comandoAString(secuencia[i]), sizeof(buf) - strlen(buf) - 1);
        if (i < longitud - 1) {
            strncat(buf, ",", sizeof(buf) - strlen(buf) - 1);
        }
    }
    serialEnviar(buf);
}

void serialEnviarEsperado(Comando cmd) {
    char buf[32];
    snprintf(buf, sizeof(buf), "EXPECTED:%s", comandoAString(cmd));
    serialEnviar(buf);
}

void serialEnviarNivel(int nivel) {
    char buf[16];
    snprintf(buf, sizeof(buf), "LEVEL:%d", nivel);
    serialEnviar(buf);
}

void serialEnviarPuntuacion(int puntuacion) {
    char buf[16];
    snprintf(buf, sizeof(buf), "SCORE:%d", puntuacion);
    serialEnviar(buf);
}

void serialEnviarGameOver() {
    serialEnviar("GAMEOVER");
}

Comando serialLeerComando() {
    static char buffer[64];
    if (!serialLeer(buffer, sizeof(buffer))) return CMD_DESCONOCIDO;
    if (strlen(buffer) == 0) return CMD_DESCONOCIDO;

    Comando cmd = stringAComando(buffer);
    if (cmd != CMD_DESCONOCIDO) {
        serialEnviarDetectado(cmd);
    }
    return cmd;
}
