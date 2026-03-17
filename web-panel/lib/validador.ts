// ============================================================
// lib/validador.ts — Normaliza texto de Whisper → comando válido
//
// Convierte el texto transcrito por Whisper WASM en un comando
// canónico del juego (ROJO, START, PAUSA, etc.).
//
// Incluye filtro de alucinaciones: Whisper a veces inventa texto
// cuando no hay voz real. Se descartan frases que no contienen
// ninguna palabra del vocabulario del juego.
// ============================================================

// Variantes fonéticas por comando
const VARIANTES: Record<string, string[]> = {
  ROJO:      ["ROJO", "ROJA", "ROXO", "RONJO", "ROCO", "ROSO"],
  VERDE:     ["VERDE", "BERDE", "BERDI", "VERD", "ERDE", "BIRDE"],
  AZUL:      ["AZUL", "ASUL", "AZUR", "ASOR", "ASUR", "AZUUL"],
  AMARILLO:  ["AMARILLO", "AMARILLA", "AMARIJO", "MARILLO", "AMARILO", "MARRILLO"],
  START:     ["START", "EMPIEZA", "INICIA", "COMIENZA", "JUGAR", "ARRANCA",
              "EMPEZAR", "INICIAR", "COMENZAR", "JUEGA", "ARRANCATE",
              "EMPIEZE", "INICIE", "INIZI", "INIZIA"],
  STOP:      ["STOP", "PARA", "PARAR", "TERMINA", "FIN", "SALIR",
              "TERMINAR", "DETENTE", "ALTO"],
  PAUSA:     ["PAUSA", "PAUSAR", "ESPERA", "ESPERAR"],
  REPITE:    ["REPITE", "REPETIR", "REPITA", "REPITELO", "REPITELA"],
  REINICIAR: ["REINICIAR", "REINICIA", "RESET", "VOLVER", "REINICIATE",
              "REINIZIO", "REINICIO"],
  ARRIBA:    ["ARRIBA", "ARRIVA"],
  ABAJO:     ["ABAJO", "ABAHO", "AVAJO"],
  IZQUIERDA: ["IZQUIERDA", "ISKIERDA"],
  DERECHA:   ["DERECHA", "DERECA"],
  SI:        ["SI", "SÍ", "YES"],
  NO:        ["NO", "NON"],
};

// Frases de dos palabras
const FRASES: Record<string, string> = {
  "OTRA VEZ": "REPITE",
  "DE NUEVO": "REPITE",
  "OTRA VES": "REPITE",
  "VOLVER A": "REPITE",
};

// Mapa inverso: variante → comando canónico
const MAPA_VARIANTES: Record<string, string> = {};
for (const [comando, variantes] of Object.entries(VARIANTES)) {
  for (const v of variantes) {
    MAPA_VARIANTES[v] = comando;
  }
}

// Todas las variantes del vocabulario — para el filtro de alucinaciones
const VOCAB_PALABRAS = new Set(Object.keys(MAPA_VARIANTES));

/**
 * Detecta alucinaciones de Whisper:
 * texto que no contiene ninguna palabra del vocabulario del juego,
 * o que repite la misma palabra más de 3 veces (loop de alucinación).
 */
function esAlucinacion(texto: string): boolean {
  const palabras = normalizar(texto).split(/\s+/).filter(Boolean);
  if (!palabras.length) return true;

  // Sin ninguna palabra del vocabulario → alucinación (ej: "Bienvenidos.", "[Música]")
  if (!palabras.some((p) => VOCAB_PALABRAS.has(p))) return true;

  // Repetición excesiva de la misma palabra → loop de alucinación
  const conteo = new Map<string, number>();
  for (const p of palabras) conteo.set(p, (conteo.get(p) ?? 0) + 1);
  if (Math.max(...conteo.values()) > 3) return true;

  return false;
}

/**
 * Normaliza texto crudo: mayúsculas, sin acentos, sin puntuación.
 */
function normalizar(texto: string): string {
  return texto
    .toUpperCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Z0-9 ]/g, "")
    .trim();
}

/**
 * Convierte texto transcrito por Whisper en un comando del juego.
 * Retorna el comando en mayúsculas o "DESCONOCIDO".
 */
export function textoAComando(texto: string): string {
  if (!texto) return "DESCONOCIDO";
  if (esAlucinacion(texto)) return "DESCONOCIDO";

  const normalizado = normalizar(texto);
  if (!normalizado) return "DESCONOCIDO";

  // 1. Coincidencia exacta del texto completo
  if (MAPA_VARIANTES[normalizado]) return MAPA_VARIANTES[normalizado];

  // 2. Frases de dos palabras
  for (const [frase, comando] of Object.entries(FRASES)) {
    if (normalizado.includes(frase)) return comando;
  }

  // 3. Palabra por palabra — solo si el texto es corto (≤ 3 palabras)
  //    Evita falsos positivos en frases largas como "y no hay algo que no hay" → NO
  const palabras = normalizado.split(/\s+/).filter(Boolean);
  if (palabras.length <= 3) {
    for (const palabra of palabras) {
      if (MAPA_VARIANTES[palabra]) return MAPA_VARIANTES[palabra];
    }
  }

  return "DESCONOCIDO";
}
