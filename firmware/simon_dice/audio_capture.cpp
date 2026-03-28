#include "audio_capture.h"
#include "serial_comm.h"
#include <Arduino.h>
#include <driver/i2s.h>

// ============================================================
// audio_capture.cpp — Implementación captura I2S + PTT buffer
// ============================================================

// ---- Buffer PSRAM para captura PTT ----
static int16_t*  _pttBuffer       = nullptr;  // asignado en PSRAM
static int       _pttMuestras     = 0;
static bool      _pttCapturando   = false;

// Buffer de trabajo para lectura DMA
static int16_t _dmaBuffer[BUFFER_SIZE];

// ---- Tabla base64 ----
static const char _B64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// Codifica hasta 45 bytes en 60 chars base64 (sin '\n' ni '\0' incluidos)
// Retorna longitud de la salida (múltiplo de 4, máx 60)
static int _base64Line(const uint8_t* src, int len, char* dst) {
    int j = 0;
    for (int i = 0; i < len; i += 3) {
        int rem   = len - i;
        uint8_t b0 = src[i];
        uint8_t b1 = (rem > 1) ? src[i + 1] : 0;
        uint8_t b2 = (rem > 2) ? src[i + 2] : 0;

        dst[j++] = _B64[b0 >> 2];
        dst[j++] = _B64[((b0 & 0x03) << 4) | (b1 >> 4)];
        dst[j++] = (rem > 1) ? _B64[((b1 & 0x0F) << 2) | (b2 >> 6)] : '=';
        dst[j++] = (rem > 2) ? _B64[b2 & 0x3F] : '=';
    }
    return j;
}

// ---- Inicialización ----

void audioInicializar() {
    // Asignar buffer en PSRAM (2 MB disponibles en ESP32-S3-N8R2)
    _pttBuffer = (int16_t*) ps_malloc(AUDIO_PTT_MAX_BYTES);
    if (!_pttBuffer) {
        // Sin PSRAM disponible: sin captura PTT (logs por Serial)
        Serial.println("// [Audio] ERROR: ps_malloc fallido — sin captura PTT");
    }

    // Configurar I2S_NUM_0 en modo RX para el micrófono INMP441
    i2s_config_t cfg = {
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
        .mck_io_num   = I2S_PIN_NO_CHANGE,   // sin MCLK (INMP441 no lo necesita)
        .bck_io_num   = I2S_SCK_PIN,
        .ws_io_num    = I2S_WS_PIN,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = I2S_SD_PIN
    };

    i2s_driver_install(I2S_NUM_MIC, &cfg, 0, NULL);
    i2s_set_pin(I2S_NUM_MIC, &pines);
    i2s_start(I2S_NUM_MIC);
}

// ---- Modo PTT ----

void audioCapturaIniciar() {
    if (!_pttBuffer) return;
    _pttMuestras   = 0;
    _pttCapturando = true;
    // Vaciar el DMA buffer de muestras acumuladas antes del PTT
    i2s_zero_dma_buffer(I2S_NUM_MIC);
}

void audioCapturaPararYEnviar() {
    if (!_pttCapturando) return;
    _pttCapturando = false;

    // Leer cualquier muestra que quedó en el DMA
    if (_pttBuffer) {
        while (_pttMuestras < AUDIO_PTT_MAX_MUESTRAS) {
            // Intentar leer con timeout corto (10ms)
            size_t bytesLeidos = 0;
            esp_err_t r = i2s_read(I2S_NUM_MIC,
                                   _dmaBuffer,
                                   sizeof(_dmaBuffer),
                                   &bytesLeidos,
                                   pdMS_TO_TICKS(10));
            if (r != ESP_OK || bytesLeidos == 0) break;

            int n = bytesLeidos / sizeof(int16_t);
            int copiar = min(n, AUDIO_PTT_MAX_MUESTRAS - _pttMuestras);
            memcpy(&_pttBuffer[_pttMuestras], _dmaBuffer, copiar * sizeof(int16_t));
            _pttMuestras += copiar;
        }
    }

    if (!_pttBuffer || _pttMuestras == 0) {
        serialEnviar("AUDIO:VACIO");
        return;
    }

    // ── Enviar audio en base64 por Serial ──
    // Protocolo:
    //   AUDIO:START:<bytes>\n
    //   <línea base64, 60 chars>\n  ...
    //   AUDIO:END\n
    //
    // 45 bytes de entrada → 60 chars base64 por línea

    int totalBytes = _pttMuestras * sizeof(int16_t);
    char header[32];
    snprintf(header, sizeof(header), "AUDIO:START:%d", totalBytes);
    serialEnviar(header);

    const uint8_t* datos = (const uint8_t*) _pttBuffer;
    char linea[64];  // 60 chars + '\0' + margen

    for (int offset = 0; offset < totalBytes; offset += 45) {
        int chunk = min(45, totalBytes - offset);
        int len   = _base64Line(datos + offset, chunk, linea);
        linea[len] = '\0';
        serialEnviar(linea);
    }

    serialEnviar("AUDIO:END");
}

bool audioCapturaActiva() {
    return _pttCapturando;
}

// ---- Lectura DMA continua (usada internamente y en VAD) ----

size_t audioLeerMuestras(int16_t* buffer, size_t cantMuestras) {
    size_t bytesLeidos = 0;
    i2s_read(I2S_NUM_MIC,
             buffer,
             cantMuestras * sizeof(int16_t),
             &bytesLeidos,
             portMAX_DELAY);
    return bytesLeidos / sizeof(int16_t);
}

// ---- Loop interno de captura PTT (llamar desde loop() si capturando) ----
// Lee el DMA y acumula en _pttBuffer mientras _pttCapturando sea true.
void audioCapturaLoop() {
    if (!_pttCapturando || !_pttBuffer) return;
    if (_pttMuestras >= AUDIO_PTT_MAX_MUESTRAS) return;  // buffer lleno

    size_t bytesLeidos = 0;
    esp_err_t r = i2s_read(I2S_NUM_MIC,
                           _dmaBuffer,
                           sizeof(_dmaBuffer),
                           &bytesLeidos,
                           0);  // timeout = 0 (no bloqueante)
    if (r != ESP_OK || bytesLeidos == 0) return;

    int n      = bytesLeidos / sizeof(int16_t);
    int copiar = min(n, AUDIO_PTT_MAX_MUESTRAS - _pttMuestras);
    memcpy(&_pttBuffer[_pttMuestras], _dmaBuffer, copiar * sizeof(int16_t));
    _pttMuestras += copiar;
}

// ---- VAD simple (modo stream) ----
bool audioHayVoz() {
    size_t n = audioLeerMuestras(_dmaBuffer, BUFFER_SIZE);
    if (n == 0) return false;
    for (size_t i = 0; i < n; i++) {
        if (abs(_dmaBuffer[i]) > VAD_UMBRAL) return true;
    }
    return false;
}
