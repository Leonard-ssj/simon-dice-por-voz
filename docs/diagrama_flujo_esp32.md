# Flujo del juego — Kit ESP32 MRD085A

> Cómo funciona una partida completa con el hardware físico.

---

## 1. Máquina de estados del juego

El ESP32 siempre está en uno de estos estados. Las transiciones ocurren por comandos de voz o por tiempo.

```mermaid
stateDiagram-v2
    direction LR

    [*] --> IDLE : encendido

    IDLE --> SHOWING : START
    note right of IDLE
        Espera que el jugador diga START
        o presione un botón PTT
    end note

    SHOWING --> LISTENING : secuencia mostrada
    note right of SHOWING
        Enciende el speaker con el tono de cada color
        Envía LED:ROJO al browser para el panel visual
    end note

    LISTENING --> EVALUATING : color recibido
    LISTENING --> GAME_OVER : timeout 15 s
    LISTENING --> PAUSA : PAUSA
    LISTENING --> SHOWING : REPITE
    note right of LISTENING
        Espera que el jugador diga el color correcto
        El timer se pausa mientras graba audio
    end note

    PAUSA --> LISTENING : START o PAUSA

    EVALUATING --> LISTENING : correcto, sigue la secuencia
    EVALUATING --> SHOWING : correcto, nivel superado
    EVALUATING --> GAME_OVER : incorrecto

    GAME_OVER --> IDLE : START o REINICIAR
    note right of GAME_OVER
        OLED muestra puntuación final
        Speaker: melodía de fin
    end note
```

---

## 2. Flujo completo de una partida

```mermaid
flowchart TD
    BOOT([Kit encendido]) --> SETUP

    SETUP[setup\nOLED bienvenida\nSpeaker melodia inicio\nSerial listo 921600 baud] --> IDLE

    IDLE([IDLE\nEspera START]) --> PTT

    PTT{Cómo hace PTT el jugador?}

    PTT -->|Botón SW1 o SW2| BTN_FLOW
    PTT -->|Barra espaciadora en browser| KB_FLOW

    subgraph BTN_FLOW[Botón físico — INMP441]
        B1[SW1/SW2 presionado] --> B2
        B2[INMP441 graba en PSRAM\nhasta soltar el botón] --> B3
        B3[Audio en base64\npor Serial al browser] --> B4
        B4[Browser envía audio\na servidor_voz.py o WASM] --> B5
        B5[Whisper transcribe\nROJO · VERDE · etc]
    end

    subgraph KB_FLOW[Teclado — micrófono del sistema]
        K1[ESPACIO presionado] --> K2
        K2[servidor_voz.py graba mic PC\no WASM graba mic browser] --> K3
        K3[ESPACIO soltado] --> K4
        K4[Whisper transcribe]
    end

    B5 --> CMD
    K4 --> CMD

    CMD[Browser envía comando\nROJO · START · etc\npor Serial al ESP32]
    CMD --> GAME

    GAME{Qué comando llegó?}
    GAME -->|START| SHOWING
    GAME -->|color correcto| CORRECT
    GAME -->|color incorrecto| WRONG
    GAME -->|timeout sin respuesta| TIMEOUT

    SHOWING[SHOWING\nSpeaker tono de cada color\nBrowser actualiza LEDs virtuales\nOLED muestra color actual]
    SHOWING --> LISTENING

    LISTENING[LISTENING\nOLED muestra color esperado\nTimer de 15 s activo]
    LISTENING --> PTT

    CORRECT{Secuencia completa?}
    CORRECT -->|No - sigue escuchando| LISTENING
    CORRECT -->|Sí - nivel superado| LEVEL_UP

    LEVEL_UP[LEVEL UP\nSpeaker tonos de acierto\nnivel y puntuacion actualizados]
    LEVEL_UP --> SHOWING

    WRONG[WRONG\nSpeaker tono de error\nOLED actualizado] --> GAMEOVER
    TIMEOUT[TIMEOUT\nSpeaker tono de error] --> GAMEOVER

    GAMEOVER([GAME OVER\nOLED muestra puntuacion final\nEspera START para nueva partida])
    GAMEOVER --> IDLE
```

---

## 3. Flujo de PTT con botón físico (detalle técnico)

Este diagrama muestra exactamente qué pasa cuando el jugador presiona SW1 o SW2.

```mermaid
sequenceDiagram
    participant J as Jugador
    participant BTN as Botón SW1/SW2
    participant ESP as ESP32 firmware
    participant BR as Browser
    participant VZ as servidor_voz.py
    participant WH as Whisper

    J->>BTN: Presiona SW1
    BTN->>ESP: GPIO flanco de bajada
    ESP->>ESP: pausarTimeout() — timer de 15s se congela
    ESP->>ESP: audioCapturaIniciar() — INMP441 empieza a grabar
    ESP->>BR: Serial → BTN_INICIO
    BR->>BR: Muestra indicador Grabando...

    loop Mientras el botón está presionado
        ESP->>ESP: audioCapturaLoop() — lee bloques I2S y guarda en PSRAM
    end

    J->>BTN: Suelta SW1
    BTN->>ESP: GPIO flanco de subida
    ESP->>ESP: audioCapturaPararYEnviar()
    ESP->>BR: Serial → AUDIO:START:64000
    ESP->>BR: Serial → [líneas en base64]
    ESP->>BR: Serial → AUDIO:END

    BR->>BR: Decodifica base64 → Float32Array
    BR->>VZ: WebSocket → audio Float32

    VZ->>WH: whisper.transcribe(audio)
    WH-->>VZ: texto = rojo
    VZ->>VZ: normalizar → ROJO
    VZ-->>BR: WebSocket → comando = ROJO

    BR->>ESP: Serial → PTT_FIN
    ESP->>ESP: reanudarTimeout() — timer sigue
    BR->>ESP: Serial → ROJO
    ESP->>ESP: procesarComando(CMD_ROJO)
    ESP->>BR: Serial → RESULT:CORRECT
```

---

## 4. Lo que el OLED muestra en cada estado

| Estado del juego | Fila 1 | Fila 2 | Fila 3 |
|---|---|---|---|
| IDLE | `IDLE` | `Nv 1` | `0 pts` |
| SHOWING | `SHOWING` | `Nv 1` | `(color actual)` |
| LISTENING | `LISTEN` | `Nv 1` | `Esp: ROJO` |
| CORRECT | `CORRECT` | `Nv 1` | `10 pts` |
| LEVEL UP | `LEVEL UP` | `Nv 2` | `10 pts` |
| WRONG | `WRONG` | — | — |
| GAME OVER | `GAME OVER` | `Pts: 10` | — |
| PAUSA | `PAUSA` | — | — |
