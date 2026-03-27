# Diagrama de Hardware — Kit MRD085A

> Conexiones físicas del kit MRD085A (ESP32-S3-N16R8).
> El chip ESP32-S3 se comunica con todos los periféricos integrados y externos.
> Los pines marcados con ⚠️ deben verificarse contra el esquemático físico del kit.

---

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}} }%%
flowchart TD
    CHIP(["ESP32-S3-N16R8\n240MHz · 16MB Flash · 8MB PSRAM\nAcceleracion vectorial ESP-NN"])

    subgraph I2S0_MIC ["CAPTURA DE VOZ — I2S0 Bus"]
        MIC(["INMP441\nMicrofono Digital I2S\nSNR 61dB · 16kHz · 16bit · Mono"])
        MIC_SCK["SCK  → GPIO12\nReloj de bit"]
        MIC_WS["WS   → GPIO13\nReloj de palabra"]
        MIC_SD["SD   → GPIO11\nDatos de audio"]
    end

    subgraph I2S1_SPK ["REPRODUCCION DE AUDIO — I2S1 Bus"]
        AMP(["MAX98357A\nAmplificador I2S\n3W · Clase D"])
        SPK(["Bocina Pasiva\n0.5W · 8 Ohm"])
        SPK_BCLK["BCLK → GPIO5\nReloj de bit"]
        SPK_WS["LRCLK → GPIO4\nCanal izquierdo/derecho"]
        SPK_DIN["DIN  → GPIO6\nDatos PCM de audio"]
        SPK_SD["SD_MODE → GPIO7\nActivar/silenciar amplificador"]
    end

    subgraph I2C_OLED ["PANTALLA — I2C Bus"]
        OLED(["OLED 0.91 pulgadas\nSSD1306 · 128x32 px\nMonocromatico blanco"])
        OLED_SDA["SDA → GPIO21\nDatos I2C"]
        OLED_SCL["SCL → GPIO22\nReloj I2C"]
    end

    subgraph GPIO_BTN ["BOTONES PTT — GPIO Entrada"]
        SW1(["SW1 Volumen+\nPTT Principal\nGPIO0 · Pull-up interno"])
        SW2(["SW2 Volumen-\nPTT Alternativo\nGPIO35 · Pull-up interno"])
    end

    subgraph GPIO_LED ["LEDs DE JUEGO — GPIO Salida"]
        LED_R(["LED ROJO\nGPIO15 · 220 Ohm"])
        LED_G(["LED VERDE\nGPIO16 · 220 Ohm"])
        LED_B(["LED AZUL\nGPIO17 · 220 Ohm"])
        LED_Y(["LED AMARILLO\nGPIO18 · 220 Ohm"])
    end

    subgraph USB_SER ["PROTOCOLO SERIAL — USB · 921600 baud"]
        USB_HW(["Puerto USB-C\nUSB-Serial integrado\n921600 baud · 8N1"])
    end

    subgraph BROWSER_LAYER ["BROWSER Chrome/Edge — Web Serial API"]
        WEB_SER["Web Serial API\nConecta al puerto COM\nlectura/escritura linea a linea"]
        WEB_PANEL["Web Panel Next.js 14\nGameStatus · LEDPanel\nSequenceDisplay · LogConsole"]
        WEB_WS["WebSocket cliente\nws://localhost:8766\nenvio de audio base64"]
    end

    subgraph SERVIDOR_PC ["SERVIDOR Python — localhost:8766"]
        SRV_WS["servidor_voz.py\nWebSocket :8766\nrecibe audio base64"]
        SRV_WHISPER["Whisper Python\nmodelo small o base\ntranscripcion local sin internet"]
        SRV_VAL["validador.py\nnormaliza texto a COMANDO\nrojo verde azul amarillo etc"]
    end

    %% Conexiones ESP32 — I2S Microfono
    CHIP -->|"I2S0 maestro"| MIC_SCK
    CHIP -->|"I2S0 maestro"| MIC_WS
    MIC_SD -->|"audio 16kHz 16bit"| CHIP
    MIC_SCK --- MIC
    MIC_WS --- MIC
    MIC --- MIC_SD

    %% Conexiones ESP32 — I2S Speaker
    CHIP -->|"I2S1 maestro"| SPK_BCLK
    CHIP -->|"I2S1 maestro"| SPK_WS
    CHIP -->|"I2S1 maestro PCM"| SPK_DIN
    CHIP -->|"activar amplificador"| SPK_SD
    SPK_BCLK --- AMP
    SPK_WS --- AMP
    SPK_DIN --- AMP
    SPK_SD --- AMP
    AMP -->|"amplificado 3W"| SPK

    %% Conexiones ESP32 — I2C OLED
    CHIP -->|"I2C maestro"| OLED_SDA
    CHIP -->|"I2C maestro"| OLED_SCL
    OLED_SDA --- OLED
    OLED_SCL --- OLED

    %% Conexiones ESP32 — Botones
    SW1 -->|"GPIO0 flanco bajada"| CHIP
    SW2 -->|"GPIO35 flanco bajada"| CHIP

    %% Conexiones ESP32 — LEDs
    CHIP -->|"GPIO15 HIGH/LOW"| LED_R
    CHIP -->|"GPIO16 HIGH/LOW"| LED_G
    CHIP -->|"GPIO17 HIGH/LOW"| LED_B
    CHIP -->|"GPIO18 HIGH/LOW"| LED_Y

    %% Serial
    CHIP -->|"texto plano READY STATE DETECTED etc"| USB_HW
    USB_HW -->|"ROJO VERDE START etc"| CHIP
    USB_HW -->|"AUDIO:START base64 AUDIO:END"| USB_HW

    %% Browser
    USB_HW <-->|"Web Serial API · 921600 baud"| WEB_SER
    WEB_SER --> WEB_PANEL
    WEB_PANEL --> WEB_WS
    WEB_WS -->|"audio Float32 base64 JSON"| SRV_WS

    %% Servidor Python
    SRV_WS --> SRV_WHISPER
    SRV_WHISPER --> SRV_VAL
    SRV_VAL -->|"comando ROJO VERDE etc"| WEB_PANEL
    WEB_PANEL -->|"PTT_FIN + COMANDO via Serial"| WEB_SER

    classDef hardware fill:#1a1500,stroke:#ddaa00,color:#fff
    classDef i2s fill:#0a1a2a,stroke:#4488ff,color:#fff
    classDef gpio fill:#0a2a0a,stroke:#33cc33,color:#ddd
    classDef serial fill:#1a0a2a,stroke:#9933ff,color:#fff
    classDef software fill:#1a1a1a,stroke:#888888,color:#ccc
    classDef browser fill:#002a2a,stroke:#00cccc,color:#fff
    classDef chip fill:#0f2d4a,stroke:#4a9eff,color:#fff

    class CHIP chip
    class MIC,AMP,SPK,SW1,SW2,LED_R,LED_G,LED_B,LED_Y,USB_HW hardware
    class MIC_SCK,MIC_WS,MIC_SD,SPK_BCLK,SPK_WS,SPK_DIN,SPK_SD i2s
    class OLED_SDA,OLED_SCL gpio
    class OLED i2s
    class WEB_SER,WEB_PANEL,WEB_WS browser
    class SRV_WS,SRV_WHISPER,SRV_VAL software
