# Flujo de conversación con el sistema

> Cómo interactúa el jugador con Simon Dice por Voz en cada estado del juego.
> Arquitectura actual: Browser Whisper WASM + simulador Python WebSocket / ESP32 Web Serial.

---

## Comandos de voz disponibles

| Comando | Sinónimos reconocidos | Cuándo es válido |
|---|---|---|
| `START` | empieza, inicia, comienza, jugar, arranca, vamos | IDLE, GAMEOVER, PAUSA |
| `ROJO` | roja, roxo, ronjo, roco, roso | LISTENING |
| `VERDE` | berde, berdi, verd, erde, birde | LISTENING |
| `AZUL` | asul, azur, asor, asur, azuul | LISTENING |
| `AMARILLO` | amarilla, amarijo, marillo, amarilo, marrillo | LISTENING |
| `REPITE` | repetir, repita, repítelo, otra vez, de nuevo | LISTENING |
| `PAUSA` | pausar, espera, esperar | LISTENING, PAUSA |
| `STOP` | para, parar, termina, fin, salir, detente, alto | cualquier momento |
| `REINICIAR` | reinicia, reset, volver, reinicio | GAMEOVER |

El validador (`validador.ts` / `validador.py`) normaliza el texto de Whisper:
elimina acentos, pasa a mayúsculas, quita puntuación, busca variantes fonéticas.
Solo busca palabra por palabra si el texto tiene ≤ 3 palabras (evita falsos positivos).

---

## Orquestador de ventanas de silencio

El browser **silencia el micrófono automáticamente** después de ciertos eventos para evitar
que el TTS del simulador Python sea capturado por Whisper como comando de voz.

| Evento | Ventana de silencio | Razón |
|---|---|---|
| Cliente conecta | 8 segundos | TTS narra bienvenida y reglas |
| `RESULT:CORRECT` | 2.5 segundos | TTS dice "Correcto. Nivel N." |
| `RESULT:WRONG` | 4.5 segundos | TTS dice "Incorrecto. Di empieza..." |
| `RESULT:TIMEOUT` | 4.5 segundos | TTS dice "Tiempo agotado. Di empieza..." |
| `GAMEOVER` | 7 segundos | TTS narra puntuación y cómo reiniciar |
| `STATE:LISTENING` | 0 (limpia) | Escuchar de inmediato cuando es el turno |

Cuando el estado cambia a `SHOWING`, el browser cancela cualquier grabación activa
y limpia los datos del turno anterior (última detección, texto crudo, último resultado).

---

## Diagrama de conversación — ciclo de una partida

```mermaid
%%{init: {"flowchart": {"htmlLabels": false}} }%%
flowchart TD
    A(["Panel conecta"]) -->|"TTS: bienvenida (~7s)\nBrowser: mic silenciado 8s"| B["IDLE: esperando START"]
    B -->|"Jugador dice START\nBrowser abre mic en segundo plano"| C["Estado: SHOWING — Nivel 1"]

    C --> D["LED encendido + tono + TTS color"]
    D --> E["LED apagado"]
    E -->|"Si hay más colores"| D
    E -->|"Secuencia terminada"| F["Estado: LISTENING\nBrowser: mic abre automáticamente"]

    F -->|"Jugador dice color correcto"| G{"Secuencia\ncompleta?"}
    F -->|"Jugador dice color incorrecto"| I["RESULT:WRONG\nTTS: incorrecto (~4s)\nBrowser: mic silenciado 4.5s"]
    F -->|"Jugador dice REPITE"| C
    F -->|"Jugador dice PAUSA"| P["Estado: PAUSA — timer congelado"]
    F -->|"Timeout 15s"| T["RESULT:TIMEOUT\nTTS: tiempo agotado\nBrowser: mic silenciado 4.5s"]

    G -->|"No: sigue la secuencia"| F
    G -->|"Sí: nivel superado"| H["TTS: Correcto. Nivel N.\nBrowser: mic silenciado 2.5s"]
    H --> C

    I --> OV["Estado: GAMEOVER\nTTS: puntuación + instrucciones (~6s)\nBrowser: mic silenciado 7s"]
    T --> OV
    OV -->|"Jugador dice START"| C
    P -->|"Jugador dice PAUSA o START"| F

    classDef sistema fill:#0f2d4a,stroke:#4a9eff,color:#fff
    classDef jugador fill:#0a2a0a,stroke:#33cc33,color:#ddd
    classDef error fill:#2a0a0a,stroke:#ff4444,color:#fff
    classDef mute fill:#2a1a0a,stroke:#ff9900,color:#fff

    class A,C,D,E,F,H sistema
    class B,G jugador
    class I,T,OV error
    class H mute
```

