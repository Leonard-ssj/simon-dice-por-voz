# Simon Dice — Guión completo del narrador

Todo lo que dice el narrador TTS (voz `es-MX-DaliaNeural` / SAPI español),
en el orden exacto en que ocurre durante una partida.

---

## Arranque del servidor

- `"Servidor listo. Abre el panel web y conecta."`

---

## Panel web conecta (cada vez que un cliente abre la conexión WebSocket)

- `"Simon Dice listo. Presiona ESPACIO para comenzar."`

---

## Inicio de partida / SHOWING\_SEQUENCE

> Se narra al comienzo de **cada** ronda (nivel 1, y cada nivel siguiente).

- `"Mira y escucha."`

---

## Durante la secuencia — colores

> Se dice **uno por uno**, sincronizado con cada LED encendido.

- `"rojo"`
- `"verde"`
- `"azul"`
- `"amarillo"`

---

## Turno del jugador — LISTENING

- `"Tu turno. Presiona ESPACIO para hablar."` — **solo en el primer turno** de la partida (nivel 1, primer color)
- `"Tu turno."` — todos los demás turnos (post-nivel, post-REPITE, etc.)
- `"Correcto. Tu turno."` — tras acertar 1 color cuando aún quedan más en la secuencia
- `"2 colores correctos. Tu turno."` — tras multi-color con 2 aceptados
- `"3 colores correctos. Tu turno."` — tras multi-color con 3 aceptados
- `"N colores correctos. Tu turno."` — el número varía según cuántos se aceptaron

---

## Secuencia completa — sube de nivel

> El jugador acertó **todos** los colores del nivel actual.

- `"Correcto."` — confirmación inmediata antes de subir de nivel
- `"Nivel 2."` — al pasar al nivel 2
- `"Nivel 3."` — al pasar al nivel 3
- `"Nivel N."` — el número varía del 2 al 15

> **El nivel 1 no se narra** — solo se anuncian los niveles siguientes.

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

- `"Fin del juego. Obtuviste N puntos."` — el número es la puntuación acumulada
- `"Di empieza para volver a jugar."`

---

## Sistema de puntuación

Los puntos se suman **al completar cada nivel**:

| Nivel completado | Puntos ganados | Total acumulado |
|:---:|:---:|:---:|
| 1 | 10 | 10 |
| 2 | 20 | 30 |
| 3 | 30 | 60 |
| 4 | 40 | 100 |
| 5 | 50 | 150 |
| 6 | 60 | 210 |
| 7 | 70 | 280 |
| 8 | 80 | 360 |
| 9 | 90 | 450 |
| 10 | 100 | 550 |
| 11 | 110 | 660 |
| 12 | 120 | 780 |
| 13 | 130 | 910 |
| 14 | 140 | 1050 |
| 15 | 150 | **1200** |

> Fórmula: `puntos_del_nivel = nivel × 10`
>
> Máximo posible (nivel 15 completado): **1 200 puntos**

Si el jugador falla **dentro** de un nivel, acumula únicamente los puntos de los niveles ya completados antes de ese fallo.

**Ejemplo:** falla en el nivel 4 (sin completarlo) → narrador dice `"Fin del juego. Obtuviste 60 puntos."` (10 + 20 + 30 de los niveles 1, 2 y 3 completados).

---

## Conteo de audios únicos posibles

> Si se quisieran pre-grabar todos los posibles clips del narrador, ¿cuántos serían?

### Frases fijas — siempre idénticas (16 audios)

| # | Frase |
|:---:|---|
| 1 | `"Servidor listo. Abre el panel web y conecta."` |
| 2 | `"Simon Dice listo. Presiona ESPACIO para comenzar."` |
| 3 | `"Mira y escucha."` |
| 4 | `"rojo"` |
| 5 | `"verde"` |
| 6 | `"azul"` |
| 7 | `"amarillo"` |
| 8 | `"Tu turno. Presiona ESPACIO para hablar."` |
| 9 | `"Tu turno."` |
| 10 | `"Correcto. Tu turno."` |
| 11 | `"Correcto."` |
| 12 | `"Incorrecto."` |
| 13 | `"Di empieza para intentar de nuevo."` |
| 14 | `"Tiempo agotado."` |
| 15 | `"Juego pausado."` |
| 16 | `"Di empieza para volver a jugar."` |

