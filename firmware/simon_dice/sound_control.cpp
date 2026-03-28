#include "sound_control.h"
#include <Arduino.h>
#include <driver/i2s.h>

// ============================================================
// sound_control.cpp — Tonos I2S para el amplificador MAX98357A
//
// Genera ondas cuadradas via I2S para el amplificador digital.
// Usa I2S_NUM_1 (I2S_NUM_0 está reservado para el micrófono).
// ============================================================

// Frecuencias de los colores del juego (Do, Mi, Sol, Si — C4-B4)
#define FREQ_ROJO      262  // Do4  — C4
#define FREQ_VERDE     330  // Mi4  — E4
#define FREQ_AZUL      392  // Sol4 — G4
#define FREQ_AMARILLO  494  // Si4  — B4

// Frecuencias de feedback
#define FREQ_CORRECTO  1047  // Do6
#define FREQ_ERROR     196   // Sol3 (grave)
#define FREQ_INICIO    880   // La5

static bool _inicializado = false;

void sonidoInicializar() {
    // Habilitar el MAX98357A (SD pin HIGH = activo)
    if (I2S_SPK_SD_PIN >= 0) {
        pinMode(I2S_SPK_SD_PIN, OUTPUT);
        digitalWrite(I2S_SPK_SD_PIN, HIGH);
    }

    i2s_config_t cfg = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate          = SPK_SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_RIGHT_LEFT,   // estéreo (MAX98357A mono sumado)
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = 4,
        .dma_buf_len          = SPK_CHUNK_SIZE,
        .use_apll             = false,
        .tx_desc_auto_clear   = true,
        .fixed_mclk           = 0
    };

    i2s_pin_config_t pines = {
        .mck_io_num   = I2S_PIN_NO_CHANGE,   // sin MCLK (MAX98357A no lo necesita)
        .bck_io_num   = I2S_SPK_BCLK_PIN,
        .ws_io_num    = I2S_SPK_WS_PIN,
        .data_out_num = I2S_SPK_DOUT_PIN,
        .data_in_num  = I2S_PIN_NO_CHANGE
    };

    esp_err_t r = i2s_driver_install(I2S_NUM_SPK, &cfg, 0, NULL);
    if (r != ESP_OK) {
        // Fallback: si I2S falla, el sistema continúa sin sonido
        _inicializado = false;
        return;
    }
    i2s_set_pin(I2S_NUM_SPK, &pines);
    _inicializado = true;
}

// ---- Generador de tonos ----

void sonidoBeep(int frecuenciaHz, int duracionMs) {
    if (!_inicializado || frecuenciaHz <= 0) return;

    int samplesPerPeriod = SPK_SAMPLE_RATE / frecuenciaHz;
    int totalSamples     = (SPK_SAMPLE_RATE / 1000) * duracionMs;

    // Buffer de muestras estéreo: izquierda + derecha (por eso × 2)
    int16_t buf[SPK_CHUNK_SIZE * 2];
    int generado = 0;
    int fase     = 0;

    while (generado < totalSamples) {
        int porGenerar = min((int)(SPK_CHUNK_SIZE), totalSamples - generado);
        for (int i = 0; i < porGenerar; i++) {
            int16_t muestra = (fase < samplesPerPeriod / 2) ? SPK_AMPLITUD : -SPK_AMPLITUD;
            buf[i * 2]     = muestra;  // canal izquierdo
            buf[i * 2 + 1] = muestra;  // canal derecho
            fase = (fase + 1) % samplesPerPeriod;
        }
        size_t bw = 0;
        i2s_write(I2S_NUM_SPK, buf, porGenerar * sizeof(int16_t) * 2, &bw, portMAX_DELAY);
        generado += porGenerar;
    }

    // Silencio corto al final para separar tonos limpios
    memset(buf, 0, SPK_CHUNK_SIZE * sizeof(int16_t) * 2);
    size_t bw = 0;
    i2s_write(I2S_NUM_SPK, buf, SPK_CHUNK_SIZE * sizeof(int16_t) * 2, &bw, portMAX_DELAY);
}

// ---- Sonidos del juego ----

void sonidoColor(Comando color) {
    int freq = 0;
    switch (color) {
        case CMD_ROJO:     freq = FREQ_ROJO;     break;
        case CMD_VERDE:    freq = FREQ_VERDE;    break;
        case CMD_AZUL:     freq = FREQ_AZUL;     break;
        case CMD_AMARILLO: freq = FREQ_AMARILLO; break;
        default: return;
    }
    sonidoBeep(freq, 400);
}

void sonidoCorrecto() {
    sonidoBeep(FREQ_CORRECTO, 120);
    delay(40);
    sonidoBeep(FREQ_CORRECTO, 240);
}

void sonidoError() {
    sonidoBeep(FREQ_ERROR, 200);
    delay(80);
    sonidoBeep(FREQ_ERROR, 400);
}

void sonidoInicio() {
    // Escala ascendente Do-Mi-Sol-Do5
    const int notas[] = {262, 330, 392, 523};
    for (int i = 0; i < 4; i++) {
        sonidoBeep(notas[i], 120);
        delay(20);
    }
}

void sonidoGameOver() {
    // Escala descendente Do5-La-Fa-Do
    const int notas[] = {523, 440, 349, 262};
    for (int i = 0; i < 4; i++) {
        sonidoBeep(notas[i], 220);
        delay(40);
    }
}

void sonidoNuevoNivel(int nivel) {
    // 1 beep por nivel (máx 4 para que sea rápido)
    int repeticiones = min(nivel, 4);
    for (int i = 0; i < repeticiones; i++) {
        sonidoBeep(FREQ_INICIO, 90);
        delay(60);
    }
}