---

## Transcripción de una sesión típica (modo simulador WebSocket)

```
[SISTEMA] Whisper WASM cargado en browser — badge "Whisper listo"
[SISTEMA] Estado: IDLE

=== CONEXIÓN ===
[BROWSER] WebSocket conectado → mic SILENCIADO 8s
[SIMULADOR] TTS: "Panel conectado."
[SIMULADOR] TTS: "Bienvenido a Simon Dice por Voz."
[SIMULADOR] TTS: "El sistema mostrará una secuencia de colores."
[SIMULADOR] TTS: "Cuando sea tu turno, di el color en voz alta."
[SIMULADOR] TTS: "Di empieza para comenzar."
[BROWSER] (8s transcurridos) → mic activo para IDLE

=== INICIO DE PARTIDA ===
[JUGADOR] "empieza"
[BROWSER] VAD detecta voz → mic graba → Whisper: "empieza" → START
[BROWSER] Envía {"tipo":"comando","comando":"START"} por WebSocket
[SIMULADOR] TTS: "Mira y escucha."
[SISTEMA] Estado: SHOWING — Nivel 1

[SISTEMA] LED ROJO encendido | Tono 262Hz
[SIMULADOR] TTS: "rojo"
[SISTEMA] LED ROJO apagado
[BROWSER] mic CANCELADO durante SHOWING

[SISTEMA] Estado: LISTENING — timeout 15s
[BROWSER] mic ACTIVO (ventana de silencio = 0)

=== TURNO CORRECTO ===
[JUGADOR] "rojo"
[BROWSER] VAD → Whisper: "rojo" → ROJO
[BROWSER] Envía {"tipo":"comando","comando":"ROJO"} → CORRECT
[SIMULADOR] TTS: "Correcto. Nivel 2."
[BROWSER] mic SILENCIADO 2.5s

=== TURNO INCORRECTO ===
[JUGADOR] "azul"  ← respuesta incorrecta
[SISTEMA] RESULT:WRONG
[SIMULADOR] TTS: "Incorrecto. Di empieza para intentar de nuevo."
[BROWSER] mic SILENCIADO 4.5s → Estado: GAMEOVER

=== GAME OVER ===
[SIMULADOR] TTS: "Fin del juego. Obtuviste 30 puntos."
[SIMULADOR] TTS: "Di empieza para volver a jugar."
[BROWSER] mic SILENCIADO 7s → luego activo para GAMEOVER

[JUGADOR] "empieza"
[BROWSER] Whisper: "empieza" → START → nueva partida
```

---

## Pasos detallados por estado — qué pasa en cada momento

### 0. Startup
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 1 | Python | Inicia servidor WebSocket en ws://localhost:8765 | — |
| 2 | Python | TTS detecta voz en español (Microsoft Sabina) | — |
| 3 | Python | TTS listo — `_tts_listo` activado | — |
| 4 | Browser | Whisper WASM worker descarga modelo (~125MB, cacheado) | Badge "Descargando modelo: X%" |
| 5 | Browser | Modelo listo | Badge "Whisper listo" ✓ |

### 1. Conexión
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 6 | Usuario | Clic "Conectar" | Botón activo |
| 7 | Browser | Abre WebSocket → ws://localhost:8765 | "Conectando a ws://..." |
| 8 | Python | Acepta conexión — dispara `on_cliente_conectado` en hilo nuevo | "Conexión establecida" |
| 9 | Python | Mic browser **SILENCIADO 8s** (TTS hablará la bienvenida) | Silencio intencional |
| 10 | Python TTS | "Panel conectado. Bienvenido a Simon Dice por Voz. Di empieza para comenzar." | (no badge — mic silenciado) |
| 11 | Browser | 8s transcurridos → bucle de escucha activa | Badge invisible (IDLE) |

