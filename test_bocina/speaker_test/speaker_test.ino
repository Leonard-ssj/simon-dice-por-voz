/**
 * @file speaker_test.ino
 * @brief Test de bocina MAX98357A — ESP32-S3-N16R8
 *        Sin dependencias externas, compila solo con el SDK de ESP32.
 *
 * CONEXIONES MAX98357A — LADO IZQUIERDO DevKitC-1:
 *
 *   Pos  Pin      MAX98357A
 *   1    3V3  ──► VDD
 *   2    GND  ──► GND
 *   2    GND  ──► SD   (mismo GND = siempre encendido)
 *   8    GPIO15 ─► BCLK  ★
 *   9    GPIO16 ─► LRC   ★
 *   10   GPIO17 ─► DIN   ★
 *        GAIN →   libre (9dB por defecto)
 *        OUT+ ──► Bocina (+)
 *        OUT- ──► Bocina (-)
 *
 * MENU:
 *   1-9  Tonos y melodias
 *   A    Cancion con voz sintetizada — Himno de la Alegria
 *   B    Escribe texto en espanol → bocina lo dice (offline, sin WiFi)
 *   C    Texto → voz humana mexicana via servidor Piper TTS (WiFi)
 *   D    Reproduce frases del vocabulario desde LittleFS (sin WiFi)
 *   0    Silencio
 */

#include <Arduino.h>
#include <driver/i2s_std.h>
#include <math.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include "narradora.h"

// ─── PINES MAX98357A — LADO IZQUIERDO ─────────────────
#define I2S_BCLK_PIN  15
#define I2S_LRC_PIN   16
#define I2S_DOUT_PIN  17
// ──────────────────────────────────────────────────────

// ─── CONFIGURACION WIFI + SERVIDOR TTS ────────────────
// Cambia estos valores antes de compilar
#define WIFI_SSID   "INFINITUM5AB2"
#define WIFI_PASS   "CUGWAYqC8C"
#define TTS_HOST    "192.168.1.69"  // IP de tu PC (WiFi)
#define TTS_PORT    8080
#define TTS_RATE    22050           // Hz — coincide con el servidor
// ──────────────────────────────────────────────────────

#define SAMPLE_RATE  44100
#define MAX_AMP      26000

static i2s_chan_handle_t tx_handle = NULL;

// ═══════════════════════════════════════════════════════
//  I2S — init / cierre
// ═══════════════════════════════════════════════════════

bool initI2S() {
  if (tx_handle) return true;
  i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  cc.auto_clear = true;
  if (i2s_new_channel(&cc, &tx_handle, NULL) != ESP_OK) return false;

  i2s_std_config_t sc = {
    .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = (gpio_num_t)I2S_BCLK_PIN,
      .ws   = (gpio_num_t)I2S_LRC_PIN,
      .dout = (gpio_num_t)I2S_DOUT_PIN,
      .din  = I2S_GPIO_UNUSED,
      .invert_flags = {false, false, false},
    },
  };
  if (i2s_channel_init_std_mode(tx_handle, &sc) != ESP_OK) return false;
  if (i2s_channel_enable(tx_handle) != ESP_OK) return false;
  return true;
}

// Reinicializa I2S con cualquier sample rate (para TTS del servidor)
bool reinitI2S(uint32_t rate) {
  if (tx_handle) {
    i2s_channel_disable(tx_handle);
    i2s_del_channel(tx_handle);
    tx_handle = NULL;
  }
  i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  cc.auto_clear = true;
  if (i2s_new_channel(&cc, &tx_handle, NULL) != ESP_OK) return false;

  i2s_std_config_t sc = {
    .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(rate),
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = (gpio_num_t)I2S_BCLK_PIN,
      .ws   = (gpio_num_t)I2S_LRC_PIN,
      .dout = (gpio_num_t)I2S_DOUT_PIN,
      .din  = I2S_GPIO_UNUSED,
      .invert_flags = {false, false, false},
    },
  };
  if (i2s_channel_init_std_mode(tx_handle, &sc) != ESP_OK) return false;
  if (i2s_channel_enable(tx_handle) != ESP_OK) return false;
  return true;
}

