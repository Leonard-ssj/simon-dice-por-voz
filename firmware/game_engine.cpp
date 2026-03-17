#include "game_engine.h"
#include "led_control.h"
#include "sound_control.h"
#include "serial_comm.h"

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
      _pausado(false) {}

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
                        _cambiarEstado(ESTADO_CORRECT);
                        sonidoCorrecto();
                        delay(500);
                        _nivel++;
                        if (_nivel > MAX_NIVEL) _nivel = MAX_NIVEL;
                        _longitudSecuencia = _nivel;
                        _agregarColor();
                        _posicionMostrar  = 0;
                        _posicionEscuchar = 0;
                        _cambiarEstado(ESTADO_SHOWING_SEQUENCE);
                    } else {
                        // Parcialmente correcto, sigue escuchando
                        serialEnviarEsperado(_secuencia[_posicionEscuchar]);
                        _tiempoInicio = millis();
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
        _posicionMostrar = 0;
        serialEnviarSecuencia(_secuencia, _longitudSecuencia);
    }
    if (nuevo == ESTADO_LISTENING) {
        _tiempoInicio = millis();
        serialEnviarEsperado(_secuencia[_posicionEscuchar]);
        serialEnviarNivel(_nivel);
        serialEnviarPuntuacion(_puntuacion);
    }
    if (nuevo == ESTADO_GAME_OVER) {
        ledsApagar();
        serialEnviarGameOver();
        serialEnviarPuntuacion(_puntuacion);
    }
}

void GameEngine::_actualizarShowing() {
    static unsigned long ultimoTiempo = 0;
    static int fase = 0; // 0 = LED encendido, 1 = pausa

    unsigned long ahora = millis();

    if (fase == 0) {
        if (_posicionMostrar == 0 && ultimoTiempo == 0) {
            // Primer LED
            ledEncender(_secuencia[_posicionMostrar]);
            sonidoColor(_secuencia[_posicionMostrar]);
            ultimoTiempo = ahora;
        } else if (ahora - ultimoTiempo >= DURACION_LED) {
            ledApagar(_secuencia[_posicionMostrar]);
            ultimoTiempo = ahora;
            fase = 1;
        }
    } else {
        if (ahora - ultimoTiempo >= PAUSA_ENTRE_LEDS) {
            _posicionMostrar++;
            if (_posicionMostrar >= _longitudSecuencia) {
                // Terminó de mostrar la secuencia
                ultimoTiempo = 0;
                fase = 0;
                _posicionEscuchar = 0;
                _cambiarEstado(ESTADO_LISTENING);
            } else {
                ledEncender(_secuencia[_posicionMostrar]);
                sonidoColor(_secuencia[_posicionMostrar]);
                ultimoTiempo = ahora;
                fase = 0;
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
    return (millis() - _tiempoInicio) >= TIMEOUT_RESPUESTA;
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
