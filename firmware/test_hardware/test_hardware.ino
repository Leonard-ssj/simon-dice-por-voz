/*
 * test_hardware.ino - Simon Dice por Voz
 * Pruebas de hardware con menu interactivo por Serial Monitor.
 *
 * LIBRERIAS REQUERIDAS (Tools > Manage Libraries):
 *   - Adafruit SSD1306      (by Adafruit)
 *   - Adafruit GFX Library  (by Adafruit)
 *   - Adafruit NeoPixel     (by Adafruit)  <- poner USAR_RGB 0 si no esta
 *
 * BOARD SETTINGS:
 *   Board: ESP32S3 Dev Module | PSRAM: OPI PSRAM | Flash: 16MB
 *   USB CDC on Boot: Enabled  | Upload Speed: 921600
 *
 * CONEXIONES:
 *   MAX4466: OUT=GPIO4  VCC=3.3V  GND=GND
 *   OLED:    SDA=GPIO10  SCL=GPIO11  VCC=3.3V  GND=GND
 *   RGB:     WS2812B integrado GPIO48
 *
 * TEST 5 — GRABACION:
 *   1. Cerrar Serial Monitor del Arduino IDE
 *   2. Correr:  python capturar_audio.py
 *   3. Cuando diga "listo", enviar '5' por el script
 *   4. Hablar al microfono durante 10 segundos
 *   5. Se guarda grabacion.wav — abrirlo con cualquier reproductor
 */

// ─── Cambiar a 0 si no esta instalada Adafruit NeoPixel ──────────────────────
#define USAR_RGB 1
// ─────────────────────────────────────────────────────────────────────────────

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#if USAR_RGB
  #include <Adafruit_NeoPixel.h>
#endif

// ─── Pines OLED ───────────────────────────────────────────────────────────────
#define OLED_SDA    10
#define OLED_SCL    11
#define OLED_ADDR   0x3C
#define OLED_W      128
#define OLED_H      32

// ─── Pin MAX4466 (analogico) ──────────────────────────────────────────────────
#define MIC_OUT_PIN   4

// ─── Boton PTT (Push-To-Talk) ─────────────────────────────────────────────────
// GPIO0 = boton BOOT del YD-ESP32-S3. Active LOW (presionado = 0).
// Se usa como PTT en Test 6: mantén presionado para grabar, suelta para enviar.
#define BTN_PTT       0

// ─── Grabacion ────────────────────────────────────────────────────────────────
// 8kHz: analogRead del ESP32 tarda ~50-100us; 16kHz (62us/muestra) no es
// alcanzable de forma confiable y genera efecto "ardilla". A 8kHz (125us)
// hay margen suficiente. El servidor Python remuestra a 16kHz para Whisper.
#define SAMPLE_RATE     8000
#define RECORD_SEGUNDOS 10
#define TOTAL_MUESTRAS  (SAMPLE_RATE * RECORD_SEGUNDOS)  // 80000
#define TOTAL_BYTES     (TOTAL_MUESTRAS * 2)             // 160000 bytes PCM 16-bit
// OVERSAMPLE=2: analogRead en ESP32-S3 tarda ~30-40us c/u. Con 4 lecturas
// (4x40=160us) se supera el intervalo de 125us y la tasa real baja a ~6250Hz
// declarada como 8kHz -> audio 1.28x rapido = efecto ardilla.
// Con 2 lecturas (2x40=80us) hay 45us de margen -> timing exacto, sin ardilla.
// Aun hay reduccion de ruido: sqrt(2) = 1.41x ~ 3dB de mejora.
#define OVERSAMPLE      2   // 2 lecturas ADC por muestra: timing seguro, 3dB ruido menos
#define GANANCIA_SW     4   // ganancia de software: x4 aprox +12dB