// ═══════════════════════════════════════════════════════
//  PRIMITIVAS BASICAS
// ═══════════════════════════════════════════════════════

void writeI2S(int16_t* buf, int samples) {
  size_t wr;
  i2s_channel_write(tx_handle, buf, samples * 2, &wr, portMAX_DELAY);
}

void silence(int ms) {
  int total = SAMPLE_RATE * ms / 1000;
  int16_t buf[256] = {};
  for (int done = 0; done < total; done += 256)
    writeI2S(buf, min(256, total - done));
}

// Tono seno con fade in/out
void tone_(float freq, int ms, float amp = MAX_AMP) {
  int total = SAMPLE_RATE * ms / 1000;
  int fade  = SAMPLE_RATE * 12 / 1000;
  const int C = 512;
  int16_t buf[C];
  for (int done = 0; done < total; ) {
    int b = min(C, total - done);
    for (int i = 0; i < b; i++) {
      int s = done + i;
      float env = 1.0f;
      if (s < fade)           env = (float)s / fade;
      if (s > total - fade)   env = (float)(total - s) / fade;
      buf[i] = (int16_t)(amp * env * sinf(2*M_PI*freq*(float)s/SAMPLE_RATE));
    }
    writeI2S(buf, b);
    done += b;
  }
}

void sweep(float f0, float f1, int ms) {
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 512;
  int16_t buf[C];
  float ph = 0;
  for (int done = 0; done < total; ) {
    int b = min(C, total - done);
    for (int i = 0; i < b; i++) {
      float prog = (float)(done + i) / total;
      ph += 2*M_PI*(f0 + (f1-f0)*prog) / SAMPLE_RATE;
      if (ph > 2*M_PI) ph -= 2*M_PI;
      buf[i] = (int16_t)(MAX_AMP * sinf(ph));
    }
    writeI2S(buf, b);
    done += b;
  }
}

// ═══════════════════════════════════════════════════════
//  TESTS 1-9
// ═══════════════════════════════════════════════════════

void test1() { tone_(440, 1000); }

void test2() {
  float n[]={261.6f,293.7f,329.6f,349.2f,392.0f,440.0f,493.9f,523.3f};
  const char* nm[]={"Do","Re","Mi","Fa","Sol","La","Si","Do"};
  for (int i=0;i<8;i++) { Serial.printf("  %s\n",nm[i]); tone_(n[i],380); silence(70); }
}

void test3() {
  sweep(100,4000,2000); silence(200); sweep(4000,100,2000);
}

void test4() { tone_(880,80); silence(50); tone_(1320,130); }

void test5() {
  for (int i=0;i<6;i++) { tone_(1000,150); silence(90); tone_(1400,150); silence(90); }
}

void test6() {
  float n[]={261.6f,261.6f,392.0f,392.0f,440.0f,440.0f,392.0f,
             349.2f,349.2f,329.6f,329.6f,293.7f,293.7f,261.6f,
             392.0f,392.0f,349.2f,349.2f,329.6f,329.6f,293.7f,
             392.0f,392.0f,349.2f,349.2f,329.6f,329.6f,293.7f,
             261.6f,261.6f,392.0f,392.0f,440.0f,440.0f,392.0f,
             349.2f,349.2f,329.6f,329.6f,293.7f,293.7f,261.6f};
  int d[]={300,300,300,300,300,300,600,300,300,300,300,300,300,600,
           300,300,300,300,300,300,600,300,300,300,300,300,300,600,
           300,300,300,300,300,300,600,300,300,300,300,300,300,600};
  for (int i=0;i<42;i++) { tone_(n[i], d[i]-40, MAX_AMP*0.8f); silence(40); }
}

