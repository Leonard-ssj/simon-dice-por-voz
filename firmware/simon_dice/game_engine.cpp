#include "game_engine.h"
#include "led_control.h"
#include "sound_control.h"
#include "serial_comm.h"
#include <Arduino.h>   // delay, millis, random, randomSeed

// ============================================================
// game_engine.cpp — Implementación de la lógica del juego
// ============================================================

GameEngine::GameEngine()
    : _estado(ESTADO_IDLE),
      _longitudSecuencia(0),
      _posicionMostrar(0),
      _posicionEscuchar(0),
      _nivel(NIVEL_INICIAL),
      _puntuacion(0),
      _tiempoInicio(0),
      _pausado(false),
      _showingUltimoTiempo(0),
      _showingFase(0),
      _enPausaTimeout(false),
      _tiempoPausadoMs(0),
      _tiempoPausadoInicio(0) {}

void GameEngine::iniciar() {
    reiniciar();
    _cambiarEstado(ESTADO_IDLE);
}

void GameEngine::reiniciar() {
    _longitudSecuencia = NIVEL_INICIAL;
    _posicionMostrar   = 0;
    _posicionEscuchar  = 0;
    _nivel             = NIVEL_INICIAL;
    _puntuacion        = 0;
    _pausado           = false;
    _generarSecuencia();
}

void GameEngine::update() {
    switch (_estado) {
        case ESTADO_SHOWING_SEQUENCE:
            _actualizarShowing();
            break;
        case ESTADO_LISTENING:
            _actualizarListening();
            break;
        default:
            break;
    }
}

void GameEngine::procesarComando(Comando cmd) {
    // Comandos globales disponibles en cualquier estado
    if (cmd == CMD_STOP) {
        _cambiarEstado(ESTADO_GAME_OVER);
        return;
    }

    if (cmd == CMD_REINICIAR) {
        reiniciar();
        _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
        return;
    }

    switch (_estado) {
        case ESTADO_IDLE:
            if (cmd == CMD_START) {
                reiniciar();
                _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
            }
            break;

        case ESTADO_LISTENING:
            if (cmd == CMD_REPITE) {
                // Vuelve a mostrar la secuencia (sin penalización en Fase 1)
                _posicionMostrar = 0;
                _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
            } else if (cmd == CMD_PAUSA) {
                _cambiarEstado(ESTADO_PAUSA);
            } else if (esColor(cmd)) {
                _cambiarEstado(ESTADO_EVALUATING);
                // Evaluar respuesta
                if (cmd == _secuencia[_posicionEscuchar]) {
                    _posicionEscuchar++;
                    if (_posicionEscuchar >= _longitudSecuencia) {
                        // Completó la secuencia completa
                        _puntuacion += _nivel * 10;
                        serialEnviarResultado("CORRECT");
                        _cambiarEstado(ESTADO_CORRECT);
                        sonidoCorrecto();
                        delay(500);
                        _nivel++;
                        if (_nivel > MAX_NIVEL) _nivel = MAX_NIVEL;
                        _longitudSecuencia = _nivel;
                        _agregarColor();
                        _posicionMostrar  = 0;
                        _posicionEscuchar = 0;
                        serialEnviarNivel(_nivel);
                        _cambiarEstado(ESTADO_LEVEL_UP);
                        sonidoNuevoNivel(_nivel);
                        delay(300);
                        _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
                    } else {
                        // Parcialmente correcto, sigue escuchando
                        serialEnviarResultado("CORRECT");
                        serialEnviarEsperado(_secuencia[_posicionEscuchar]);
                        _tiempoInicio    = millis();
                        _tiempoPausadoMs = 0;
                        _cambiarEstado(ESTADO_LISTENING);
                    }
                } else {
                    // Respuesta incorrecta
                    sonidoError();
                    _cambiarEstado(ESTADO_WRONG);
                    delay(1000);
                    _cambiarEstado(ESTADO_GAME_OVER);
                }
            }
            break;

        case ESTADO_PAUSA:
            if (cmd == CMD_PAUSA || cmd == CMD_START) {
                _cambiarEstado(ESTADO_LISTENING);
            }
            break;

        case ESTADO_GAME_OVER:
            if (cmd == CMD_START || cmd == CMD_REINICIAR) {
                reiniciar();
                _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
            }
            break;

        default:
            break;
    }
}

// ---- Privados ----

