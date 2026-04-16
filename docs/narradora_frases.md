# Narradora — Frases completas

Voz: **es-MX-DaliaNeural** (Edge TTS, requiere internet)
Fallback offline: **Microsoft Sabina Desktop** (SAPI de Windows)

---

## Arranque del servidor

- `"Servidor listo. Abre el panel web y conecta."`

---

## Panel web conecta

- `"Simon Dice listo. Presiona ESPACIO para comenzar."`

---

## Inicio de partida / SHOWING_SEQUENCE

- `"Mira y escucha."`

---

## Durante la secuencia — colores (uno por LED encendido)

- `"rojo"`
- `"verde"`
- `"azul"`
- `"amarillo"`

---

## Turno del jugador — LISTENING

- `"Tu turno. Presiona ESPACIO para hablar."` — solo en el primer turno de cada partida nueva
- `"Tu turno."` — todos los demás turnos normales
- `"Correcto. Tu turno."` — tras acierto de un color, quedan más en la secuencia
- `"2 colores correctos. Tu turno."` — tras multi-color con 2 aceptados
- `"3 colores correctos. Tu turno."` — tras multi-color con 3 aceptados
- `"N colores correctos. Tu turno."` — el número varía según cuántos se aceptaron

---

## Secuencia completa — sube de nivel

- `"Correcto."` — confirmación antes de subir de nivel
- `"Nivel 2."` — al pasar al nivel 2
- `"Nivel 3."` — al pasar al nivel 3
- `"Nivel N."` — el número varía (del 2 al 20)

*(El nivel 1 no se narra — solo se narran los niveles siguientes)*

---

## Color incorrecto — WRONG

- `"Incorrecto."`
- `"Di empieza para intentar de nuevo."`

---

## Tiempo agotado — TIMEOUT

- `"Tiempo agotado."`
- `"Di empieza para intentar de nuevo."`

---

## Pausa

- `"Juego pausado."`

---

## Fin del juego — GAME OVER

- `"Fin del juego. Obtuviste 10 puntos."` — el número varía según la puntuación final
- `"Di empieza para volver a jugar."`

---

## Resumen — todas las frases únicas de una vez

```
"Servidor listo. Abre el panel web y conecta."
"Simon Dice listo. Presiona ESPACIO para comenzar."
"Mira y escucha."
"rojo"
"verde"
"azul"
"amarillo"
"Tu turno. Presiona ESPACIO para hablar."
"Tu turno."
"Correcto. Tu turno."
"2 colores correctos. Tu turno."
"3 colores correctos. Tu turno."
"N colores correctos. Tu turno."
"Correcto."
"Nivel 2."
"Nivel 3."
"Nivel N."
"Incorrecto."
"Di empieza para intentar de nuevo."
"Tiempo agotado."
"Juego pausado."
"Fin del juego. Obtuviste X puntos."
"Di empieza para volver a jugar."
```

---

## Sonidos musicales (sin voz, solo tono por altavoz)

- **ROJO** en secuencia → Do4 (262 Hz)
- **VERDE** en secuencia → Mi4 (330 Hz)
- **AZUL** en secuencia → Sol4 (392 Hz)
- **AMARILLO** en secuencia → Si4 (494 Hz)
- **Respuesta correcta** → Do6 → Mi6 (1047 → 1319 Hz, ascendente)
- **Respuesta incorrecta / timeout** → Sol3 → Mi3 (196 → 165 Hz, descendente)
- **Inicio del juego** → Do-Mi-Sol-Do (262→330→392→523 Hz, fanfarria)
- **Game Over** → Do-La-Fa-Do (523→440→349→262 Hz, descendente dramático)
