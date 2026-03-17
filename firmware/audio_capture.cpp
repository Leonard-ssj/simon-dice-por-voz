#include "audio_capture.h"
#include "serial_comm.h"
#include <Arduino.h>
#include <driver/i2s.h>

// ============================================================
// audio_capture.cpp — Implementación captura I2S
// ============================================================

static int16_t _bufferAudio[BUFFER_SIZE];

void audioInicializar() {
    i2s_config_t config = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate          = SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = 8,
        .dma_buf_len          = BUFFER_SIZE,
        .use_apll             = false,
        .tx_desc_auto_clear   = false,
        .fixed_mclk           = 0
    };

    i2s_pin_config_t pines = {
        .bck_io_num   = I2S_SCK_PIN,
        .ws_io_num    = I2S_WS_PIN,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = I2S_SD_PIN
    };

    i2s_driver_install(I2S_NUM_MIC, &config, 0, NULL);
    i2s_set_pin(I2S_NUM_MIC, &pines);
    i2s_start(I2S_NUM_MIC);
}

size_t audioLeerMuestras(int16_t* buffer, size_t cantMuestras) {
    size_t bytesLeidos = 0;
    i2s_read(I2S_NUM_MIC, buffer, cantMuestras * sizeof(int16_t), &bytesLeidos, portMAX_DELAY);
    return bytesLeidos / sizeof(int16_t);
}

bool audioHayVoz() {
    size_t n = audioLeerMuestras(_bufferAudio, BUFFER_SIZE);
    if (n == 0) return false;

    // VAD simple: detecta si alguna muestra supera el umbral
    for (size_t i = 0; i < n; i++) {
        if (abs(_bufferAudio[i]) > VAD_UMBRAL) return true;
    }
    return false;
}

bool audioCapturarYEnviar() {
    // Captura CHUNK_DURACION ms de audio y envía los bytes por Serial
    int totalMuestras = (SAMPLE_RATE * CHUNK_DURACION) / 1000;
    int muestrasLeidas = 0;

    serialEnviar("AUDIO:START");

    while (muestrasLeidas < totalMuestras) {
        int aLeer = min(BUFFER_SIZE, totalMuestras - muestrasLeidas);
        size_t n = audioLeerMuestras(_bufferAudio, aLeer);

        // Enviar bytes raw por Serial (little-endian, 16-bit, mono, 16kHz)
        Serial.write((uint8_t*)_bufferAudio, n * sizeof(int16_t));
        muestrasLeidas += n;
    }

    serialEnviar("AUDIO:END");
    return true;
}

bool audioEsperarVoz(int duracionMaxMs) {
    unsigned long inicio = millis();

    // Esperar inicio de voz
    while (millis() - inicio < (unsigned long)duracionMaxMs) {
        if (audioHayVoz()) {
            return audioCapturarYEnviar();
        }
        delay(10);
    }
    return false; // Timeout sin detectar voz
}