void test7() {
  for (int v=3000; v<=MAX_AMP; v+=3000) {
    Serial.printf("  amp %d/%d\n", v, MAX_AMP);
    tone_(440, 300, v); silence(120);
  }
}

void test8() { tone_(100, 2000); }
void test9() { tone_(2000, 1000); }

// ═══════════════════════════════════════════════════════
//  OPCION A — HIMNO DE LA ALEGRIA CON VOZ CANTADA
//
//  Cada nota es una silaba "La" sintetizada con:
//  - Fuente glotal: 6 armonicos (simula cuerdas vocales)
//  - Formantes vocales A: F1=800Hz F2=1200Hz F3=2500Hz
//  - Vibrato 5.2Hz ±1.2%
//  - Chorus: 2 osciladores ligeramente desafinados
//  - ADSR: ataque 35ms / release 55ms
// ═══════════════════════════════════════════════════════

void voiceNote(float pitch, int ms) {
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 256;
  int16_t buf[C];
  float p2 = pitch * 1.009f; // segundo oscilador (chorus)
  int att = SAMPLE_RATE * 35 / 1000;
  int rel = SAMPLE_RATE * 55 / 1000;

  for (int done = 0; done < total; ) {
    int b = min(C, total - done);
    for (int i = 0; i < b; i++) {
      int s = done + i;
      float t = (float)s / SAMPLE_RATE;

      float env = 1.0f;
      if (s < att)           env = (float)s / att;
      else if (s > total-rel) env = (float)(total-s) / rel;

      float vib = 1.0f + 0.012f * sinf(2*M_PI*5.2f*t);

      // Fuente glotal armonicos
      float a[]={1.0f,0.55f,0.28f,0.14f,0.07f,0.03f};
      float s1=0, s2=0;
      for (int h=1;h<=6;h++) {
        s1 += a[h-1]*sinf(2*M_PI*pitch*vib*h*t);
        s2 += a[h-1]*sinf(2*M_PI*p2*vib*h*t);
      }
      // Resonancias formantes vocal 'a'
      float fm = 0.55f*sinf(2*M_PI*800*t)
               + 0.35f*sinf(2*M_PI*1200*t)
               + 0.10f*sinf(2*M_PI*2500*t);

      float smp = ((s1*0.6f+s2*0.4f)*0.62f + fm*0.38f) * env;
      buf[i] = (int16_t)(MAX_AMP * 0.78f * smp);
    }
    writeI2S(buf, b);
    done += b;
  }
}

// Consonante L de transicion
void consonL(float pitch, int ms) {
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 256; int16_t buf[C];
  for (int done=0; done<total; ) {
    int b = min(C, total-done);
    for (int i=0; i<b; i++) {
      float t = (float)(done+i)/SAMPLE_RATE;
      float env = (float)(done+i)/total;
      float src = sinf(2*M_PI*pitch*t)+0.4f*sinf(2*M_PI*pitch*2*t);
      float fl  = 0.7f*sinf(2*M_PI*380*t)+0.3f*sinf(2*M_PI*1100*t);
      buf[i] = (int16_t)(MAX_AMP*0.5f*env*(src*0.6f+fl*0.4f));
    }
    writeI2S(buf, b); done += b;
  }
}

void silabaLa(float pitch, int ms) {
  consonL(pitch, ms*20/100);
  voiceNote(pitch, ms*80/100);
}

void testA_cancion() {
  Serial.println(">> Himno de la Alegria — La la la...");
  float n[] = {329.6f,329.6f,349.2f,392.0f,392.0f,349.2f,329.6f,293.7f,
               261.6f,261.6f,293.7f,329.6f,329.6f,293.7f,293.7f,
               329.6f,329.6f,349.2f,392.0f,392.0f,349.2f,329.6f,293.7f,
               261.6f,261.6f,293.7f,329.6f,293.7f,261.6f,261.6f};
  int  d[] = {370,370,370,370,370,370,370,370,370,370,370,370,550,370,780,
              370,370,370,370,370,370,370,370,370,370,370,370,370,780,780};
  int cnt = sizeof(n)/sizeof(n[0]);
  for (int i=0; i<cnt; i++) {
    Serial.printf("  La %d/%d  %.0fHz\n", i+1, cnt, n[i]);
    silabaLa(n[i], d[i]-50);
    silence(50);
  }
}

