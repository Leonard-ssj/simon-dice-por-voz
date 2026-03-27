# Arquitectura completa — Tres modos de operación

> El sistema tiene tres formas de funcionar. Todos comparten el mismo Web Panel.

---

## Los tres modos de un vistazo

```mermaid
flowchart TD
    subgraph MODO_A[Modo A — Simulador PC]
        A1[python main.py\njuego_sim.py]
        A2[WebSocket :8765]
        A3[Whisper Python\nmic del sistema]
        A4[TTS edge-tts/SAPI]
        A5[LEDs virtuales\nen terminal ANSI]
        A1 --> A2
        A1 --> A3
        A1 --> A4
        A1 --> A5
    end

    subgraph MODO_B[Modo B — ESP32 + servidor_voz]
        B1[Kit MRD085A\nESP32-S3-N16R8]
        B2[INMP441 + MAX98357A\nOLED + SW1/SW2]
        B3[servidor_voz.py\nWhisper Python\npuerto 8766]
        B1 --- B2
    end

    subgraph MODO_C[Modo C — ESP32 solo]
        C1[Kit MRD085A\nmismo hardware]
        C2[Sin Python\nSin instalación adicional]
        C1 --- C2
    end

    subgraph PANEL[Web Panel — Chrome o Edge]
        P1[useWebSocket.ts]
        P2[useWebSerial.ts]
        P3[Whisper WASM\nWeb Worker]
        P4[validador.ts]
        P5[GameStatus · LEDPanel\nSequenceDisplay · LogConsole\nScoreBoard · TurnoTimer]
        P2 --> P3
        P3 --> P4
    end

    A2 <-->|WebSocket JSON| P1
    B1 <-->|USB Serial 921600\ntexto plano + audio base64| P2
    B1 <-->|audio base64 via browser| B3
    B3 <-->|WebSocket JSON\naudio Float32| P2
    C1 <-->|USB Serial 921600\ntexto plano + audio base64| P2
```

---

## ¿Cuándo usar cada modo?

| | Modo A — Simulador | Modo B — ESP32 + Python | Modo C — ESP32 solo |
|---|---|---|---|
| ¿Necesita hardware ESP32? | No | Sí | Sí |
| ¿Necesita Python? | Sí (obligatorio) | Sí (servidor_voz) | **No** |
| ¿Dónde corre el juego? | Python (PC) | Firmware ESP32 | Firmware ESP32 |
| ¿Quién transcribe la voz? | Whisper Python | Whisper Python | Whisper WASM en browser |
| ¿Qué micrófono usa? | Micrófono del sistema | INMP441 del kit o mic PC | INMP441 del kit o mic browser |
| ¿Hay OLED y speaker físico? | No | Sí | Sí |
| ¿Se puede desplegar en Vercel? | No | No | **Sí** |
| ¿Para qué sirve? | Pruebas sin hardware | Entrega con mayor precisión | Entrega autónoma final |

---

## Cómo funciona el reconocimiento de voz en cada modo

### Modo A — Simulador PC

```mermaid
sequenceDiagram
    participant J as Jugador
    participant B as Browser
    participant P as Python ws_server.py

    J->>B: Presiona ESPACIO
    B->>P: PTT_INICIO por WebSocket
    P->>P: Graba micrófono del sistema (sounddevice)
    J->>B: Suelta ESPACIO
    B->>P: PTT_FIN por WebSocket
    P->>P: Whisper transcribe → rojo
    P->>P: normalizar → ROJO
    P-->>B: voz: {comando: ROJO}
    B->>B: juego_sim.py procesa ROJO
```

### Modo B — ESP32 con servidor_voz.py

```mermaid
sequenceDiagram
    participant J as Jugador
    participant SW as Botón SW1/SW2
    participant ESP as ESP32
    participant BR as Browser
    participant VZ as servidor_voz.py

    J->>SW: Presiona botón
    SW->>ESP: GPIO → pausarTimeout + grabar INMP441
    ESP->>BR: Serial → AUDIO:START + líneas base64 + AUDIO:END
    BR->>VZ: WebSocket → audio Float32
    VZ->>VZ: Whisper Python transcribe → ROJO
    VZ-->>BR: WebSocket → comando ROJO
    BR->>ESP: Serial → PTT_FIN + ROJO
    ESP->>ESP: procesarComando(CMD_ROJO)
```

### Modo C — ESP32 sin Python

```mermaid
sequenceDiagram
    participant J as Jugador
    participant BR as Browser
    participant WW as Whisper WASM
    participant ESP as ESP32

    J->>BR: Presiona ESPACIO (teclado)
    BR->>BR: getUserMedia → graba micrófono del browser
    J->>BR: Suelta ESPACIO
    BR->>WW: Float32Array de audio
    WW->>WW: Whisper WASM transcribe en background
    WW-->>BR: texto = rojo
    BR->>BR: validador.ts → ROJO
    BR->>ESP: Serial → ROJO
    ESP->>ESP: procesarComando(CMD_ROJO)
```

---

## Protocolo Serial — mensajes entre ESP32 y browser

**ESP32 → browser**

| Mensaje | Cuándo se envía |
|---|---|
| `READY` | Al arrancar |
| `STATE:IDLE` / `STATE:SHOWING` / `STATE:LISTENING` / etc. | Al cambiar de estado |
| `LED:ROJO` / `LED:VERDE` / `LED:AZUL` / `LED:AMARILLO` | Al mostrar un color de la secuencia |
| `LED:OFF` | Al apagar el LED del color |
| `SEQUENCE:ROJO,VERDE,AZUL` | Al iniciar cada nivel |
| `EXPECTED:ROJO` | Al entrar en LISTENING |
| `RESULT:CORRECT` / `RESULT:WRONG` / `RESULT:TIMEOUT` | Al evaluar la respuesta |
| `LEVEL:3` / `SCORE:30` | Al subir de nivel |
| `GAMEOVER` | Al terminar la partida |
| `BTN_INICIO` | Cuando el jugador presiona SW1/SW2 |
| `AUDIO:START:N` + líneas base64 + `AUDIO:END` | Audio capturado por INMP441 |

**browser → ESP32**

| Mensaje | Significado |
|---|---|
| `ROJO\n` / `VERDE\n` / `AZUL\n` / `AMARILLO\n` | Color detectado por voz |
| `START\n` / `STOP\n` / `PAUSA\n` / `REPITE\n` / `REINICIAR\n` | Comandos de control |
| `PTT_INICIO\n` / `PTT_FIN\n` | Inicio/fin de captura por teclado (pausa el timer) |
