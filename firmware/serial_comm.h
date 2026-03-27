#pragma once

#include "vocabulario.h"
#include "game_engine.h"

// ============================================================
// serial_comm.h — Protocolo Serial ESP32 ↔ PC
// Formato: texto plano, una línea por mensaje, terminado en \n
// Velocidad: 115200 baud
// ============================================================

// 921600 baud necesarios para transferir audio PTT del INMP441
// (16kHz x 16bit = 32 KB/s; 921600 baud ~ 64 KB/s utiles)
#define SERIAL_BAUD 921600

// Inicializa la comunicación Serial
void serialInicializar();

// Envía una línea de texto por Serial
void serialEnviar(const char* mensaje);

// Lee una línea desde Serial (retorna true si hay datos)
// buffer debe tener al menos maxLen bytes
bool serialLeer(char* buffer, int maxLen);

// ---- Mensajes ESP32 → PC ----

void serialEnviarReady();
void serialEnviarEstado(EstadoJuego estado);
void serialEnviarDetectado(Comando cmd);
void serialEnviarResultado(const char* resultado);  // "CORRECT", "WRONG", "TIMEOUT"
void serialEnviarSecuencia(Comando* secuencia, int longitud);
void serialEnviarEsperado(Comando cmd);
void serialEnviarNivel(int nivel);
void serialEnviarPuntuacion(int puntuacion);
void serialEnviarGameOver();

// ---- Lectura PC → ESP32 ----

// Procesa líneas recibidas por Serial y retorna el comando detectado
// Retorna CMD_DESCONOCIDO si no hay nada o no se reconoce
Comando serialLeerComando();