// ═══════════════════════════════════════════════════════
//  OPCION B — TEXTO EN ESPAÑOL → VOZ SINTETIZADA
//
//  Sintesis de formantes por fonema. El español es fonetico:
//  cada letra suena igual sin importar el contexto,
//  lo que hace la sintesis letra-a-letra bastante inteligible.
//
//  Vocales:  formantes F1/F2 reales del español peninsular
//  Sonoras:  armonicos con coloracion espectral
//  Plosivas: silencio + explosion de energia
//  Fricativas: ruido blanco filtrado
//
//  100% offline. Sin WiFi. Sin API key.
// ═══════════════════════════════════════════════════════

// Genera ruido pseudo-aleatorio filtrado (fricativas: s, f, j)
void noisePhoneme(int ms, float hiFreq, float amp) {
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 256; int16_t buf[C];
  float prev = 0;
  for (int done=0; done<total; ) {
    int b = min(C, total-done);
    for (int i=0; i<b; i++) {
      int s = done+i;
      float env = 1.0f;
      int fd = SAMPLE_RATE*12/1000;
      if (s < fd)        env = (float)s/fd;
      if (s > total-fd)  env = (float)(total-s)/fd;
      // Ruido + filtro paso-alto simple
      float noise = (float)(random(-10000, 10000)) / 10000.0f;
      float hi = noise - prev; prev = noise;
      float lo = noise - hi;
      float out = hi * (hiFreq/8000.0f) + lo * (1.0f - hiFreq/8000.0f);
      buf[i] = (int16_t)(amp * env * out);
    }
    writeI2S(buf, b); done += b;
  }
}

// Plosiva: cierre (silencio) + explosion
void plosive(float freq, int ms) {
  silence(22);
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 256; int16_t buf[C];
  for (int done=0; done<total; ) {
    int b = min(C, total-done);
    for (int i=0; i<b; i++) {
      float env = 1.0f - (float)(done+i)/total;
      env = env * env; // decaimiento cuadratico
      float t = (float)(done+i)/SAMPLE_RATE;
      buf[i] = (int16_t)(MAX_AMP*0.65f*env*sinf(2*M_PI*freq*t));
    }
    writeI2S(buf, b); done += b;
  }
}

// Vocal con formantes F1/F2
void vocalFormant(float F1, float F2, int ms, float pitch=185.0f) {
  int total = SAMPLE_RATE * ms / 1000;
  const int C = 256; int16_t buf[C];
  int att = SAMPLE_RATE*18/1000;
  int rel = SAMPLE_RATE*22/1000;
  float p2 = pitch * 1.007f;
  float a[]={1.0f,0.5f,0.25f,0.12f,0.06f};

  for (int done=0; done<total; ) {
    int b = min(C, total-done);
    for (int i=0; i<b; i++) {
      int s = done+i;
      float t = (float)s/SAMPLE_RATE;
      float env=1.0f;
      if (s<att)           env=(float)s/att;
      else if(s>total-rel) env=(float)(total-s)/rel;

      float vib = 1.0f + 0.010f*sinf(2*M_PI*5.0f*t);
      float src=0, src2=0;
      for (int h=1;h<=5;h++) {
        src  += a[h-1]*sinf(2*M_PI*pitch*vib*h*t);
        src2 += a[h-1]*sinf(2*M_PI*p2*vib*h*t);
      }
      float fm = 0.60f*sinf(2*M_PI*F1*t) + 0.40f*sinf(2*M_PI*F2*t);
      float smp = ((src*0.55f+src2*0.45f)*0.65f + fm*0.35f) * env;
      buf[i] = (int16_t)(MAX_AMP*0.80f*smp);
    }
    writeI2S(buf, b); done += b;
  }
}