// ─── Coeficientes filtros biquad (Butterworth 2do orden, Audio EQ Cookbook) ───
// Fs = 8000Hz, Q = 0.7071 (maximally flat)
// HPF @ 80Hz — elimina DC bias del MAX4466 y rumble de baja frecuencia
static const float HPF_B0 =  0.9566f, HPF_B1 = -1.9131f, HPF_B2 = 0.9566f;
static const float HPF_A1 = -1.9112f, HPF_A2 =  0.9150f;
// LPF @ 3400Hz — limita a banda de voz (telefonica), elimina ruido ADC de alta frec.
static const float LPF_B0 = 0.7158f, LPF_B1 = 1.4316f, LPF_B2 = 0.7158f;
static const float LPF_A1 = 1.3490f, LPF_A2 = 0.5141f;

// ─── RGB ──────────────────────────────────────────────────────────────────────
#define RGB_PIN    48
#define RGB_BRILLO 35

// ─── Objetos ──────────────────────────────────────────────────────────────────
Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);

#if USAR_RGB
  Adafruit_NeoPixel pixel(1, RGB_PIN, NEO_GRB + NEO_KHZ800);
#endif

bool oled_listo = false;
bool mic_listo  = false;

// ─── Prototipos ───────────────────────────────────────────────────────────────
void mostrar_menu();
void test_1_i2c_scanner();
void test_2_oled();
void test_3_rgb();
void test_4_microfono();
void test_5_grabar();
void test_6_whisper();
void mic_nivel_loop();
void mic_detener();
void oled_texto(const char* l1, const char* l2 = "", const char* l3 = "");

// =============================================================================
//  SETUP
// =============================================================================
void setup() {
  Serial.begin(921600);
  delay(1200);

  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(400000);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

#if USAR_RGB
  pixel.begin();
  pixel.setBrightness(RGB_BRILLO);
  pixel.clear();
  pixel.show();
#endif

  mostrar_menu();
}

// =============================================================================
//  LOOP
// =============================================================================
void loop() {
  if (mic_listo) {
    mic_nivel_loop();
    if (Serial.available()) {
      while (Serial.available()) Serial.read();
      mic_detener();
      Serial.println("\n[MIC] Test detenido.");
      mostrar_menu();
    }
    return;
  }

  if (!Serial.available()) return;
  char op = Serial.read();
  while (Serial.available()) Serial.read();

  Serial.println();
  switch (op) {
    case '1': test_1_i2c_scanner(); break;
    case '2': test_2_oled();        break;
    case '3': test_3_rgb();         break;
    case '4': test_4_microfono();   break;
    case '5': test_5_grabar();      break;
    case '6': test_6_whisper();     break;
    case '0':
      test_1_i2c_scanner();
      test_2_oled();
      test_3_rgb();
      test_4_microfono();
      break;
    default:
      Serial.printf("Opcion '%c' no reconocida.\n", op);
      break;
  }

  if (!mic_listo) {
    Serial.println();
    mostrar_menu();
  }
}

// =============================================================================
//  MENU
// =============================================================================
void mostrar_menu() {
  Serial.println();
  Serial.println("======================================");
  Serial.println("   TEST HARDWARE - Simon Dice");
  Serial.println("======================================");
  Serial.println("  1 -> Scanner I2C");
  Serial.println("  2 -> OLED SSD1306");
#if USAR_RGB
  Serial.println("  3 -> RGB LED WS2812B");
#else
  Serial.println("  3 -> RGB LED (deshabilitado)");
#endif
  Serial.println("  4 -> Microfono MAX4466 (VU meter)");
  Serial.println("  5 -> Grabar audio 10 segundos (WAV)");
  Serial.println("  6 -> Test Whisper (reconocimiento de voz)");
  Serial.println("  0 -> Todos los tests 1-4");
  Serial.println("======================================");
  Serial.println("Envia el numero...");
}

