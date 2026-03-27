#pragma once

#include "vocabulario.h"

// ============================================================
// game_engine.h — Máquina de estados del juego Simon Dice
// ============================================================

// Configuración del juego
// Opción C: 15000ms para dar tiempo al browser (VAD + Whisper ~1-3s de inferencia)
#define TIMEOUT_RESPUESTA  15000  // ms máximos para responder
#define DURACION_LED       800    // ms que enciende cada LED
#define PAUSA_ENTRE_LEDS   300    // ms entre LEDs de la secuencia
#define NIVEL_INICIAL      1      // longitud inicial de la secuencia
#define MAX_NIVEL          20     // nivel máximo alcanzable

// Estados de la máquina de estados
enum EstadoJuego {
    ESTADO_IDLE,
    ESTADO_SHOWING_SEQUENCE,
    ESTADO_LISTENING,
    ESTADO_EVALUATING,
    ESTADO_CORRECT,
    ESTADO_LEVEL_UP,
    ESTADO_WRONG,
    ESTADO_GAME_OVER,
    ESTADO_PAUSA
};

class GameEngine {
public:
    GameEngine();
    void iniciar();
    void reiniciar();
    void update();                         // llamar en cada loop()
    void procesarComando(Comando cmd);     // comando recibido por voz

    EstadoJuego getEstado() const;
    int getNivel() const;
    int getPuntuacion() const;
    int getPosicionActual() const;
    int getLongitudSecuencia() const;
    Comando getColorEnPosicion(int pos) const;
    Comando getColorEsperado() const;
    bool juegoActivo() const;

    // Congelan/reanudan el countdown durante transcripción PTT.
    // Llamados desde botones.cpp (botón físico) o simon_dice.ino (Serial).
    void pausarTimeout();
    void reanudarTimeout();

private:
    EstadoJuego _estado;
    Comando _secuencia[MAX_NIVEL];
    int _longitudSecuencia;
    int _posicionMostrar;     // índice al mostrar la secuencia
    int _posicionEscuchar;    // índice al escuchar al jugador
    int _nivel;
    int _puntuacion;
    unsigned long _tiempoInicio;
    bool _pausado;

    void _generarSecuencia();
    void _agregarColor();
    void _cambiarEstado(EstadoJuego nuevo);
    void _actualizarShowing();
    void _actualizarListening();
    bool _timeoutVencido() const;

    // estado de la animación de secuencia (antes eran static locales)
    unsigned long _showingUltimoTiempo;
    int           _showingFase;

    // pausa de timeout durante transcripción PTT
    bool          _enPausaTimeout;
    unsigned long _tiempoPausadoMs;
    unsigned long _tiempoPausadoInicio;
};
