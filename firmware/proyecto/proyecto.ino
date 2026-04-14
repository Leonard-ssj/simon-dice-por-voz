/*
 * proyecto.ino — Simon Dice por Voz
 * Firmware principal — capa de hardware (ESP32-S3)
 *
 * Este firmware NO tiene lógica de juego. Solo maneja hardware:
 *   - Captura audio del MAX4466 cuando se activa PTT
 *   - Envía audio al PC por Serial (Python lo procesa con Whisper)
 *   - Recibe comandos del PC: LED:X, OLED:texto
 *   - Muestra estado en OLED SSD1306 y RGB WS2812B
 *
 * La lógica del juego vive completamente en servidor_pc/servidor.py
 *
 * HARDWARE (YD-ESP32-S3 en protoboard):
 *   MAX4466:  OUT=GPIO4    VCC=3.3V   GND=GND
 *   OLED:     SDA=GPIO10   SCL=GPIO11  VCC=3.3V  GND=GND
 *   RGB:      WS2812B integrado GPIO48
 *   Botón:    GPIO0 (BOOT, activo LOW) — PTT físico
 *
 * BOARD SETTINGS (Arduino IDE / Antigravity):
 *   Board:            ESP32S3 Dev Module
 *   PSRAM:            OPI PSRAM
 *   Flash Size:       16MB (128Mb)
 *   USB CDC on Boot:  Enabled
 *   Upload Speed:     921600
 *
 * LIBRERÍAS REQUERIDAS (Tools > Manage Libraries):
 *   - Adafruit SSD1306      (by Adafruit)
 *   - Adafruit GFX Library  (by Adafruit)
 *   - Adafruit NeoPixel     (by Adafruit)
 *
 * PROTOCOLO SERIAL (921600 baud):
 *
 *   ESP32 → PC:
 *     READY                 sistema inicializado
 *     PTT_START             empezó grabación (botón físico o Serial 'R')
 *     PTT_STOP              paró grabación
 *     AUDIO_CORTO           grabación demasiado corta, descartada
 *     AUDIO_START:N         inicia transmisión de N bytes PCM int16 LE 8kHz
 *     [N bytes PCM]         audio crudo
 *     AUDIO_END             fin de transmisión
 *
 *   PC → ESP32:
 *     R                     iniciar grabación (PTT remoto — spacebar del panel)
 *     T                     detener grabación (PTT remoto)
 *     LED:ROJO              encender RGB rojo
 *     LED:VERDE             encender RGB verde
 *     LED:AZUL              encender RGB azul
 *     LED:AMARILLO          encender RGB amarillo
 *     LED:OFF               apagar RGB
 *     OLED:l1|l2|l3         mostrar 3 líneas en OLED (| = separador de línea)
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include <driver/i2s.h>   // MAX98357A I2S speaker
#include <math.h>

// ─── Pines — micrófono + OLED + RGB + botón ───────────────────────────────────
#define MIC_OUT_PIN   4      // MAX4466 OUT — ADC1_CH3
// BTN_PTT (GPIO0) ELIMINADO — GPIO0 tiene falsos positivos en boot y durante el juego.
// El PTT ahora es SOLO por Serial 'R'/'T' desde el panel web (barra espaciadora).
#define OLED_SDA      10
#define OLED_SCL      11
#define OLED_ADDR     0x3C
#define OLED_W        128
#define OLED_H        32
#define RGB_PIN       48     // WS2812B integrado
#define RGB_BRILLO    40     // 0-255 (40 = brillo suave)

// ─── Pines — MAX98357A I2S speaker ────────────────────────────────────────────
// Conectar en protoboard:
//   MAX98357A LRC  → GPIO5    (Word Select / LRCLK)
//   MAX98357A BCLK → GPIO6    (Bit Clock)
//   MAX98357A DIN  → GPIO7    (Data In desde ESP32)
//   MAX98357A VIN  → 5V o 3.3V
//   MAX98357A GND  → GND
//   MAX98357A GAIN → libre    (= 15dB default)
//   MAX98357A SD   → libre    (= encendido)
//   MAX98357A +/-  → altavoz 4-8Ω
#define SPEAKER_WS    5      // LRC
#define SPEAKER_BCK   6      // BCLK
#define SPEAKER_DATA  7      // DIN
#define SPEAKER_RATE  16000  // Hz — Whisper usa 16kHz, misma tasa para el speaker
#define I2S_PORT      I2S_NUM_0

// ─── Audio de captura (MAX4466 → ADC) ────────────────────────────────────────
// 8kHz: cada muestra = 125µs. Con OVERSAMPLE=2 (2x40µs=80µs) hay 45µs de margen.
// Sin OVERSAMPLE, el ruido ADC sería mayor. Con 4 (4x40=160µs) se supera el
// intervalo → efecto ardilla (voz acelerada). 2 es el equilibrio óptimo.
#define SAMPLE_RATE     8000
#define OVERSAMPLE      2         // 2 lecturas ADC por muestra → reduce ruido ~3dB
#define GANANCIA_SW     6         // amplificación de software (era 4 — subida para MAX4466 débil)
#define MAX_SEG_GRAB    10        // máximo de grabación en segundos
#define MAX_MUESTRAS    (SAMPLE_RATE * MAX_SEG_GRAB)   // 80000 muestras = 160KB

// ─── Coeficientes filtros biquad (Butterworth 2do orden, Fs=8kHz) ────────────
// Calculados con Audio EQ Cookbook (Robert Bristow-Johnson)
// HPF @ 80Hz — elimina DC bias del MAX4466 y rumble de baja frecuencia
static const float HPF_B0 =  0.9566f, HPF_B1 = -1.9131f, HPF_B2 = 0.9566f;
static const float HPF_A1 = -1.9112f, HPF_A2 =  0.9150f;
// LPF @ 3400Hz — banda de voz telefónica, corta ruido ADC de alta frecuencia
static const float LPF_B0 = 0.7158f,  LPF_B1 = 1.4316f,  LPF_B2 = 0.7158f;
static const float LPF_A1 = 1.3490f,  LPF_A2 = 0.5141f;

// ─── Objetos ──────────────────────────────────────────────────────────────────
Adafruit_SSD1306  oled(OLED_W, OLED_H, &Wire, -1);
Adafruit_NeoPixel pixel(1, RGB_PIN, NEO_GRB + NEO_KHZ800);
bool              oled_listo = false;

// ─── Estado ───────────────────────────────────────────────────────────────────
enum Estado { LISTO, GRABANDO };
Estado   estado = LISTO;
// btn_previo y ptt_remoto ELIMINADOS — el botón físico fue quitado del proyecto.
// El PTT es exclusivamente por Serial ('R' para iniciar, 'T' para detener).

// Buffer de audio en PSRAM (10s × 8kHz × 2 bytes = 160KB)
static int16_t* audio_buf        = nullptr;
static int      muestras_grabadas = 0;

// Estado de los filtros biquad (se resetea al inicio de cada grabación)
static float hx1, hx2, hy1, hy2;   // HPF 80Hz
static float lx1, lx2, ly1, ly2;   // LPF 3400Hz

// Buffer acumulador de líneas Serial entrantes (comandos del PC)
static String serial_buf = "";

// ─── Prototipos ───────────────────────────────────────────────────────────────
void oled_mostrar(const char* l1, const char* l2 = "", const char* l3 = "");
void rgb_color(const char* nombre);
void rgb_apagar();
void iniciar_grabacion();
void detener_y_enviar();
void enviar_audio();
void procesar_serial_entrada();
void procesar_linea(const String& linea);
void setup_speaker();
void play_tone(int freq_hz, int dur_ms, int vol = 22000);
void play_color_tone(const char* color);

// =============================================================================
//  MAX98357A — Configurar I2S para salida de audio
// =============================================================================
void setup_speaker() {
  i2s_config_t cfg = {};
  cfg.mode              = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate       = SPEAKER_RATE;
  cfg.bits_per_sample   = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format    = I2S_CHANNEL_FMT_ONLY_LEFT;   // mono
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags  = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count     = 8;
  cfg.dma_buf_len       = 64;
  cfg.use_apll          = false;
  cfg.tx_desc_auto_clear = true;
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);

  i2s_pin_config_t pins = {};
  pins.bck_io_num    = SPEAKER_BCK;
  pins.ws_io_num     = SPEAKER_WS;
  pins.data_out_num  = SPEAKER_DATA;
  pins.data_in_num   = I2S_PIN_NO_CHANGE;
  i2s_set_pin(I2S_PORT, &pins);
  i2s_zero_dma_buffer(I2S_PORT);   // silencio inicial
}

// =============================================================================
//  play_tone — Genera y reproduce un tono sinusoidal por I2S
//  freq_hz : frecuencia en Hz  (0 = silencio)
//  dur_ms  : duración en milisegundos
//  vol     : amplitud 0-32767  (22000 ≈ volumen moderado)
// =============================================================================
void play_tone(int freq_hz, int dur_ms, int vol) {
  if (freq_hz <= 0 || dur_ms <= 0) return;
  int n = (SPEAKER_RATE * dur_ms) / 1000;
  int16_t* buf = (int16_t*)malloc(n * sizeof(int16_t));
  if (!buf) return;
  for (int i = 0; i < n; i++) {
    buf[i] = (int16_t)(vol * sinf(2.0f * (float)M_PI * freq_hz * i / SPEAKER_RATE));
  }
  size_t bw;
  i2s_write(I2S_PORT, buf, n * sizeof(int16_t), &bw, portMAX_DELAY);
  free(buf);
}

// =============================================================================
//  play_color_tone — Tono único por color del Simon Dice
//  Los tonos deben sonar distintos y ser fáciles de memorizar:
//    ROJO    → Do  (262 Hz) — grave
//    VERDE   → Mi  (330 Hz) — medio-grave
//    AZUL    → Sol (392 Hz) — medio-agudo
//    AMARILLO→ Si  (494 Hz) — agudo
// =============================================================================
void play_color_tone(const char* color) {
  struct { const char* n; int hz; } tabla[] = {
    { "ROJO",     262 },
    { "VERDE",    330 },
    { "AZUL",     392 },
    { "AMARILLO", 494 },
    { nullptr,      0 },
  };
  for (int i = 0; tabla[i].n != nullptr; i++) {
    if (strcmp(color, tabla[i].n) == 0) {
      play_tone(tabla[i].hz, 350);   // 350ms — audible sin ser molesto
      return;
    }
  }
}

// =============================================================================
//  SETUP
// =============================================================================
void setup() {
  Serial.begin(921600);
  delay(1200);   // tiempo para que el host abra el puerto

  // I2C y OLED
  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(400000);
  if (oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    oled_listo = true;
  }

  // ADC — máxima atenuación para leer señales analógicas hasta 3.3V
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // RGB
  pixel.begin();
  pixel.setBrightness(RGB_BRILLO);
  rgb_apagar();

  // MAX98357A — I2S speaker
  setup_speaker();

  // Reservar buffer de audio en PSRAM.
  // PSRAM OPI (8MB) tiene espacio de sobra; fallback a SRAM si no hay PSRAM.
  audio_buf = (int16_t*)ps_malloc((size_t)MAX_MUESTRAS * 2);
  if (!audio_buf) {
    audio_buf = (int16_t*)malloc((size_t)MAX_MUESTRAS * 2);
    if (!audio_buf) {
      oled_mostrar("ERROR MEMORIA", "Sin PSRAM", "Ver board settings");
      while (true) delay(1000);   // detener — sin buffer no hay juego
    }
    // PSRAM no disponible: grabaciones > 2-3s saturarán SRAM
    oled_mostrar("WARN: sin PSRAM", "Max ~2s grab", "");
    delay(2000);
  }

  oled_mostrar("Simon Dice", "por Voz v1.0", "Conectando...");

  // Anunciar que el firmware está listo al PC
  Serial.println("READY");
}

// =============================================================================
//  LOOP
// =============================================================================
void loop() {

  // ── Modo GRABANDO: loop de captura de audio a 8kHz ────────────────────────
  if (estado == GRABANDO) {
    uint32_t t0 = micros();
    const uint32_t intervalo_us = 1000000UL / SAMPLE_RATE;   // 125µs

    // Oversampling (promedio de OVERSAMPLE lecturas) → reduce ruido ADC
    int32_t suma = 0;
    for (int j = 0; j < OVERSAMPLE; j++) suma += analogRead(MIC_OUT_PIN);
    float x = (float)suma / OVERSAMPLE - 2048.0f;   // centrar en 0, rango ±2048

    // Biquad HPF 80Hz (Direct Form I)
    float hp = HPF_B0*x  + HPF_B1*hx1 + HPF_B2*hx2 - HPF_A1*hy1 - HPF_A2*hy2;
    hx2 = hx1; hx1 = x;
    hy2 = hy1; hy1 = hp;

    // Biquad LPF 3400Hz
    float lp = LPF_B0*hp + LPF_B1*lx1 + LPF_B2*lx2 - LPF_A1*ly1 - LPF_A2*ly2;
    lx2 = lx1; lx1 = hp;
    ly2 = ly1; ly1 = lp;

    // Escalar a 16-bit con ganancia de software
    int32_t m = (int32_t)(lp * (GANANCIA_SW * 16.0f));
    if (m >  32767) m =  32767;
    if (m < -32768) m = -32768;
    if (muestras_grabadas < MAX_MUESTRAS) {
      audio_buf[muestras_grabadas++] = (int16_t)m;
    }

    // ── Verificar condiciones de parada ─────────────────────────────────────
    // Solo 'T' por Serial (spacebar suelto en el panel web)
    if (Serial.available()) {
      char c = (char)Serial.peek();
      if (c == 'T' || c == 't') {
        Serial.read();
        while (Serial.available()) Serial.read();  // flush
        detener_y_enviar();
        return;
      }
      Serial.read();  // descartar cualquier otro byte durante grabación
    }

    // 2. Límite de 10 segundos
    if (muestras_grabadas >= MAX_MUESTRAS) {
      detener_y_enviar();
      return;
    }

    // Esperar hasta completar el intervalo de 125µs para mantener 8kHz exacto
    while (micros() - t0 < intervalo_us);
    return;
  }

  // ── Modo LISTO: procesar comandos Serial del PC ───────────────────────────
  // El PTT es SOLO por Serial — no hay botón físico.
  procesar_serial_entrada();
}

// =============================================================================
//  PTT — Iniciar grabación
// =============================================================================
void iniciar_grabacion() {
  if (estado == GRABANDO || !audio_buf) return;

  muestras_grabadas = 0;

  // Resetear estado de los filtros biquad (evita transiente inicial)
  hx1 = hx2 = hy1 = hy2 = 0.0f;
  lx1 = lx2 = ly1 = ly2 = 0.0f;

  estado = GRABANDO;

  // RGB rojo = grabando
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));
  pixel.show();

  oled_mostrar("GRABANDO...", "Habla ahora", "Suelta para enviar");
  Serial.println("PTT_START");
}

// =============================================================================
//  PTT — Detener y preparar envío
// =============================================================================
void detener_y_enviar() {
  estado = LISTO;
  Serial.println("PTT_STOP");

  // RGB azul = procesando (Whisper en PC)
  pixel.setPixelColor(0, pixel.Color(0, 0, 255));
  pixel.show();
  oled_mostrar("Procesando...", "Whisper", "espera...");

  enviar_audio();
}

// =============================================================================
//  Enviar audio al PC por Serial
// =============================================================================
void enviar_audio() {
  // Validar duración mínima (0.25s = 2000 muestras a 8kHz)
  if (muestras_grabadas < (SAMPLE_RATE / 4)) {
    Serial.println("AUDIO_CORTO");
    pixel.clear(); pixel.show();
    oled_mostrar("PTT muy corto", "Habla mas tiempo", "");
    return;
  }

  int bytes_audio = muestras_grabadas * 2;

  // Encabezado con número exacto de bytes
  Serial.printf("AUDIO_START:%d\n", bytes_audio);

  // Audio PCM int16 little-endian
  Serial.write((const uint8_t*)audio_buf, (size_t)bytes_audio);

  // Terminador
  Serial.print("\nAUDIO_END\n");

  // El firmware NO bloquea esperando respuesta.
  // El PC (servidor.py) procesará el audio con Whisper y enviará
  // comandos LED: y OLED: de vuelta cuando tenga el resultado.
  // El loop() normal los procesará vía procesar_serial_entrada().
}

// =============================================================================
//  SERIAL ENTRADA — procesar comandos llegando del PC
// =============================================================================
void procesar_serial_entrada() {
  while (Serial.available()) {
    char c = (char)Serial.read();

    // 'R' = iniciar grabación (spacebar presionado en el panel web)
    if (c == 'R' || c == 'r') {
      while (Serial.available()) Serial.read();
      if (estado == LISTO) {
        iniciar_grabacion();
      }
      return;
    }

    // 'T' = detener grabación (spacebar suelto — solo relevante en GRABANDO,
    //       en LISTO se ignora silenciosamente)
    if (c == 'T' || c == 't') {
      while (Serial.available()) Serial.read();
      return;
    }

    // Acumular líneas de texto
    if (c == '\n') {
      serial_buf.trim();
      if (serial_buf.length() > 0) {
        procesar_linea(serial_buf);
      }
      serial_buf = "";
    } else if (c != '\r') {
      serial_buf += c;
    }
  }
}

// =============================================================================
//  Procesar una línea de comando del PC
// =============================================================================
void procesar_linea(const String& linea) {

  // ── LED:COLOR ───────────────────────────────────────────────────────────────
  if (linea.startsWith("LED:")) {
    String color = linea.substring(4);
    color.toUpperCase();
    rgb_color(color.c_str());

    if (color == "OFF") {
      oled_mostrar("ESCUCHANDO", "Presiona ESPACIO", "para hablar");
    } else {
      char buf[20];
      snprintf(buf, sizeof(buf), "COLOR: %s", color.c_str());
      oled_mostrar(buf, "", "");
      // Tono del color — MAX98357A (350ms, no bloquea el serial porque
      // Python espera DURACION_LED=800ms antes de enviar el siguiente LED)
      play_color_tone(color.c_str());
    }
    return;
  }

  // ── TONE:freq,dur — tono personalizado desde Python ──────────────────────
  if (linea.startsWith("TONE:")) {
    String params = linea.substring(5);
    int coma = params.indexOf(',');
    int freq = params.toInt();
    int dur  = (coma >= 0) ? params.substring(coma + 1).toInt() : 300;
    play_tone(freq, dur);
    return;
  }

  // ── OLED:linea1|linea2|linea3 ───────────────────────────────────────────────
  if (linea.startsWith("OLED:")) {
    String contenido = linea.substring(5);

    // Truncar cada línea a 21 chars (OLED 128px / 6px por char ≈ 21 chars)
    int sep1 = contenido.indexOf('|');
    int sep2 = (sep1 >= 0) ? contenido.indexOf('|', sep1 + 1) : -1;

    String l1 = (sep1 >= 0) ? contenido.substring(0, sep1)       : contenido;
    String l2 = (sep1 >= 0 && sep2 < 0) ? contenido.substring(sep1 + 1) : "";
    String l3 = "";
    if (sep1 >= 0 && sep2 >= 0) {
      l2 = contenido.substring(sep1 + 1, sep2);
      l3 = contenido.substring(sep2 + 1);
    }

    oled_mostrar(l1.c_str(), l2.c_str(), l3.c_str());
    return;
  }
}

// =============================================================================
//  RGB — Encender color por nombre
// =============================================================================
void rgb_color(const char* nombre) {
  struct { const char* n; uint8_t r, g, b; } tabla[] = {
    { "ROJO",     255,   0,   0 },
    { "VERDE",      0, 220,   0 },
    { "AZUL",       0,   0, 255 },
    { "AMARILLO", 255, 200,   0 },
    { "BLANCO",   255, 255, 255 },
    { "OFF",        0,   0,   0 },
    { nullptr,      0,   0,   0 },
  };
  for (int i = 0; tabla[i].n != nullptr; i++) {
    if (strcmp(nombre, tabla[i].n) == 0) {
      pixel.setPixelColor(0, pixel.Color(tabla[i].r, tabla[i].g, tabla[i].b));
      pixel.show();
      return;
    }
  }
  // Color desconocido → apagar
  rgb_apagar();
}

void rgb_apagar() {
  pixel.clear();
  pixel.show();
}

// =============================================================================
//  OLED — Mostrar hasta 3 líneas de texto (textSize=1 → 6×8px por carácter)
// =============================================================================
void oled_mostrar(const char* l1, const char* l2, const char* l3) {
  if (!oled_listo) return;
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0,  0); oled.print(l1);
  oled.setCursor(0, 11); oled.print(l2);
  oled.setCursor(0, 22); oled.print(l3);
  oled.display();
}