// =============================================================================
//  TEST 1 — Scanner I2C
// =============================================================================
void test_1_i2c_scanner() {
  Serial.println("--- TEST 1: Scanner I2C (SDA=10, SCL=11) ---");
  int n = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  0x%02X", addr);
      if (addr == 0x3C || addr == 0x3D) Serial.print("  <- OLED SSD1306");
      Serial.println();
      n++;
    }
  }
  if (n == 0) Serial.println("  [!] Ninguno. Verificar VCC/GND/SDA=10/SCL=11.");
  else        Serial.printf("  Total: %d dispositivo(s).\n", n);

  if (oled_listo) {
    char buf[22]; sprintf(buf, "%d dispositivo(s)", n);
    oled_texto("TEST 1: I2C SCAN", buf, n > 0 ? "OK" : "ERROR");
    delay(1500);
  }
}

// =============================================================================
//  TEST 2 — OLED SSD1306
// =============================================================================
void test_2_oled() {
  Serial.println("--- TEST 2: OLED SSD1306 (0x3C, 128x32) ---");
  if (!oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("  [!] No responde en 0x3C.");
    oled_listo = false; return;
  }
  oled_listo = true;
  Serial.println("  OK.");

  oled.clearDisplay(); oled.fillScreen(SSD1306_WHITE); oled.display();
  Serial.println("  1/4 pantalla blanca"); delay(700);

  oled.clearDisplay(); oled.setTextColor(SSD1306_WHITE); oled.setTextSize(1);
  oled.setCursor(0,  0); oled.print("Simon Dice por Voz");
  oled.setCursor(0, 11); oled.print("Test OLED OK");
  oled.setCursor(0, 22); oled.print("SDA:10  SCL:11");
  oled.display();
  Serial.println("  2/4 texto"); delay(1500);

  oled.clearDisplay();
  oled.drawRect(0,0,128,32,SSD1306_WHITE);
  oled.fillCircle(20,16,8,SSD1306_WHITE);
  oled.fillTriangle(50,2,40,30,60,30,SSD1306_WHITE);
  oled.fillRoundRect(90,4,35,24,6,SSD1306_WHITE);
  oled.display();
  Serial.println("  3/4 formas"); delay(1500);

  oled.clearDisplay(); oled.setTextSize(2);
  oled.setCursor(10,4); oled.print("LISTO!");
  oled.display();
  Serial.println("  4/4 texto grande"); delay(1000);

  oled.clearDisplay(); oled.display();
  Serial.println("  TEST OLED: COMPLETO.");
}

// =============================================================================
//  TEST 3 — RGB LED WS2812B
// =============================================================================
void test_3_rgb() {
#if USAR_RGB
  Serial.printf("--- TEST 3: RGB LED WS2812B GPIO%d ---\n", RGB_PIN);
  struct { uint8_t r,g,b; const char* n; } col[] = {
    {255,0,0,"ROJO"},{0,255,0,"VERDE"},{0,0,255,"AZUL"},
    {255,255,0,"AMARILLO"},{255,0,255,"MAGENTA"},{0,255,255,"CYAN"},
    {255,255,255,"BLANCO"},{0,0,0,"APAGADO"},
  };
  for (int i = 0; i < 8; i++) {
    pixel.setPixelColor(0, pixel.Color(col[i].r, col[i].g, col[i].b));
    pixel.show();
    Serial.printf("  -> %s\n", col[i].n);
    if (oled_listo) oled_texto("TEST 3: RGB", col[i].n);
    delay(500);
  }
  Serial.printf("  Si NO viste colores -> cambiar RGB_PIN a %d.\n", RGB_PIN==48?47:48);
  Serial.println("  TEST RGB: COMPLETO.");
#else
  Serial.println("--- TEST 3: RGB deshabilitado ---");
#endif
}

