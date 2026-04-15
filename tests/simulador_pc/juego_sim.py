# ============================================================
# juego_sim.py — Máquina de estados del juego (espejo del firmware en Python)
# Completamente independiente del hardware.
# ============================================================

import random
import time
import threading as _threading
from enum import Enum
from config_test import (
    TIMEOUT_RESPUESTA, NIVEL_INICIAL, MAX_NIVEL,
    DURACION_LED_SIM, PAUSA_ENTRE_LEDS
)

# Vocabulario (espejo de vocabulario.h)
COLORES = ["ROJO", "VERDE", "AZUL", "AMARILLO"]

VOCABULARIO = {
    "ROJO", "VERDE", "AZUL", "AMARILLO",
    "START", "STOP", "PAUSA", "REPITE", "REINICIAR",
    "ARRIBA", "ABAJO", "IZQUIERDA", "DERECHA",
    "SI", "NO"
}


class Estado(Enum):
    IDLE             = "IDLE"
    SHOWING_SEQUENCE = "SHOWING"
    LISTENING        = "LISTENING"
    EVALUATING       = "EVALUATING"
    CORRECT          = "CORRECT"
    LEVEL_UP         = "LEVEL_UP"
    WRONG            = "WRONG"
    GAME_OVER        = "GAMEOVER"
    PAUSA            = "PAUSA"