void GameEngine::_generarSecuencia() {
    randomSeed(millis());
    for (int i = 0; i < MAX_NIVEL; i++) {
        _secuencia[i] = COLORES_VALIDOS[random(NUM_COLORES)];
    }
}

void GameEngine::_agregarColor() {
    // La secuencia ya tiene longitud _nivel, solo se añade si es necesario
    if (_longitudSecuencia <= _nivel) {
        _secuencia[_longitudSecuencia - 1] = COLORES_VALIDOS[random(NUM_COLORES)];
    }
}

void GameEngine::_cambiarEstado(EstadoJuego nuevo) {
    _estado = nuevo;
    serialEnviarEstado(nuevo);

    if (nuevo == ESTADO_SHOWING_SEQUENCE) {
        _posicionMostrar     = 0;
        _showingUltimoTiempo = 0;
        _showingFase         = 0;
        serialEnviarSecuencia(_secuencia, _longitudSecuencia);
    }
    if (nuevo == ESTADO_LISTENING) {
        _tiempoInicio    = millis();
        _tiempoPausadoMs = 0;
        _enPausaTimeout  = false;
        serialEnviarEsperado(_secuencia[_posicionEscuchar]);
        serialEnviarNivel(_nivel);
        serialEnviarPuntuacion(_puntuacion);
    }
    if (nuevo == ESTADO_GAME_OVER) {
        sonidoGameOver();
        ledEfectoGameOver();
        serialEnviarGameOver();
        serialEnviarPuntuacion(_puntuacion);
    }
}

void GameEngine::_actualizarShowing() {
    unsigned long ahora = millis();

    if (_showingFase == 0) {
        if (_posicionMostrar == 0 && _showingUltimoTiempo == 0) {
            // Primer LED
            ledEncender(_secuencia[_posicionMostrar]);
            sonidoColor(_secuencia[_posicionMostrar]);
            _showingUltimoTiempo = ahora;
        } else if (ahora - _showingUltimoTiempo >= DURACION_LED) {
            ledApagar(_secuencia[_posicionMostrar]);
            _showingUltimoTiempo = ahora;
            _showingFase = 1;
        }
    } else {
        if (ahora - _showingUltimoTiempo >= PAUSA_ENTRE_LEDS) {
            _posicionMostrar++;
            if (_posicionMostrar >= _longitudSecuencia) {
                // Terminó de mostrar la secuencia
                _showingUltimoTiempo = 0;
                _showingFase = 0;
                _posicionEscuchar = 0;
                _cambiarEstado(ESTADO_LISTENING);
            } else {
                ledEncender(_secuencia[_posicionMostrar]);
                sonidoColor(_secuencia[_posicionMostrar]);
                _showingUltimoTiempo = ahora;
                _showingFase = 0;
            }
        }
    }
}

void GameEngine::_actualizarListening() {
    if (_timeoutVencido()) {
        sonidoError();
        serialEnviarResultado("TIMEOUT");
        _cambiarEstado(ESTADO_GAME_OVER);
    }
}

bool GameEngine::_timeoutVencido() const {
    if (_enPausaTimeout) return false;
    return (millis() - _tiempoInicio - _tiempoPausadoMs) >= TIMEOUT_RESPUESTA;
}

void GameEngine::pausarTimeout() {
    if (_estado == ESTADO_LISTENING && !_enPausaTimeout) {
        _enPausaTimeout      = true;
        _tiempoPausadoInicio = millis();
    }
}

void GameEngine::reanudarTimeout() {
    if (_enPausaTimeout) {
        _enPausaTimeout   = false;
        _tiempoPausadoMs += millis() - _tiempoPausadoInicio;
    }
}

// ---- Getters ----

EstadoJuego GameEngine::getEstado() const        { return _estado; }
int GameEngine::getNivel() const                  { return _nivel; }
int GameEngine::getPuntuacion() const             { return _puntuacion; }
int GameEngine::getPosicionActual() const         { return _posicionEscuchar; }
int GameEngine::getLongitudSecuencia() const      { return _longitudSecuencia; }
Comando GameEngine::getColorEsperado() const      { return _secuencia[_posicionEscuchar]; }
bool GameEngine::juegoActivo() const              { return _estado != ESTADO_IDLE && _estado != ESTADO_GAME_OVER; }

Comando GameEngine::getColorEnPosicion(int pos) const {
    if (pos >= 0 && pos < _longitudSecuencia) return _secuencia[pos];
    return CMD_DESCONOCIDO;
}