// =============================================================================
//  TEST 4 — MAX4466 VU meter
// =============================================================================
void test_4_microfono() {
  Serial.println("--- TEST 4: Microfono MAX4466 (VU meter) ---");
  Serial.println("  OUT=GPIO4  VCC=3.3V  GND=GND");
  Serial.println();

  int reposo = 0;
  for (int i = 0; i < 16; i++) reposo += analogRead(MIC_OUT_PIN);
  reposo /= 16;
  float v_reposo = reposo * 3.3f / 4095.0f;
  Serial.printf("  Reposo: %d (%.2fV)\n", reposo, v_reposo);

  if (reposo < 100) {
    Serial.println("  [!] ~0V. Verificar VCC y GND.");
    if (oled_listo) oled_texto("MAX4466 ERROR", "Reposo ~0V", "Ver Serial");
    return;
  }
  if (reposo > 4000) {
    Serial.println("  [!] ~3.3V. Verificar cable OUT=GPIO4.");
    if (oled_listo) oled_texto("MAX4466 ERROR", "Reposo ~3.3V", "Revisar OUT");
    return;
  }

  Serial.println("  OK. Habla al mic. Cualquier tecla para salir.");
  Serial.println();
  Serial.println("  ADC  | Voltaje | Nivel");
  Serial.println("  -----+---------+----------------------------------------");

  mic_listo = true;
  if (oled_listo) oled_texto("MAX4466 OK", "GPIO4 listo", "Habla al mic");
}

// =============================================================================
//  TEST 5 — Grabar 10 segundos y enviar como PCM crudo
//  Usar junto con el script Python: capturar_audio.py
// =============================================================================
void test_5_grabar() {
  Serial.println("--- TEST 5: Grabacion de audio ---");
  Serial.println("  IMPORTANTE: cerrar Serial Monitor y correr:");
  Serial.println("  python capturar_audio.py");
  Serial.println();
  Serial.println("  Si ya corres el script, enviame '5' desde el script.");
  Serial.println("  Esperando 2 segundos... luego GRABA.");
  delay(2000);

  if (oled_listo) oled_texto("GRABANDO...", "10 segundos", "Habla ahora!");

#if USAR_RGB
  pixel.setPixelColor(0, pixel.Color(255, 0, 0)); // rojo = grabando
  pixel.show();
#endif

  // Encabezado que Python detecta
  Serial.printf("AUDIO_START:%d\n", TOTAL_BYTES);

  // 125us entre muestras @ 8kHz
  const uint32_t intervalo_us = 1000000UL / SAMPLE_RATE;

  // Estado de los filtros biquad (todos en 0 = silencio inicial)
  float hx1=0,hx2=0, hy1=0,hy2=0;   // HPF 80Hz state
  float lx1=0,lx2=0, ly1=0,ly2=0;   // LPF 3400Hz state

  for (int i = 0; i < TOTAL_MUESTRAS; i++) {
    uint32_t t0 = micros();

    // Oversampling 4x: promedia 4 lecturas ADC -> reduce ruido en sqrt(4) = 2x (-6dB)
    int32_t suma_adc = 0;
    for (int j = 0; j < OVERSAMPLE; j++) suma_adc += analogRead(MIC_OUT_PIN);
    float x = (float)suma_adc / OVERSAMPLE - 2048.0f;  // centrado en 0, rango +-2048

    // Biquad HPF 80Hz (Direct Form I): elimina DC bias y rumble
    // Formula: y[n] = B0*x[n] + B1*x[n-1] + B2*x[n-2] - A1*y[n-1] - A2*y[n-2]
    float hp = HPF_B0*x  + HPF_B1*hx1 + HPF_B2*hx2 - HPF_A1*hy1 - HPF_A2*hy2;
    hx2=hx1; hx1=x;   hy2=hy1; hy1=hp;

    // Biquad LPF 3400Hz: limita a banda de voz, corta ruido ADC de alta frecuencia
    float lp = LPF_B0*hp + LPF_B1*lx1 + LPF_B2*lx2 - LPF_A1*ly1 - LPF_A2*ly2;
    lx2=lx1; lx1=hp;  ly2=ly1; ly1=lp;

    // Escalar a 16-bit con ganancia (lp en +-2048; x16 llena 16-bit; xGANANCIA_SW sube volumen)
    int32_t muestra32 = (int32_t)(lp * (GANANCIA_SW * 16.0f));
    if (muestra32 >  32767) muestra32 =  32767;
    if (muestra32 < -32768) muestra32 = -32768;
    int16_t muestra = (int16_t)muestra32;

    // Enviar 2 bytes little-endian (formato WAV/PCM estandar)
    Serial.write((uint8_t)(muestra & 0xFF));
    Serial.write((uint8_t)((muestra >> 8) & 0xFF));

    // Esperar para mantener 8kHz exacto
    while (micros() - t0 < intervalo_us);
  }

  Serial.print("\nAUDIO_END\n");

#if USAR_RGB
  pixel.setPixelColor(0, pixel.Color(0, 255, 0)); // verde = listo
  pixel.show();
  delay(1000);
  pixel.clear(); pixel.show();
#endif

  if (oled_listo) oled_texto("Grabacion OK", "Ver grabacion.wav", "");
  Serial.println("Grabacion completa.");
}