### 2. Inicio del juego
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 12 | Browser | Escucha en segundo plano (IDLE, sin badge) | Nada visible |
| 13 | Usuario | Dice "empieza" | — |
| 14 | Browser VAD | RMS > 0.015 por ≥1 bloque → activa grabación | Badge "Detectando voz..." |
| 15 | Browser VAD | 500ms de silencio → detiene grabación | Badge "Procesando..." |
| 16 | Whisper WASM | Procesa audio (~2-5s con whisper-small) | Badge "Procesando..." |
| 17 | validador.ts | "empieza" → START | — |
| 18 | Browser | Envía `{"tipo":"comando","comando":"START"}` | Log: "START → enviado" |

### 3. Mostrando secuencia
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 19 | Python | Inicia `_mostrar_secuencia_bloqueante()` en hilo separado | Estado: "Mostrando secuencia" |
| 20 | Python | `STATE:SHOWING` → browser limpia datos del turno anterior | LEDs apagados |
| 21 | Python | `LED:ROJO` → tono 262Hz (400ms) → `LED:null` | LED Rojo se enciende → se apaga |
| 22 | Python | Pausa 300ms | — |
| 23 | Python | Repite para cada color de la secuencia | Cada LED parpadea en el panel |
| 24 | Browser mic | Mic cancelado durante SHOWING | Sin badge |

### 4. Turno del jugador
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 25 | Python | `STATE:LISTENING` → `silencioHastaRef = 0` | Estado: "Escuchando..." |
| 26 | Browser | Badge "Escuchando..." aparece inmediatamente | Badge indigo pulsante |
| 27 | Browser | `getUserMedia()` abre el micrófono real (~300-500ms) | Badge "Abriendo micrófono..." |
| 28 | Browser | Mic abierto → countdown 8s comienza | Badge "Habla ahora" azul |
| 29 | Usuario | Dice el color | Barra de nivel sube |
| 30 | Browser VAD | RMS > 0.015 → activa grabación | Badge "Detectando voz..." verde |
| 31 | Browser VAD | 500ms silencio → para grabación, cierra mic | Badge "Procesando..." violeta |
| 32 | Whisper WASM | Inferencia (~2-5s) | Badge "Procesando..." |
| 33 | validador.ts | Normaliza texto → comando canónico | — |
| 34 | Browser | Envía `{"tipo":"comando","comando":"ROJO"}` | Log: `"rojo" → ROJO` |

### 5. Evaluación — Correcto
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 35 | Python | Evalúa: ROJO == esperado → CORRECT | Estado: "¡Correcto!" |
| 36 | Python | `RESULT:CORRECT` → browser silencia mic 2.5s | silencioHastaRef + 2.5s |
| 37 | Python TTS | "Correcto. Nivel N." (~1.5s) | Badge desaparece |
| 38 | Python | Si secuencia completa → `LEVEL_UP` + nueva secuencia | Nivel +1 |
| 39 | Python | Vuelve al paso 19 (siguiente nivel) | — |

### 6. Evaluación — Incorrecto o Timeout
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 35b | Python | Evalúa: color incorrecto / 15s sin respuesta | Estado: "Incorrecto" / "Timeout" |
| 36b | Python | `RESULT:WRONG/TIMEOUT` → browser silencia mic 4.5s | silencioHastaRef + 4.5s |
| 37b | Python TTS | "Incorrecto/Tiempo agotado. Di empieza para intentar de nuevo." | Badge desaparece |
| 38b | Python | `STATE:GAMEOVER` → browser silencia mic 7s | Banner rojo "Fin del juego" |
| 39b | Python TTS | "Fin del juego. Obtuviste X puntos. Di empieza para volver a jugar." | — |
| 40b | Browser | 7s transcurridos → escucha "empieza" en segundo plano | Sin badge (GAMEOVER) |
| 41b | Usuario | Dice "empieza" o clic "Reiniciar" | Nueva partida |

### 7. Reinicio vía botón
| # | Quién | Acción | Panel web |
|---|---|---|---|
| 42 | Usuario | Clic botón "↺ Reiniciar" | — |
| 43 | Browser | Envía `{"tipo":"comando","comando":"REINICIAR"}` | Log limpiado |
| 44 | Python | `juego.procesar_comando("REINICIAR")` → nueva partida | Vuelve al paso 19 |