// Sonora (l, m, n, r) — formantes mas bajos
void sonora(float F1, float F2, int ms, float pitch=185.0f) {
  vocalFormant(F1, F2, ms, pitch); // misma funcion, distintos formantes
}

// Pronunciar una letra del español
void letra(char c, float pitch=185.0f) {
  c = tolower(c);
  int dur = 95; // duracion base por fonema en ms

  // Vocales — formantes reales del español (Quilis 1999)
  if      (c=='a') vocalFormant(800, 1200, dur, pitch);
  else if (c=='e') vocalFormant(500, 1800, dur, pitch);
  else if (c=='i') vocalFormant(300, 2200, dur-10, pitch);
  else if (c=='o') vocalFormant(500,  900, dur, pitch);
  else if (c=='u') vocalFormant(300,  700, dur-10, pitch);

  // Sonoras
  else if (c=='l') sonora(380, 1100, 75, pitch);
  else if (c=='m') sonora(200,  800, 80, pitch);
  else if (c=='n') sonora(250, 1700, 75, pitch);
  else if (c=='r') { // vibrante simple: 2 pulsos
    for (int k=0;k<2;k++) { sonora(350,1100,28,pitch); silence(14); }
  }
  else if (c=='v') sonora(300, 1000, 70, pitch);
  else if (c=='y') sonora(300, 2100, 65, pitch);
  else if (c=='w') sonora(300,  700, 70, pitch);

  // Plosivas
  else if (c=='p') plosive(180, 55);
  else if (c=='b') plosive(140, 65);
  else if (c=='t') plosive(380, 48);
  else if (c=='d') plosive(280, 58);
  else if (c=='c') plosive(480, 52); // ca co cu
  else if (c=='k') plosive(500, 50);
  else if (c=='q') plosive(500, 50); // que qui
  else if (c=='g') plosive(230, 60);

  // Fricativas (ruido filtrado)
  else if (c=='s') noisePhoneme(85, 5500, 14000);
  else if (c=='f') noisePhoneme(80, 4000,  9500);
  else if (c=='j') noisePhoneme(95, 3000, 10000);
  else if (c=='x') noisePhoneme(90, 3500, 10000);
  else if (c=='z') noisePhoneme(75, 4500,  8000);
  else if (c=='h') silence(25);   // h es muda en español

  // Espacios y puntuacion
  else if (c==' ') silence(140);
  else if (c==',') silence(220);
  else if (c=='.'||c=='!'||c=='?') silence(320);

  // Pausa de coarticulacion entre letras
  silence(16);
}

// Manejar UTF-8 de tildes y ñ
void pronunciar(const String& txt, float pitch=185.0f) {
  int i = 0;
  while (i < (int)txt.length()) {
    uint8_t b = (uint8_t)txt[i];
    if (b == 0xC3 && i+1 < (int)txt.length()) {
      uint8_t b2 = (uint8_t)txt[i+1];
      char  eq = 0;
      if (b2==0xA1||b2==0x81) eq='a';
      if (b2==0xA9||b2==0x89) eq='e';
      if (b2==0xAD||b2==0x8D) eq='i';
      if (b2==0xB3||b2==0x93) eq='o';
      if (b2==0xBA||b2==0x9A) eq='u';
      if (b2==0xB1||b2==0x91) eq='n'; // ñ → n aproximado
      if (eq) { letra(eq, pitch); i+=2; continue; }
    }
    letra((char)b, pitch);
    i++;
  }
}