class JuegoSimulador:
    """
    Lógica completa del Simon Dice en Python.
    Se comunica hacia afuera mediante callbacks para no acoplarse
    al WebSocket, terminal o cualquier otra salida.

    Las operaciones bloqueantes (mostrar secuencia, transiciones CORRECT/WRONG)
    corren en threads daemon propios — procesar_comando() retorna en <1ms.
    """

    def __init__(self, timeout_ms: int = None,
                 duracion_led_ms: int = None,
                 pausa_leds_ms:   int = None):
        # timeout_ms permite sobreescribir TIMEOUT_RESPUESTA sin tocar config_test.py.
        # servidor_pc pasa config.py:TIMEOUT_RESPUESTA (60s).
        # El simulador de tests usa el valor por defecto de config_test.py (30s).
        self._timeout_ms    = timeout_ms    if timeout_ms    is not None else TIMEOUT_RESPUESTA
        # Timing de la secuencia — si no se pasa, usa config_test.py.
        # servidor.py debe pasar los valores de config.py para evitar desincronía.
        self._duracion_led  = duracion_led_ms if duracion_led_ms is not None else DURACION_LED_SIM
        self._pausa_leds    = pausa_leds_ms   if pausa_leds_ms   is not None else PAUSA_ENTRE_LEDS

        self._estado        = Estado.IDLE
        self._secuencia     = []
        self._pos_escuchar  = 0
        self._nivel         = NIVEL_INICIAL
        self._puntuacion    = 0
        self._tiempo_inicio = 0.0
        self._tiempo_pausado = 0.0
        self._tiempo_pausado_inicio = 0.0  # evitar AttributeError si reanudar antes de pausar
        self._en_pausa_timeout = False
        self._pausado       = False
        self._terminando    = False        # bandera anti doble-GAMEOVER

        # Protege _estado contra acceso concurrente (hilo-seq vs hilo-tick)
        self._lock          = _threading.Lock()
        # Evita doble arranque de secuencia simultánea
        self._seq_en_curso  = False

        # Callbacks — se asignan desde main.py
        self.on_estado_cambio  = lambda estado: None   # (Estado)
        self.on_mostrar_led    = lambda color: None     # (str) enciende LED
        self.on_apagar_led     = lambda color: None     # (str) apaga LED
        self.on_apagar_todos   = lambda: None
        self.on_sonido         = lambda tipo, extra=None: None  # ("color"|"correcto"|"error"|"inicio"|"gameover", extra)
        self.on_secuencia      = lambda seq: None       # (list[str])
        self.on_esperado       = lambda color: None     # (str)
        self.on_nivel          = lambda n: None         # (int)
        self.on_puntuacion     = lambda p: None         # (int)
        self.on_resultado      = lambda r: None         # ("CORRECT"|"WRONG"|"TIMEOUT")
        self.on_log            = lambda msg: None       # (str)

    # ------------------------------------------------------------------ #
    #  Propiedades                                                         #
    # ------------------------------------------------------------------ #

    @property
    def estado(self) -> Estado:
        return self._estado

    @property
    def nivel(self) -> int:
        return self._nivel

    @property
    def puntuacion(self) -> int:
        return self._puntuacion

    @property
    def secuencia(self) -> list:
        return list(self._secuencia)

    @property
    def esperado(self) -> str | None:
        if self._pos_escuchar < len(self._secuencia):
            return self._secuencia[self._pos_escuchar]
        return None

    # ------------------------------------------------------------------ #
    #  Control del juego                                                   #
    # ------------------------------------------------------------------ #

    def iniciar(self):
        self._reiniciar()
        self._cambiar_estado(Estado.IDLE)
        self.on_log("Sistema listo. Di EMPIEZA para comenzar.")

    def _reiniciar(self):
        self._nivel        = NIVEL_INICIAL
        self._puntuacion   = 0
        self._pos_escuchar = 0
        self._secuencia    = self._generar_secuencia(MAX_NIVEL)
        self._pausado      = False
        self._terminando   = False   # permitir que tick() dispare timeout en la nueva partida

    def procesar_comando(self, cmd: str):
        """
        Procesa un comando del juego. SIEMPRE retorna en <1ms.
        Las operaciones bloqueantes (mostrar secuencia, sleeps de transición)
        se ejecutan en threads daemon — no bloquean el hilo llamante.
        """
        cmd = cmd.strip().upper()

        if cmd not in VOCABULARIO and cmd != "DESCONOCIDO":
            return

        # Comandos globales
        if cmd == "STOP":
            self._cambiar_estado(Estado.GAME_OVER)
            return
        if cmd == "REINICIAR":
            self._reiniciar()
            self._iniciar_secuencia()
            return

        estado = self._estado

        if estado == Estado.IDLE:
            if cmd == "START":
                self._reiniciar()
                self._iniciar_secuencia()

        elif estado == Estado.LISTENING:
            if cmd == "REPITE":
                self.on_log("Repitiendo secuencia...")
                # Mostrar secuencia de nuevo en su propio thread
                self._seq_en_curso = True
                _threading.Thread(
                    target=self._hilo_repite,
                    daemon=True, name="seq-repite"
                ).start()
            elif cmd == "PAUSA":
                self._cambiar_estado(Estado.PAUSA)
            elif cmd in COLORES:
                self._evaluar(cmd)

        elif estado == Estado.PAUSA:
            if cmd in ("PAUSA", "START"):
                self._empezar_escucha()

        elif estado == Estado.GAME_OVER:
            if cmd in ("START", "REINICIAR"):
                self._reiniciar()
                self._iniciar_secuencia()

    def _hilo_repite(self):
        """Muestra la secuencia de nuevo (REPITE) sin bloquear el hilo llamante."""
        try:
            self._mostrar_secuencia_bloqueante()
            self._empezar_escucha()
        finally:
            self._seq_en_curso = False

    def pausar_timeout(self):
        """Congela el contador de timeout mientras Whisper procesa."""
        if self._estado == Estado.LISTENING and not self._en_pausa_timeout:
            self._en_pausa_timeout = True
            self._tiempo_pausado_inicio = time.time()

    def reanudar_timeout(self):
        """Reanuda el contador descontando el tiempo que estuvo procesando."""
        if self._en_pausa_timeout:
            self._en_pausa_timeout = False
            self._tiempo_pausado += time.time() - self._tiempo_pausado_inicio

    def tick(self):
        """Llamar periódicamente para verificar timeout."""
        if self._estado == Estado.LISTENING and not self._en_pausa_timeout and not self._terminando:
            elapsed = (time.time() - self._tiempo_inicio - self._tiempo_pausado) * 1000
            if elapsed >= self._timeout_ms:
                self._terminando = True
                self.on_resultado("TIMEOUT")
                self.on_log("Tiempo agotado.")
                self.on_sonido("error")
                self._cambiar_estado(Estado.GAME_OVER)

    # ------------------------------------------------------------------ #
    #  Lógica interna                                                      #
    # ------------------------------------------------------------------ #

    def _generar_secuencia(self, longitud: int) -> list:
        return [random.choice(COLORES) for _ in range(longitud)]

    def _iniciar_secuencia(self):
        """
        Arranca la visualización de la secuencia en un thread daemon.
        Retorna inmediatamente — NO bloquea el hilo llamante.
        """
        if self._seq_en_curso:
            return
        self._seq_en_curso = True
        self._pos_escuchar = 0
        longitud = self._nivel
        self.on_secuencia(self._secuencia[:longitud])
        _threading.Thread(
            target=self._hilo_secuencia,
            daemon=True, name="seq"
        ).start()

    def _hilo_secuencia(self):
        """Hilo dedicado: muestra LEDs (bloqueante aquí) y pasa a LISTENING."""
        try:
            self._mostrar_secuencia_bloqueante()
            self._empezar_escucha()
        finally:
            self._seq_en_curso = False

    def _mostrar_secuencia_bloqueante(self):
        """Muestra los LEDs de la secuencia uno por uno (bloqueante — solo llamar desde un thread dedicado)."""
        self._cambiar_estado(Estado.SHOWING_SEQUENCE)
        longitud = self._nivel
        for color in self._secuencia[:longitud]:
            self.on_mostrar_led(color)
            self.on_sonido("color", color)
            time.sleep(self._duracion_led / 1000)
            self.on_apagar_led(color)
            time.sleep(self._pausa_leds / 1000)

    def _empezar_escucha(self):
        self._tiempo_inicio    = time.time()
        self._tiempo_pausado   = 0.0
        self._en_pausa_timeout = False
        self._terminando       = False   # rearmar para cada turno
        self._cambiar_estado(Estado.LISTENING)
        if self.esperado:
            self.on_esperado(self.esperado)

    def _evaluar(self, cmd: str):
        self._cambiar_estado(Estado.EVALUATING)
        esperado = self._secuencia[self._pos_escuchar]

        if cmd == esperado:
            self._pos_escuchar += 1
            if self._pos_escuchar >= self._nivel:
                # Secuencia completada — transición en thread propio (no bloquear audio-proc)
                self._puntuacion += self._nivel * 10
                self.on_puntuacion(self._puntuacion)
                self.on_resultado("CORRECT")
                self.on_sonido("correcto")
                self._cambiar_estado(Estado.CORRECT)
                _threading.Thread(
                    target=self._hilo_nivel_up,
                    daemon=True, name="nivel-up"
                ).start()
            else:
                # Parcialmente correcto — siguiente color sin transición lenta
                self.on_resultado("CORRECT")
                self.on_log(f"Bien ({self._pos_escuchar}/{self._nivel}). Sigue...")
                self._empezar_escucha()
        else:
            self.on_resultado("WRONG")
            self.on_log(f"Incorrecto. Esperaba {esperado}, dijiste {cmd}.")
            self.on_sonido("error")
            self._cambiar_estado(Estado.WRONG)
            _threading.Thread(
                target=self._hilo_gameover,
                daemon=True, name="gameover-delay"
            ).start()

    def _hilo_nivel_up(self):
        """Espera breve post-CORRECT, sube nivel y arranca nueva secuencia."""
        time.sleep(0.6)
        self._nivel = min(self._nivel + 1, MAX_NIVEL)
        self.on_nivel(self._nivel)
        self.on_log(f"¡Nivel {self._nivel}! Secuencia ahora tiene {self._nivel} pasos.")
        self._iniciar_secuencia()

    def _hilo_gameover(self):
        """Espera breve post-WRONG y transiciona a GAME_OVER."""
        time.sleep(0.8)
        self._cambiar_estado(Estado.GAME_OVER)

    def _cambiar_estado(self, nuevo: Estado):
        self._estado = nuevo
        self.on_estado_cambio(nuevo)

        if nuevo == Estado.GAME_OVER:
            self.on_apagar_todos()
            self.on_sonido("gameover")
            self.on_log(f"Fin del juego — Puntuación final: {self._puntuacion}")
            self.on_puntuacion(self._puntuacion)
