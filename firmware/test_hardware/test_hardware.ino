#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>

// ====== Cableado confirmado por el usuario ======
// MIC I2S
#define MIC_WS   15   // WS / LRCLK
#define MIC_SCK  16   // SCK / BCLK
#define MIC_SD   17   // SD / DOUT del mic
// OLED I2C
#define OLED_SDA 10
#define OLED_SCL 11
#define OLED_ADDR 0x3C
#define OLED_W 128
#define OLED_H 32

// ====== Config ======
#define SERIAL_BAUD 115200
#define SAMPLE_RATE 16000
#define DMA_BUF_LEN 256
#define DMA_BUF_CNT 8

static Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1);
static bool oledOk = false;
static bool micOk = false;
static bool micStreamOn = false;
static i2s_channel_fmt_t micFmt = I2S_CHANNEL_FMT_ONLY_LEFT; // L/R del mic conectado a GND
static int micShift = 8;
static int32_t micBuf[DMA_BUF_LEN];
static unsigned long lastMicPrintMs = 0;

static void printMenu() {
  Serial.println();
  Serial.println("=== TEST HARDWARE (MIC + OLED) ===");
  Serial.println("h  -> menu");
  Serial.println("s  -> estado");
  Serial.println("o  -> test OLED");
  Serial.println("c  -> limpiar OLED");
  Serial.println("l  -> MIC canal LEFT");
  Serial.println("r  -> MIC canal RIGHT");
  Serial.println("8/1/4/6 -> shift 8/11/14/16");
  Serial.println("m  -> medir MIC una vez");
  Serial.println("v  -> toggle stream MIC (cada 250ms)");
  Serial.println("t  -> RAWTEST (12 muestras crudas)");
}

static void oledShow(const char* l1, const char* l2 = "", const char* l3 = "") {
  if (!oledOk) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(l1);
  display.setCursor(0, 11);
  display.println(l2);
  display.setCursor(0, 22);
  display.println(l3);
  display.display();
}

static bool initOled() {
  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setTimeOut(500);
  Wire.beginTransmission(OLED_ADDR);
  if (Wire.endTransmission() != 0) return false;
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) return false;
  oledShow("OLED OK", "SDA=10 SCL=11", "");
  return true;
}

static bool initMic() {
  i2s_config_t cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = micFmt,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = DMA_BUF_CNT,
    .dma_buf_len = DMA_BUF_LEN,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pins = {
    .mck_io_num = I2S_PIN_NO_CHANGE,
    .bck_io_num = MIC_SCK,
    .ws_io_num = MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = MIC_SD
  };

  if (i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL) != ESP_OK) return false;
  if (i2s_set_pin(I2S_NUM_0, &pins) != ESP_OK) return false;
  i2s_zero_dma_buffer(I2S_NUM_0);
  i2s_set_clk(I2S_NUM_0, SAMPLE_RATE, I2S_BITS_PER_SAMPLE_32BIT, I2S_CHANNEL_MONO);
  delay(80);
  return true;
}

static void reinitMic() {
  i2s_driver_uninstall(I2S_NUM_0);
  micOk = initMic();
}

static void measureMic(float* outRms, int* outPeak, int* outNz) {
  *outRms = 0.0f;
  *outPeak = 0;
  *outNz = 0;
  if (!micOk) return;

  size_t bytesRead = 0;
  if (i2s_read(I2S_NUM_0, micBuf, sizeof(micBuf), &bytesRead, pdMS_TO_TICKS(80)) != ESP_OK || bytesRead == 0) return;

  int n = (int)(bytesRead / sizeof(int32_t));
  float sumSq = 0.0f;
  int peak = 0;
  int nz = 0;

  for (int i = 0; i < n; i++) {
    int32_t v = micBuf[i] >> micShift;
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    if (v != 0) nz++;
    int a = v >= 0 ? v : -v;
    if (a > peak) peak = a;
    sumSq += (float)v * (float)v;
  }

  *outRms = n > 0 ? sqrtf(sumSq / (float)n) : 0.0f;
  *outPeak = peak;
  *outNz = nz;
}