// =============================================================================
//  LOOP nivel microfono (VU meter continuo)
// =============================================================================
void mic_nivel_loop() {
  int suma = 0, pico = 0;
  for (int i = 0; i < 8; i++) {
    int v = analogRead(MIC_OUT_PIN);
    suma += v;
    int amp = abs(v - 2048);
    if (amp > pico) pico = amp;
  }
  int val = suma / 8;
  float voltios = val * 3.3f / 4095.0f;
  int amplitud = abs(val - 2048);
  int nivel = constrain(map(amplitud, 0, 1500, 0, 40), 0, 40);

  char barra[41];
  for (int i = 0; i < 40; i++)
    barra[i] = (i < nivel) ? ((i < 15) ? '=' : (i < 30) ? '*' : '!') : '-';
  barra[40] = '\0';

  Serial.printf("  %4d | %.2fV   | [%s]", val, voltios, barra);
  if (amplitud < 30) Serial.print("  silencio");
  Serial.println();

  if (oled_listo) {
    oled.clearDisplay();
    oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 0); oled.print("MAX4466  GPIO4");
    char buf[22]; sprintf(buf, "ADC:%4d  %.2fV", val, voltios);
    oled.setCursor(0, 11); oled.print(buf);
    int w = constrain(map(amplitud, 0, 1500, 0, 128), 0, 128);
    oled.fillRect(0, 24, w, 7, SSD1306_WHITE);
    oled.display();
  }

#if USAR_RGB
  uint8_t br = (uint8_t)constrain(map(amplitud, 0, 1500, 0, 255), 0, 255);
  pixel.setPixelColor(0, pixel.Color(br, 0, br / 2));
  pixel.show();
#endif

  delay(50);
}

// =============================================================================
//  Detener microfono
// =============================================================================
void mic_detener() {
  mic_listo = false;
#if USAR_RGB
  pixel.clear(); pixel.show();
#endif
}