---

## Sesión con PAUSA

```
[SISTEMA] Estado: LISTENING — esperando "VERDE"

[JUGADOR] "pausa"
[BROWSER] Whisper → PAUSA → enviado
[SISTEMA] Estado: PAUSA — timer congelado

[JUGADOR] "pausa"   (o "empieza")
[SISTEMA] Estado: LISTENING — timer reanuda
```

---

## Filtro de alucinaciones de Whisper

Whisper a veces inventa texto cuando no hay voz real. El sistema lo filtra así:

1. **Verificación de energía en el worker**: Si el RMS máximo del audio < 0.012, no se llama a Whisper. Devuelve `""` de inmediato.
2. **Sin vocabulario del juego**: Si el texto transcrito no contiene ninguna palabra del vocabulario del juego, se descarta como alucinación.
3. **Repetición excesiva**: Si la misma palabra aparece > 3 veces, es un loop de alucinación.
4. **Texto muy largo**: Solo se busca palabra por palabra si el texto tiene ≤ 3 palabras (evita falsos positivos como "no hay nada que no hay" → NO).
5. **Ventana de silencio**: El mic no abre durante los primeros segundos después de eventos con TTS, evitando que Whisper capture el audio del narrador.

---

## Mensajes WebSocket durante una partida (modo simulador)

| Evento | Mensaje JSON | Cuándo |
|---|---|---|
| Sistema listo | `{"tipo":"ready"}` | Al arrancar el simulador |
| Cambio de estado | `{"tipo":"state","estado":"SHOWING"}` | Cada transición |
| LED encendido | `{"tipo":"led","color":"ROJO"}` | Durante secuencia |
| LED apagado | `{"tipo":"led","color":null}` | Durante secuencia |
| Secuencia completa | `{"tipo":"sequence","secuencia":["ROJO","VERDE"]}` | Al iniciar nivel |
| Color esperado | `{"tipo":"expected","esperado":"ROJO"}` | Al iniciar turno |
| Resultado | `{"tipo":"result","resultado":"CORRECT"}` | Tras evaluar |
| Nivel | `{"tipo":"level","nivel":3}` | Al subir nivel |
| Puntuación | `{"tipo":"score","puntuacion":30}` | Al cambiar score |
| Game Over | `{"tipo":"gameover"}` | Fin de partida |
| Log | `{"tipo":"log","raw":"mensaje"}` | Debug/info |

### Panel → simulador

```json
{"tipo": "comando", "comando": "ROJO"}
```

---

## Bugs resueltos

| Bug | Causa | Estado |
|---|---|---|
| TTS no decía los colores | `sounddevice` y `pyttsx3` abrían el dispositivo de audio simultáneamente en Windows | **Corregido:** tono primero (bloqueante) luego TTS |
| LEDs no se veían en el panel | `_on_led_encender`/`_on_led_apagar` no enviaban WS; `page.tsx` usaba `estadoJuego.esperado` en lugar de `ledActivo` | **Corregido:** mensaje `tipo:"led"` + campo `ledActivo` |
| Whisper capturaba TTS del simulador | El mic estaba abierto mientras el narrador Python hablaba | **Corregido:** ventanas de silencio de 2.5–8s según el evento |
| "[MÚSICA]" y alucinaciones en IDLE | Whisper procesaba silencio/ruido de fondo repetidamente | **Corregido:** ventana de silencio + filtro de energía RMS + solo loguear en LISTENING |
| "empieza" no reconocido | Whisper tiny con poco contexto reconocía "Empiezan.", "En pieza." | **Corregido:** modelo whisper-small q8 + initial_prompt expandido |
| Log spameado con DESCONOCIDO | El bucle de fondo logueaba cada intento en IDLE/GAMEOVER | **Corregido:** solo loguear resultados de voz en estado LISTENING |
| Badge "Habla ahora" antes de abrir mic | `transcribiendo=true` se activaba antes de `getUserMedia` | **Corregido:** estado `micAbierto` separado |
| Badge mostraba en GAMEOVER/IDLE | Bucle de fondo activaba el badge visual en todos los estados | **Corregido:** badge y nivel de mic solo visibles en estado LISTENING |