```

---

## Tabla de componentes del kit MRD085A

| Componente | Modelo | Bus | Pines ESP32-S3 | Notas |
|---|---|---|---|---|
| Microcontrolador | ESP32-S3-N16R8 | — | — | 240MHz, 16MB Flash, 8MB PSRAM |
| Micrófono digital | INMP441 | I2S0 | SCK=12, WS=13, SD=11 | 16kHz, 16bit, Mono, SNR 61dB |
| Amplificador audio | MAX98357A | I2S1 | BCLK=5, LRCLK=4, DIN=6, SD=7 | Clase D, 3W, salida diferencial |
| Bocina pasiva | — | — | via MAX98357A | 0.5W, 8Ω estimado |
| Pantalla OLED | SSD1306 0.91" | I2C | SDA=21, SCL=22 | 128×32 px, monocromático |
| Botón SW1 | Pulsador | GPIO | GPIO0 | Volumen+, PTT principal, pull-up |
| Botón SW2 | Pulsador | GPIO | GPIO35 | Volumen-, PTT alternativo, pull-up |
| LED Rojo | LED 5mm | GPIO | GPIO15 | Resistencia 220Ω |
| LED Verde | LED 5mm | GPIO | GPIO16 | Resistencia 220Ω |
| LED Azul | LED 5mm | GPIO | GPIO17 | Resistencia 220Ω |
| LED Amarillo | LED 5mm | GPIO | GPIO18 | Resistencia 220Ω |
| USB Serial | Integrado | USB | — | 921600 baud, cable de flasheo |

---

## Pines a verificar con esquemático MRD085A

> Las siguientes asignaciones son **estimadas** y deben confirmarse con el esquemático
> o con la documentación oficial del kit MRD085A antes de escribir código.

| Pin | Función | Estado |
|---|---|---|
| GPIO12 | INMP441 SCK (I2S0 clock) | ⚠️ VERIFICAR con esquemático |
| GPIO13 | INMP441 WS (I2S0 word select) | ⚠️ VERIFICAR con esquemático |
| GPIO11 | INMP441 SD (I2S0 data in) | ⚠️ VERIFICAR con esquemático |
| GPIO5 | MAX98357A BCLK (I2S1 clock) | ⚠️ VERIFICAR con esquemático |
| GPIO4 | MAX98357A LRCLK (I2S1 word select) | ⚠️ VERIFICAR con esquemático |
| GPIO6 | MAX98357A DIN (I2S1 data out) | ⚠️ VERIFICAR con esquemático |
| GPIO7 | MAX98357A SD_MODE (enable) | ⚠️ VERIFICAR con esquemático |
| GPIO21 | OLED SDA (I2C data) | ⚠️ VERIFICAR con esquemático |
| GPIO22 | OLED SCL (I2C clock) | ⚠️ VERIFICAR con esquemático |
| GPIO0 | SW1 Volumen+ (PTT principal) | ⚠️ VERIFICAR con esquemático |
| GPIO35 | SW2 Volumen- (PTT alternativo) | ⚠️ VERIFICAR con esquemático |
| GPIO15 | LED Rojo | ⚠️ VERIFICAR con esquemático |
| GPIO16 | LED Verde | ⚠️ VERIFICAR con esquemático |
| GPIO17 | LED Azul | ⚠️ VERIFICAR con esquemático |
| GPIO18 | LED Amarillo | ⚠️ VERIFICAR con esquemático |