static void printMicLevelOnce() {
  float rms = 0.0f;
  int peak = 0;
  int nz = 0;
  measureMic(&rms, &peak, &nz);
  Serial.printf("MICLVL:rms=%.1f peak=%d nz=%d fmt=%s shift=%d pins(W=%d S=%d D=%d)\n",
                rms, peak, nz,
                micFmt == I2S_CHANNEL_FMT_ONLY_RIGHT ? "R" : "L",
                micShift, MIC_WS, MIC_SCK, MIC_SD);
}

static void rawTest() {
  if (!micOk) {
    Serial.println("RAWTEST:MIC_FAIL");
    return;
  }
  size_t bytesRead = 0;
  if (i2s_read(I2S_NUM_0, micBuf, sizeof(micBuf), &bytesRead, pdMS_TO_TICKS(120)) != ESP_OK || bytesRead == 0) {
    Serial.println("RAWTEST:NO_DATA");
    return;
  }
  int n = (int)(bytesRead / sizeof(int32_t));
  Serial.printf("RAWTEST:n=%d fmt=%s shift=%d\n", n, micFmt == I2S_CHANNEL_FMT_ONLY_RIGHT ? "R" : "L", micShift);
  for (int i = 0; i < n && i < 12; i++) {
    int32_t v = micBuf[i] >> micShift;
    Serial.printf("  %02d raw=0x%08X v=%ld\n", i, (uint32_t)micBuf[i], (long)v);
  }
}

static void printStatus() {
  Serial.printf("ESTADO: OLED=%s MIC=%s fmt=%s shift=%d stream=%s\n",
                oledOk ? "OK" : "FAIL",
                micOk ? "OK" : "FAIL",
                micFmt == I2S_CHANNEL_FMT_ONLY_RIGHT ? "R" : "L",
                micShift,
                micStreamOn ? "ON" : "OFF");
}

static void handleCmd(char c) {
  if (c == 'h' || c == 'H') {
    printMenu();
  } else if (c == 's' || c == 'S') {
    printStatus();
  } else if (c == 'o' || c == 'O') {
    oledShow("TEST OLED", "Si lees esto,", "funciona");
    Serial.println("OLED_TEST:OK");
  } else if (c == 'c' || c == 'C') {
    oledShow("", "", "");
    Serial.println("OLED_CLEAR:OK");
  } else if (c == 'l' || c == 'L') {
    micFmt = I2S_CHANNEL_FMT_ONLY_LEFT;
    reinitMic();
    Serial.println("MIC_FMT:L");
  } else if (c == 'r' || c == 'R') {
    micFmt = I2S_CHANNEL_FMT_ONLY_RIGHT;
    reinitMic();
    Serial.println("MIC_FMT:R");
  } else if (c == '8') {
    micShift = 8;
    Serial.println("MIC_SHIFT:8");
  } else if (c == '1') {
    micShift = 11;
    Serial.println("MIC_SHIFT:11");
  } else if (c == '4') {
    micShift = 14;
    Serial.println("MIC_SHIFT:14");
  } else if (c == '6') {
    micShift = 16;
    Serial.println("MIC_SHIFT:16");
  } else if (c == 'm' || c == 'M') {
    printMicLevelOnce();
  } else if (c == 'v' || c == 'V') {
    micStreamOn = !micStreamOn;
    Serial.printf("MIC_STREAM:%s\n", micStreamOn ? "ON" : "OFF");
  } else if (c == 't' || c == 'T') {
    rawTest();
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.setTimeout(20);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);

  oledOk = initOled();
  micOk = initMic();

  Serial.println();
  Serial.println("INICIO TEST MIC+OLED");
  Serial.println(oledOk ? "OLED_OK" : "OLED_FAIL");
  Serial.println(micOk ? "MIC_OK" : "MIC_FAIL");
  Serial.println("I2S: WS=15 SCK=16 SD=17");
  Serial.println("I2C: SDA=10 SCL=11");
  printMenu();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') continue;
    handleCmd(c);
  }

  if (micStreamOn) {
    unsigned long now = millis();
    if (now - lastMicPrintMs >= 250) {
      lastMicPrintMs = now;
      printMicLevelOnce();
    }
  }
}
