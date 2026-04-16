# Bocina ESP32-S3 con voz — Guía completa

## ¿Qué hace este proyecto?

El ESP32-S3-N16R8 reproduce frases de voz humana en español mexicano
a través de un amplificador MAX98357A conectado a una bocina,
sin necesidad de internet ni servidor en tiempo de ejecución.

Los 59 archivos de audio (PCM 22050 Hz, 16-bit mono) se almacenan
en la flash interna del ESP32 usando el sistema de archivos LittleFS.

---

## Hardware necesario

| Componente | Descripción |
|---|---|
| ESP32-S3-N16R8 | 16 MB Flash, 8 MB PSRAM |
| MAX98357A | Amplificador I2S, 3 W |
| Bocina | 4-8 Ω |

### Conexiones MAX98357A → ESP32-S3

```
ESP32-S3        MAX98357A
─────────       ──────────
3V3  ────────►  VDD
GND  ────────►  GND
GND  ────────►  SD   (siempre encendido)
GPIO15 ──────►  BCLK
GPIO16 ──────►  LRC
GPIO17 ──────►  DIN
```

> **Nota VDD:** Usa 3V3, no 5V.
> El MAX98357A acepta 2.5–5.5 V, pero en esta placa
> la señal lógica I2S es de 3.3 V; alimentarlo con 3.3 V
> garantiza niveles compatibles sin divisor de voltaje.

---

## Estructura del proyecto

```
TEST_bocina_esp32s3n16r8/
│
├── speaker_test/              ← Sketch de Arduino IDE
│   ├── speaker_test.ino       ← Código principal del ESP32
│   ├── narradora.h            ← AUTO-GENERADO (enum + rutas + helpers)
│   ├── partitions.csv         ← Tabla de particiones 16 MB
│   └── data/                  ← 59 archivos .pcm para LittleFS
│
├── vocabulario/
│   ├── narradora_frases.md    ← Guión completo (fuente de verdad)
│   └── audio/                 ← 59 archivos .pcm generados
│
├── models/
│   └── es_MX-claude-high.onnx ← Modelo Piper TTS (63 MB)
│
├── descargar_modelo.py        ← Descarga el modelo de HuggingFace
├── generar_audio.py           ← Genera los 59 archivos PCM con Piper
├── generar_header.py          ← Genera narradora.h para el ESP32
├── subir_audio.py             ← Sube los PCM al ESP32 via esptool
├── tts_server.py              ← Servidor Flask TTS en tiempo real (WiFi)
└── requirements.txt           ← pip install -r requirements.txt
```

---

## Cómo funciona el audio

### Flujo completo

```
Texto en narradora_frases.md
        │
        ▼
generar_audio.py   (Piper TTS → PCM 22050 Hz 16-bit mono)
        │
        ├──► vocabulario/audio/*.pcm
        └──► speaker_test/data/*.pcm
                    │
                    ▼
            subir_audio.py   (littlefs-python + esptool)
                    │
                    ▼
            Flash ESP32 @ offset 0x310000 (partición "audio", 12.8 MB)
                    │
                    ▼
            ESP32: LittleFS.open() → I2S → MAX98357A → Bocina
```

### Formato de audio

| Parámetro | Valor |
|---|---|
| Sample rate | 22050 Hz |
| Bits | 16-bit con signo |
| Canales | Mono |
| Endian | Little-endian |
| Formato de archivo | PCM crudo (sin cabecera WAV) |

---

## Vocabulario — 59 archivos

### Frases fijas (16)

| Archivo | Texto |
|---|---|
| `srv_listo.pcm` | "Servidor listo. Abre el panel web y conecta." |
| `simon_listo.pcm` | "Simón Dice listo. Presiona espacio para comenzar." |
| `mira_escucha.pcm` | "Mira y escucha." |
| `color_rojo.pcm` | "rojo" |
| `color_verde.pcm` | "verde" |
| `color_azul.pcm` | "azul" |
| `color_amarillo.pcm` | "amarillo" |
| `turno_primero.pcm` | "Tu turno. Presiona espacio para hablar." |
| `turno.pcm` | "Tu turno." |
| `correcto_turno.pcm` | "Correcto. Tu turno." |
| `correcto.pcm` | "Correcto." |
| `incorrecto.pcm` | "Incorrecto." |
| `di_empieza.pcm` | "Di empieza para intentar de nuevo." |
| `tiempo_agotado.pcm` | "Tiempo agotado." |
| `pausado.pcm` | "Juego pausado." |
| `di_volver.pcm` | "Di empieza para volver a jugar." |

### Colores correctos (13) — N = 2..14

`correctos_02.pcm` … `correctos_14.pcm`
→ "N colores correctos. Tu turno."

### Niveles (14) — N = 2..15

`nivel_02.pcm` … `nivel_15.pcm`
→ "Nivel N."

### Fin del juego (16) — puntuaciones posibles

`fin_0000.pcm` … `fin_1200.pcm`
→ "Fin del juego. Obtuviste N puntos."

