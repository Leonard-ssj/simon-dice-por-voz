# Arquitectura del kit

## Diagrama general

```mermaid
flowchart LR
    USB[USB-C PC]
    ESP[ESP32-S3 N16R8]
    OLED[OLED SSD1306 0.91]
    MIC[INMP441 I2S]
    AMP[MAX98357A I2S]
    SPK[Bocina 4Ω 3W]
    SW1[Botón SW1]
    SW2[Botón SW2]
    RGB[LED RGB]

    USB <-->|Serial| ESP
    ESP <-->|I2C SDA/SCL| OLED
    MIC -->|SD / WS / SCK| ESP
    ESP -->|BCLK / LRC / DIN| AMP
    AMP --> SPK
    SW1 --> ESP
    SW2 --> ESP
    ESP --> RGB
```

## Componentes

- ESP32-S3 N16R8 (placa principal)
- OLED SSD1306 0.91" por I2C
- Micrófono INMP441 por I2S
- Amplificador MAX98357A por I2S
- Bocina pasiva 4Ω 3W
- Botones SW1 y SW2
- LED RGB integrado
- USB-C para alimentación y comunicación serial

## Flujo funcional

```mermaid
sequenceDiagram
    participant U as Usuario
    participant ESP as ESP32-S3
    participant MIC as INMP441
    participant AMP as MAX98357A
    participant SPK as Bocina
    participant OLED as OLED
    participant PC as PC

    U->>ESP: Presiona SW1/SW2
    ESP->>MIC: Inicia captura I2S
    MIC-->>ESP: Flujo de audio digital
    ESP->>PC: Envía datos por serial
    PC-->>ESP: Envía comando de control
    ESP->>OLED: Actualiza estado
    ESP->>AMP: Envía audio de salida
    AMP->>SPK: Reproduce sonido
```