void testB_textoVoz() {
  Serial.println("\n>> TEXTO A VOZ (offline, sin WiFi)");
  Serial.println("   Sintesis de fonemas del espanol");
  Serial.println("   Escribe el texto y presiona ENTER:");
  Serial.print("   > ");

  String texto = "";
  unsigned long t0 = millis();
  while (millis() - t0 < 60000) {
    if (Serial.available()) {
      char c = Serial.read();
      if ((c=='\n'||c=='\r') && texto.length()>0) break;
      if (c!='\n' && c!='\r') { texto += c; Serial.print(c); }
    }
  }
  Serial.println();
  if (texto.length() == 0) { Serial.println("  Sin texto"); return; }

  Serial.printf("  Pronunciando: \"%s\"\n", texto.c_str());
  pronunciar(texto);
  Serial.println("  [OK]");
}

// ═══════════════════════════════════════════════════════
//  OPCION C — VOZ HUMANA via servidor Piper TTS (WiFi)
//
//  El ESP32 envia el texto por HTTP POST al servidor Python.
//  El servidor genera audio PCM 16-bit mono 22050 Hz con
//  Piper TTS (voz es_MX-cortana-high, offline en la PC).
//  El ESP32 recibe y escribe el audio directo al I2S.
//
//  Requisitos en PC:
//    pip install -r requirements.txt
//    python descargar_modelo.py
//    python tts_server.py
// ═══════════════════════════════════════════════════════

void testC_piperTTS() {
  Serial.println("\n>> TTS PIPER — voz humana mexicana (WiFi)");

  // Limpiar buffer UART antes de leer (evita concatenar texto de llamadas anteriores)
  delay(20);
  while (Serial.available()) Serial.read();

  // Leer texto del Serial con timeout 60s
  Serial.println("   Escribe el texto y presiona ENTER:");
  Serial.print("   > ");
  String texto = "";
  unsigned long t0 = millis();
  while (millis() - t0 < 60000) {
    if (Serial.available()) {
      char c = Serial.read();
      if ((c == '\n' || c == '\r') && texto.length() > 0) break;
      if (c != '\n' && c != '\r') { texto += c; Serial.print(c); }
    }
  }
  Serial.println();
  if (texto.length() == 0) { Serial.println("  Sin texto."); return; }

  // Conectar WiFi si no esta conectado
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("  Conectando a '%s'", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
      delay(500); Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("  [FALLO] Sin WiFi — verifica SSID y contrasena"); return;
    }
    Serial.printf("  WiFi OK — IP local: %s\n", WiFi.localIP().toString().c_str());
  }

  // Cambiar I2S a 22050 Hz para el audio del servidor
  Serial.printf("  I2S -> %d Hz... ", TTS_RATE);
  if (!reinitI2S(TTS_RATE)) {
    Serial.println("[FALLO]"); return;
  }
  Serial.println("OK");

  // Peticion HTTP POST al servidor Piper
  String url = String("http://") + TTS_HOST + ":" + TTS_PORT + "/tts";
  Serial.printf("  POST %s\n", url.c_str());

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  http.setTimeout(15000);

  int code = http.POST(texto);
  if (code != 200) {
    Serial.printf("  [HTTP %d] Error — servidor activo? IP correcta?\n", code);
    http.end();
    reinitI2S(SAMPLE_RATE);
    return;
  }

  int totalBytes = http.getSize();
  float duracion = (totalBytes > 0) ? (float)totalBytes / 2.0f / TTS_RATE : -1;
  if (duracion > 0)
    Serial.printf("  Recibiendo %d bytes (%.1f s)...\n", totalBytes, duracion);
  else
    Serial.println("  Recibiendo audio (tamano desconocido)...");

  // Leer stream y escribir directo al I2S
  WiFiClient* stream = http.getStreamPtr();
  const int BUF_SIZE = 2048;
  static uint8_t audioBuf[BUF_SIZE];
  int recibidos = 0;

  while (http.connected() && (totalBytes < 0 || recibidos < totalBytes)) {
    int disponible = stream->available();
    if (disponible > 0) {
      int leer = min(disponible, BUF_SIZE);
      int n = stream->readBytes(audioBuf, leer);
      if (n > 0) {
        size_t escrito;
        i2s_channel_write(tx_handle, audioBuf, n, &escrito, portMAX_DELAY);
        recibidos += n;
      }
    } else {
      delay(1);
    }
  }

  http.end();
  silence(300);
  reinitI2S(SAMPLE_RATE);   // restaurar 44100 Hz para los otros tests
  Serial.printf("  [OK] %d bytes reproducidos\n", recibidos);
}