// =============================================================================
//  TEST 6 — Reconocimiento Whisper con PTT por teclado (desde Python terminal)
//
//  Flujo:
//    1. Corre test_whisper.py en PC (carga Whisper ~20s, luego envia ENTER)
//    2. OLED muestra "ENTER = grabar"
//    3. El script Python pregunta "Presiona ENTER para GRABAR" → usuario presiona
//    4. Python envia 'R' al ESP32 → empieza a grabar
//    5. El script pregunta "Presiona ENTER para PARAR" → usuario presiona
//    6. Python envia 'T' al ESP32 → para la grabacion
//    7. Whisper procesa y devuelve DETECTED:<palabra>
// =============================================================================
void test_6_whisper() {
  Serial.println("--- TEST 6: Reconocimiento Whisper (PTT por teclado) ---");
  Serial.println("1. Abre otra terminal: cd firmware/test_hardware");
  Serial.println("   python test_whisper.py");
  Serial.println("2. Sigue las instrucciones en la terminal Python.");
  Serial.println("Esperando ENTER del script Python...");
  oled_texto("TEST 6 WHISPER", "Corre en PC:", "test_whisper.py");

  // Esperar ENTER del script (senal de que Whisper ya cargo y esta listo)
  while (!Serial.available()) delay(10);
  while (Serial.available()) Serial.read();

  // ── Esperar 'R' del script Python (Record = empezar) ─────────────────────
  oled_texto("ENTER=grabar", "Presiona ENTER", "en la terminal PC");
  Serial.println("  READY_TO_RECORD");  // senal al script Python

  char cmd = 0;
  while (cmd != 'R' && cmd != 'r') {
    if (Serial.available()) cmd = (char)Serial.read();
    delay(5);
  }
  while (Serial.available()) Serial.read();  // flush

  // ── Reservar buffer en PSRAM ─────────────────────────────────────────────
  // 10s x 8kHz x 2bytes = 160KB — cabe facilmente en PSRAM del N16R8
  const int MAX_SEG      = 10;
  const int MAX_MUESTRAS = SAMPLE_RATE * MAX_SEG;
  const size_t MAX_BUF   = (size_t)MAX_MUESTRAS * 2;

  int16_t* audio_buf = (int16_t*)ps_malloc(MAX_BUF);
  if (!audio_buf) {
    audio_buf = (int16_t*)malloc(MAX_BUF);
    if (!audio_buf) {
      Serial.println("  [ERROR] Sin memoria. Habilita PSRAM: OPI PSRAM en board settings.");
      oled_texto("ERROR MEMORIA", "Habilita PSRAM", "en board settings");
      return;
    }
    Serial.println("  [WARN] Sin PSRAM — usando SRAM");
  }

  // ── Grabar: loop hasta recibir 'T' (sTop) o llegar al limite ─────────────
#if USAR_RGB
  pixel.setPixelColor(0, pixel.Color(255, 0, 0));   // rojo = grabando
  pixel.show();
#endif
  oled_texto("GRABANDO...", "Habla ahora", "ENTER para parar");
  Serial.println("  RECORDING_START");   // senal al script Python

  const uint32_t intervalo_us = 1000000UL / SAMPLE_RATE;
  float hx1=0,hx2=0, hy1=0,hy2=0;
  float lx1=0,lx2=0, ly1=0,ly2=0;
  int muestras_grabadas = 0;

  while (muestras_grabadas < MAX_MUESTRAS) {
    uint32_t t0 = micros();

    // Oversampling 4x + filtros biquad (mismo pipeline que Test 5)
    int32_t suma_adc = 0;
    for (int j = 0; j < OVERSAMPLE; j++) suma_adc += analogRead(MIC_OUT_PIN);
    float x = (float)suma_adc / OVERSAMPLE - 2048.0f;

    float hp = HPF_B0*x  + HPF_B1*hx1 + HPF_B2*hx2 - HPF_A1*hy1 - HPF_A2*hy2;
    hx2=hx1; hx1=x;   hy2=hy1; hy1=hp;

    float lp = LPF_B0*hp + LPF_B1*lx1 + LPF_B2*lx2 - LPF_A1*ly1 - LPF_A2*ly2;
    lx2=lx1; lx1=hp;  ly2=ly1; ly1=lp;

    int32_t m32 = (int32_t)(lp * (GANANCIA_SW * 16.0f));
    if (m32 >  32767) m32 =  32767;
    if (m32 < -32768) m32 = -32768;
    audio_buf[muestras_grabadas++] = (int16_t)m32;

    // Revisar si Python envio 'T' (stop) — tarda ~1us, no afecta el timing
    if (Serial.available()) {
      char c = (char)Serial.peek();
      if (c == 'T' || c == 't') { Serial.read(); break; }
      Serial.read();  // descartar cualquier otro byte
    }

    while (micros() - t0 < intervalo_us);
  }

  // ── Validar duracion minima ───────────────────────────────────────────────
  int bytes_grabados = muestras_grabadas * 2;
  float duracion_seg = (float)muestras_grabadas / SAMPLE_RATE;
  bool lleno         = (muestras_grabadas >= MAX_MUESTRAS);

  Serial.printf("  Grabacion: %.2fs (%d bytes)%s\n",
                duracion_seg, bytes_grabados, lleno ? " [LIMITE 10s]" : "");

  if (muestras_grabadas < (SAMPLE_RATE / 4)) {
    free(audio_buf);
    oled_texto("MUY CORTO", "Habla mas tiempo", "e intenta de nuevo");
    Serial.println("  RECORDING_TOO_SHORT");
#if USAR_RGB
    pixel.clear(); pixel.show();
#endif
    return;
  }

  // ── Enviar audio al PC ────────────────────────────────────────────────────
#if USAR_RGB
  pixel.setPixelColor(0, pixel.Color(0, 0, 255));   // azul = procesando
  pixel.show();
#endif
  char oled_dur[22];
  sprintf(oled_dur, "Dur: %.1fs  env...", duracion_seg);
  oled_texto("Enviando...", oled_dur, "espera en PC");

  Serial.printf("AUDIO_START:%d\n", bytes_grabados);
  Serial.write((const uint8_t*)audio_buf, (size_t)bytes_grabados);
  Serial.print("\nAUDIO_END\n");

  free(audio_buf);

  // Timeout mas largo para modelo small (~20-30s en CPU)
  oled_texto("Procesando...", "Whisper small", "espera ~30s");
  Serial.println("  Audio enviado. Whisper procesando (modelo small ~20-30s)...");

  // ── Esperar DETECTED:<palabra> ────────────────────────────────────────────
  String buf_linea = "";
  unsigned long t_limite = millis() + 60000UL;  // 60s timeout para modelo small
  bool recibido = false;

  while (millis() < t_limite) {
    if (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n') {
        if (buf_linea.startsWith("DETECTED:")) {
          String palabra = buf_linea.substring(9);
          palabra.trim();
          Serial.printf("  Whisper detecto: %s\n", palabra.c_str());

          oled.clearDisplay();
          oled.setTextColor(SSD1306_WHITE);
          oled.setCursor(0, 0);
          oled.setTextSize(1); oled.print("DETECTADO:");
          oled.setCursor(0, 12);
          oled.setTextSize(2); oled.print(palabra.substring(0, 8));
          oled.setTextSize(1);
          oled.display();

#if USAR_RGB
          bool correcto = (palabra != "DESCONOCIDO");
          pixel.setPixelColor(0, correcto
            ? pixel.Color(0, 255, 0)      // verde = detectado
            : pixel.Color(255, 100, 0));  // naranja = no reconocido
          pixel.show();
          delay(4000);
          pixel.clear(); pixel.show();
#endif
          recibido = true;
          break;
        }
        buf_linea = "";
      } else if (c != '\r') {
        buf_linea += c;
      }
    }
  }

  if (!recibido) {
    oled_texto("TIMEOUT 60s", "Sin respuesta", "del PC");
    Serial.println("  [WARN] No llego DETECTED: en 60 segundos.");
#if USAR_RGB
    pixel.setPixelColor(0, pixel.Color(255, 0, 0));
    pixel.show(); delay(1000); pixel.clear(); pixel.show();
#endif
  }
}

// =============================================================================
//  UTILIDAD — 3 lineas en OLED
// =============================================================================
void oled_texto(const char* l1, const char* l2, const char* l3) {
  if (!oled_listo) return;
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0,  0); oled.print(l1);
  oled.setCursor(0, 11); oled.print(l2);
  oled.setCursor(0, 22); oled.print(l3);
  oled.display();
}