### Frases variables — dependen del estado del juego (43 audios)

**"N colores correctos. Tu turno."** — N va de 2 a 14 = **13 audios**

> N máximo es 14: si el jugador dice 14 colores correctos en un solo turno
> con el nivel 15 activo, aún queda 1 color → se narra esta frase.
> Si acierta los 15 completos, va directo a CORRECT y no pasa por aquí.

| N | Frase |
|:---:|---|
| 2 | `"2 colores correctos. Tu turno."` |
| 3 | `"3 colores correctos. Tu turno."` |
| … | … |
| 14 | `"14 colores correctos. Tu turno."` |

**"Nivel N."** — N va de 2 a 15 = **14 audios**

| N | Frase |
|:---:|---|
| 2 | `"Nivel 2."` |
| 3 | `"Nivel 3."` |
| … | … |
| 15 | `"Nivel 15."` |

**"Fin del juego. Obtuviste N puntos."** — solo los 16 valores posibles del sistema de puntuación = **16 audios**

| Puntos | Frase |
|:---:|---|
| 0 | `"Fin del juego. Obtuviste 0 puntos."` |
| 10 | `"Fin del juego. Obtuviste 10 puntos."` |
| 30 | `"Fin del juego. Obtuviste 30 puntos."` |
| 60 | `"Fin del juego. Obtuviste 60 puntos."` |
| 100 | `"Fin del juego. Obtuviste 100 puntos."` |
| 150 | `"Fin del juego. Obtuviste 150 puntos."` |
| 210 | `"Fin del juego. Obtuviste 210 puntos."` |
| 280 | `"Fin del juego. Obtuviste 280 puntos."` |
| 360 | `"Fin del juego. Obtuviste 360 puntos."` |
| 450 | `"Fin del juego. Obtuviste 450 puntos."` |
| 550 | `"Fin del juego. Obtuviste 550 puntos."` |
| 660 | `"Fin del juego. Obtuviste 660 puntos."` |
| 780 | `"Fin del juego. Obtuviste 780 puntos."` |
| 910 | `"Fin del juego. Obtuviste 910 puntos."` |
| 1050 | `"Fin del juego. Obtuviste 1050 puntos."` |
| 1200 | `"Fin del juego. Obtuviste 1200 puntos."` |

> Los puntos solo pueden tomar estos 16 valores porque la fórmula es
> acumulativa y determinista: `Σ(nivel × 10)` desde nivel 1 hasta el
> último completado.

### Total

| Tipo | Cantidad |
|---|:---:|
| Frases fijas | 16 |
| "N colores correctos. Tu turno." | 13 |
| "Nivel N." | 14 |
| "Fin del juego. Obtuviste N puntos." | 16 |
| **Total audios únicos posibles** | **59** |

> El TTS genera todos en tiempo real — no se pre-graban.
> Este conteo es útil si en el futuro se quisiera cambiar a audios
> pre-grabados para eliminar la dependencia de internet/SAPI.

---

## Notas técnicas

- El narrador **no habla** mientras se muestra la secuencia — `"Mira y escucha."` se encola antes y el TTS bloquea el PTT hasta que termina.
- El timer de turno **se congela** mientras el narrador habla; el jugador no pierde tiempo de respuesta durante la narración.
- Los comandos `REINICIAR` y `PARA` cancelan inmediatamente cualquier narración pendiente en la cola.
- La voz preferida es `es-MX-DaliaNeural` (edge-tts, requiere internet); si no está disponible, usa la voz SAPI española instalada en Windows.
