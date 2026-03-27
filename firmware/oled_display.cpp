#include "oled_display.h"
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>

// ============================================================
// oled_display.cpp — Implementación OLED SSD1306 0.91"
// ============================================================

static Adafruit_SSD1306 _display(OLED_ANCHO, OLED_ALTO, &Wire, -1);
static bool _listo = false;

// ---- Texto abreviado para cada estado ----
static const char* _textoEstado(const char* estado) {
    if (strcmp(estado, "IDLE") == 0)        return "ESPERANDO";
    if (strcmp(estado, "SHOWING") == 0)     return "SECUENCIA";
    if (strcmp(estado, "LISTENING") == 0)   return "TU TURNO";
    if (strcmp(estado, "EVALUATING") == 0)  return "PROCESANDO";
    if (strcmp(estado, "CORRECT") == 0)     return "CORRECTO!";
    if (strcmp(estado, "LEVEL_UP") == 0)    return "NIVEL UP!";
    if (strcmp(estado, "WRONG") == 0)       return "INCORRECTO";
    if (strcmp(estado, "GAMEOVER") == 0)    return "FIN JUEGO";
    if (strcmp(estado, "PAUSA") == 0)       return "PAUSADO";
    return estado;
}

bool oledInicializar() {
    Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);

    if (!_display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
        // Hardware no encontrado — el sistema continúa sin OLED
        _listo = false;
        return false;
    }

    _listo = true;
    _display.clearDisplay();
    _display.setTextColor(SSD1306_WHITE);
    _display.display();
    return true;
}

void oledMostrarBienvenida() {
    if (!_listo) return;
    _display.clearDisplay();
    _display.setTextSize(1);
    _display.setCursor(0, 0);
    _display.println("SIMON DICE POR VOZ");
    _display.println("-------------------");
    _display.println("Conecta panel web");
    _display.println("o di:  EMPIEZA");
    _display.display();
}

void oledMostrarEstado(const char* estado, int nivel, int puntuacion, const char* colorEsperado) {
    if (!_listo) return;
    _display.clearDisplay();

    // Fila 0 (y=0): estado del juego
    _display.setTextSize(1);
    _display.setCursor(0, 0);
    _display.print(_textoEstado(estado));

    // Fila 1 (y=10): nivel y puntuación
    _display.setCursor(0, 10);
    _display.print("Niv:");
    _display.print(nivel);
    _display.print("  Pts:");
    _display.print(puntuacion);

    // Fila 2 (y=20): color esperado o hint
    _display.setCursor(0, 20);
    if (colorEsperado && strlen(colorEsperado) > 0) {
        _display.print("Di: ");
        _display.print(colorEsperado);
    } else if (strcmp(estado, "LISTENING") == 0) {
        _display.print("[PTT = BOTON/ESPACIO]");
    }

    _display.display();
}

void oledMostrarColor(const char* color) {
    if (!_listo) return;
    _display.clearDisplay();

    // Nombre del color grande (2x) centrado verticalmente
    _display.setTextSize(2);
    int ancho = strlen(color) * 12;  // ~12px por carácter en size 2
    int x     = max(0, (OLED_ANCHO - ancho) / 2);
    _display.setCursor(x, 8);
    _display.println(color);

    _display.display();
}

void oledMostrarGameOver(int puntuacion) {
    if (!_listo) return;
    _display.clearDisplay();
    _display.setTextSize(1);

    _display.setCursor(0, 0);
    _display.println("=== FIN DEL JUEGO ===");
    _display.setCursor(0, 12);
    _display.print("Puntos: ");
    _display.println(puntuacion);
    _display.setCursor(0, 22);
    _display.print("Di EMPIEZA p/volver");

    _display.display();
}

void oledLimpiar() {
    if (!_listo) return;
    _display.clearDisplay();
    _display.display();
}