| Archivo | Puntos |
|---|---|
| fin_0000.pcm | 0 |
| fin_0010.pcm | 10 |
| fin_0030.pcm | 30 |
| fin_0060.pcm | 60 |
| fin_0100.pcm | 100 |
| fin_0150.pcm | 150 |
| fin_0210.pcm | 210 |
| fin_0280.pcm | 280 |
| fin_0360.pcm | 360 |
| fin_0450.pcm | 450 |
| fin_0550.pcm | 550 |
| fin_0660.pcm | 660 |
| fin_0780.pcm | 780 |
| fin_0910.pcm | 910 |
| fin_1050.pcm | 1050 |
| fin_1200.pcm | 1200 |

---

## Pasos para poner en marcha

### 1. Instalar dependencias Python (una sola vez)

```bash
pip install -r requirements.txt
```

### 2. Descargar el modelo TTS (una sola vez, ~63 MB)

```bash
python descargar_modelo.py
```

Descarga `models/es_MX-claude-high.onnx` y su `.json` desde HuggingFace.

### 3. Generar los archivos de audio (una sola vez, o al cambiar frases)

```bash
python generar_audio.py
```

Genera 59 archivos `.pcm` en `vocabulario/audio/` y `speaker_test/data/`.
Los archivos existentes se saltan automáticamente.

### 4. Generar narradora.h (después de generar audio)

```bash
python generar_header.py
```

Actualiza `speaker_test/narradora.h` con el enum y helpers.

### 5. Configurar Arduino IDE

En **Herramientas** seleccionar:

| Opción | Valor |
|---|---|
| Board | ESP32S3 Dev Module |
| Flash Size | **16MB (128Mb)** |
| Partition Scheme | **Custom** |
| PSRAM | OPI PSRAM |

> **Importante:** `Flash Size` debe ser 16MB. Si está en 4MB, el ESP32
> falla al arrancar con el error "exceeds flash chip size 0x400000".

### 6. Subir el sketch

En Arduino IDE: **Ctrl+U**

El sketch está en `speaker_test/speaker_test.ino`.
El archivo `partitions.csv` en la misma carpeta se usa automáticamente.

### 7. Subir los archivos de audio al ESP32

```bash
python subir_audio.py
```

Crea una imagen LittleFS (~5 MB) y la flashea directamente al ESP32
en el offset `0x310000` usando esptool a 921600 baud.

No es necesario el plugin "ESP32 LittleFS Data Upload" de Arduino IDE.

> **Nota:** Cierra el Serial Monitor antes de correrlo.

### 8. Verificar en Serial Monitor

Abre Serial Monitor a **115200 baud**. Deberías ver:

```
=== BOCINA TEST — BCLK=15 LRC=16 DIN=17 ===
LittleFS OK (5088 KB usados / 13107 KB total)
Bocina OK
```

Presiona **D** para reproducir los 59 audios en orden.

---

## Sketch — funciones principales

### reproducir(VozID id)

Lee el archivo `.pcm` de LittleFS y lo escribe al I2S a 22050 Hz.

```cpp
reproducir(VOZ_CORRECTO);          // "Correcto."
reproducir(vozNivel(5));           // "Nivel 5."
reproducir(vozCorrectos(3));       // "3 colores correctos. Tu turno."
reproducir(vozFin(360));           // "Fin del juego. Obtuviste 360 puntos."
```

### reproducirYRestaurar(VozID id)

Como `reproducir()` pero restaura el I2S a 44100 Hz después
(necesario si luego quieres reproducir tonos o melodías).

### Helpers del enum

```cpp
vozNivel(n)       // n = 2..15  →  VOZ_NIVEL_02..VOZ_NIVEL_15
vozCorrectos(n)   // n = 2..14  →  VOZ_CORRECTOS_02..VOZ_CORRECTOS_14
vozFin(puntos)    // cualquier valor → el audio del puntaje más cercano
```

---

## Opción D del menú — prueba completa

Al presionar `D` en el Serial Monitor, el ESP32:

1. Verifica que LittleFS está montado
2. Reproduce los 59 archivos en orden del enum
3. Imprime en Serial: `[N/59] /nombre.pcm`
4. 300 ms de silencio entre cada archivo

---

## Servidor TTS en tiempo real (opcional, requiere WiFi)

Para la opción C del menú (texto libre → voz):

```bash
python tts_server.py
```

Servidor Flask en puerto 8080. El ESP32 envía texto por HTTP POST
y recibe PCM crudo que escribe directo al I2S.

Configurar en `speaker_test.ino`:
```cpp
#define WIFI_SSID  "TuRedWiFi"
#define WIFI_PASS  "TuContrasena"
#define TTS_HOST   "192.168.1.XX"   // IP de tu PC
#define TTS_PORT   8080
```

---

## Solución de problemas

| Error | Causa | Solución |
|---|---|---|
| `exceeds flash chip size 0x400000` | Flash Size = 4MB en Arduino IDE | Cambiar a 16MB y recompilar |
| `LittleFS: no montado` | Audio no subido | Ejecutar `python subir_audio.py` |
| `No module named esptool` | esptool en otro Python | El script lo detecta automáticamente; si falla: `pip install esptool` |
| Voz entrecortada | I2S a frecuencia incorrecta | El sketch reinicia I2S a 22050 Hz antes de reproducir |
| Sin sonido | Conexiones I2S incorrectas | Verificar GPIO 15/16/17 y VDD=3V3 |
