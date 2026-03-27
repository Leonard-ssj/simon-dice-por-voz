#pragma once

// ============================================================
// oled_display.h — Display OLED 0.91" SSD1306 (I2C)
//
// Muestra en tiempo real el estado del juego, nivel, puntuación
// y el color esperado. El display funciona aunque el panel web
// no esté conectado.
//
// Librería necesaria: Adafruit SSD1306 + Adafruit GFX
//   (Sketch → Include Library → Manage Libraries)
//
// ⚠️ Pines I2C — verificar con el esquemático del kit MRD085A
// ============================================================

// Pines I2C del display ⚠️ VERIFICAR con el kit físico
#define OLED_SDA_PIN    21    // ⚠️ VERIFICAR
#define OLED_SCL_PIN    22    // ⚠️ VERIFICAR

// Dimensiones del display 0.91"
#define OLED_ANCHO      128
#define OLED_ALTO       32

// Dirección I2C estándar del SSD1306 (puede ser 0x3D en algunos módulos)
#define OLED_I2C_ADDR   0x3C

// ---- API pública ----

// Inicializa el display. Retorna false si no se detectó hardware.
// El sistema funciona normalmente aunque retorne false.
bool oledInicializar();

// Actualiza el display con el estado actual del juego.
// Llamar cada vez que cambie el estado, nivel, puntuación o esperado.
void oledMostrarEstado(const char* estado, int nivel, int puntuacion, const char* colorEsperado);

// Muestra un color grande durante la secuencia (llamar al encender cada LED)
void oledMostrarColor(const char* color);

// Pantalla de bienvenida al arrancar
void oledMostrarBienvenida();

// Pantalla de game over con puntuación final
void oledMostrarGameOver(int puntuacion);

// Limpia el display (pantalla en negro)
void oledLimpiar();