// ═══════════════════════════════════════════════════════
//  OPCION D — VOCABULARIO DESDE LITTLEFS (sin WiFi)
//
//  reproducir(VozID) lee el .pcm desde flash y lo manda
//  al I2S directamente. Delay ~50ms (solo lectura flash).
//
//  Requiere subir los archivos PCM con:
//    python preparar_datos.py
//    Arduino IDE: Herramientas -> ESP32 LittleFS Data Upload
// ═══════════════════════════════════════════════════════

// Buffer estatico reutilizable para lectura de flash
static uint8_t _pcmBuf[4096];

// Lee un .pcm de LittleFS y lo reproduce por I2S a 22050 Hz
void reproducir(VozID id) {
  if (id >= VOZ_COUNT) {
    Serial.printf("  [VOZ] ID invalido: %d\n", id);
    return;
  }
  const char* ruta = VOZ_ARCHIVOS[id];

  if (!reinitI2S(TTS_RATE)) {
    Serial.printf("  [VOZ] Fallo I2S\n"); return;
  }

  File f = LittleFS.open(ruta, "r");
  if (!f) {
    Serial.printf("  [VOZ] No encontrado: %s\n", ruta);
    reinitI2S(SAMPLE_RATE);
    return;
  }

  size_t escrito;
  while (f.available()) {
    int n = f.read(_pcmBuf, sizeof(_pcmBuf));
    if (n > 0) i2s_channel_write(tx_handle, _pcmBuf, n, &escrito, portMAX_DELAY);
  }
  f.close();
}

// Reproduce y restaura I2S a 44100 Hz para los otros tests
void reproducirYRestaurar(VozID id) {
  reproducir(id);
  silence(150);
  reinitI2S(SAMPLE_RATE);
}

// ── Test interactivo de la opcion D ──────────────────────
void testD_vocabulario() {
  Serial.println("\n>> VOCABULARIO LITTLEFS (sin WiFi)");

  // Verificar que LittleFS tiene archivos
  File root = LittleFS.open("/");
  if (!root || !root.isDirectory()) {
    Serial.println("  [FALLO] LittleFS vacio o no montado.");
    Serial.println("  Sube los archivos con: Herramientas -> ESP32 LittleFS Data Upload");
    return;
  }

  // Contar archivos .pcm
  int count = 0;
  File entry = root.openNextFile();
  while (entry) {
    if (!entry.isDirectory()) count++;
    entry = root.openNextFile();
  }
  Serial.printf("  LittleFS OK — %d archivos\n\n", count);

  // Reproduce todos los archivos en orden de enum (VOZ_ID 0 .. VOZ_COUNT-1)
  for (int i = 0; i < (int)VOZ_COUNT; i++) {
    Serial.printf("  [%2d/%2d] %s\n", i + 1, (int)VOZ_COUNT, VOZ_ARCHIVOS[i]);
    reproducir((VozID)i);
    silence(300);
  }

  reinitI2S(SAMPLE_RATE);
  Serial.println("\n  [OK] Vocabulario completo");
}

// ═══════════════════════════════════════════════════════
//  MENU
// ═══════════════════════════════════════════════════════

void menu() {
  Serial.println("\n╔══════════════════════════════════════════════════╗");
  Serial.println("║   TEST BOCINA MAX98357A — ESP32-S3-N16R8         ║");
  Serial.println("╠══════════════════════════════════════════════════╣");
  Serial.printf ("║  BCLK=GPIO%d   LRC=GPIO%d   DIN=GPIO%d              ║\n",
                 I2S_BCLK_PIN, I2S_LRC_PIN, I2S_DOUT_PIN);
  Serial.println("╠══════════════════════════════════════════════════╣");
  Serial.println("║  1  Tono 440 Hz                                  ║");
  Serial.println("║  2  Escala Do Re Mi Fa Sol La Si Do              ║");
  Serial.println("║  3  Sweep 100 → 4000 Hz                          ║");
  Serial.println("║  4  Bip                                          ║");
  Serial.println("║  5  Alarma                                       ║");
  Serial.println("║  6  Twinkle Twinkle                              ║");
  Serial.println("║  7  Test volumen                                 ║");
  Serial.println("║  8  Tono bajo 100 Hz                             ║");
  Serial.println("║  9  Tono agudo 2000 Hz                           ║");
  Serial.println("╠══════════════════════════════════════════════════╣");
  Serial.println("║  A  Himno de la Alegria (voz cantada)            ║");
  Serial.println("║  B  Escribe texto → bocina lo dice (offline)     ║");
  Serial.println("║  C  Texto → voz humana mexicana (WiFi+Piper)     ║");
  Serial.println("║  D  Vocabulario LittleFS (sin WiFi, instantaneo) ║");
  Serial.println("╠══════════════════════════════════════════════════╣");
  Serial.println("║  0  Silencio                                     ║");
  Serial.println("╚══════════════════════════════════════════════════╝");
  Serial.print("Opcion: ");
}

// ═══════════════════════════════════════════════════════
//  SETUP / LOOP
// ═══════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && millis()-t0 < 5000) delay(10);
  delay(400);

  Serial.printf("\n=== BOCINA TEST — BCLK=%d LRC=%d DIN=%d ===\n",
                I2S_BCLK_PIN, I2S_LRC_PIN, I2S_DOUT_PIN);

  if (!initI2S()) {
    Serial.println("[FATAL] Fallo I2S"); while(true) delay(1000);
  }

  // Montar LittleFS — label "audio" segun partitions.csv
  // (no fatal si falla — solo la opcion D no funciona)
  if (LittleFS.begin(false, "/littlefs", 10, "audio")) {
    Serial.printf("LittleFS OK (%d KB usados / %d KB total)\n",
                  (int)(LittleFS.usedBytes() / 1024),
                  (int)(LittleFS.totalBytes() / 1024));
  } else {
    Serial.println("LittleFS: no montado (sube archivos con python subir_audio.py)");
  }

  // Bip de confirmacion
  tone_(523.3f,180); silence(70); tone_(659.3f,180); silence(70); tone_(783.9f,260);
  Serial.println("Bocina OK");
  menu();
}

unsigned long tMenu = 0;

void loop() {
  if (!Serial.available() && millis()-tMenu > 15000) {
    Serial.println("\n[Esperando opcion...]"); menu(); tMenu = millis();
  }
  if (Serial.available()) {
    char c = Serial.read();
    while (Serial.available()) Serial.read();
    if (c=='\n'||c=='\r') return;
    if (c>='a'&&c<='z') c -= 32;
    Serial.println(c); tMenu = millis();

    switch(c) {
      case '1': test1(); break;
      case '2': test2(); break;
      case '3': test3(); break;
      case '4': test4(); break;
      case '5': test5(); break;
      case '6': test6(); break;
      case '7': test7(); break;
      case '8': test8(); break;
      case '9': test9(); break;
      case 'A': testA_cancion();  break;
      case 'B': testB_textoVoz(); break;
      case 'C': testC_piperTTS();    break;
      case 'D': testD_vocabulario(); break;
      case '0': Serial.println(">> Silencio"); silence(100); break;
      default:  Serial.println("Usa 0-9, A, B, C o D"); break;
    }
    Serial.println("[Listo]"); menu(); tMenu = millis();
  }
}
