# ============================================================
# validador.py — Normaliza texto de Whisper → comando válido
#
# Convierte texto transcrito en un comando canónico del juego.
# Incluye filtro de alucinaciones igual que validador.ts del browser.
#
# Usado solo por el simulador cuando necesita validar texto
# (actualmente el browser valida con validador.ts, pero este
# archivo se mantiene como referencia y para posibles futuros usos).
# ============================================================

import unicodedata
import re
from collections import Counter

# Variantes fonéticas por comando
VARIANTES: dict[str, list[str]] = {
    "ROJO":      ["ROJO", "ROJA", "ROXO", "RONJO", "ROCO", "ROSO"],
    "VERDE":     ["VERDE", "BERDE", "BERDI", "VERD", "ERDE", "BIRDE"],
    "AZUL":      ["AZUL", "ASUL", "AZUR", "ASOR", "ASUR"],
    "AMARILLO":  ["AMARILLO", "AMARILLA", "AMARIJO", "MARILLO", "AMARILO", "MARRILLO"],
    "START":     ["START", "EMPIEZA", "INICIA", "COMIENZA", "JUGAR", "ARRANCA",
                  "EMPEZAR", "INICIAR", "COMENZAR", "JUEGA", "ARRANCATE",
                  "EMPIEZE", "INICIE", "INIZI", "INIZIA"],
    "STOP":      ["STOP", "PARA", "PARAR", "TERMINA", "FIN", "SALIR",
                  "TERMINAR", "DETENTE", "ALTO"],
    "PAUSA":     ["PAUSA", "PAUSAR", "ESPERA", "ESPERAR"],
    "REPITE":    ["REPITE", "REPETIR", "REPITA", "REPITELO", "REPITELA"],
    "REINICIAR": ["REINICIAR", "REINICIA", "RESET", "VOLVER",
                  "REINICIATE", "REINICIO"],
    "ARRIBA":    ["ARRIBA", "ARRIVA"],
    "ABAJO":     ["ABAJO", "ABAHO", "AVAJO"],
    "IZQUIERDA": ["IZQUIERDA", "ISKIERDA"],
    "DERECHA":   ["DERECHA", "DERECA"],
    "SI":        ["SI"],
    "NO":        ["NO"],
}

# Frases de dos palabras
FRASES: dict[str, str] = {
    "OTRA VEZ": "REPITE",
    "DE NUEVO": "REPITE",
    "OTRA VES": "REPITE",
}

# Mapa inverso: variante → comando canónico
_MAPA: dict[str, str] = {}
for _cmd, _vars in VARIANTES.items():
    for _v in _vars:
        _MAPA[_v] = _cmd

# Todas las claves del mapa para el filtro de alucinaciones
_VOCAB = set(_MAPA.keys())


def _normalizar(texto: str) -> str:
    """Mayúsculas, sin acentos, sin puntuación."""
    texto = texto.upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^A-Z0-9 ]", "", texto)
    return texto.strip()


def _es_alucinacion(texto: str) -> bool:
    """
    Detecta alucinaciones de Whisper:
    - Sin ninguna palabra del vocabulario del juego
    - Repetición de la misma palabra > 3 veces (loop)
    """
    palabras = _normalizar(texto).split()
    if not palabras:
        return True
    # Sin vocabulario del juego → alucinación
    if not (set(palabras) & _VOCAB):
        return True
    # Loop de repetición → alucinación
    conteo = Counter(palabras)
    if conteo.most_common(1)[0][1] > 3:
        return True
    return False


def texto_a_comando(texto: str) -> str:
    """Convierte texto de Whisper en un comando del juego. Retorna 'DESCONOCIDO' si no hay coincidencia."""
    if not texto:
        return "DESCONOCIDO"
    if _es_alucinacion(texto):
        return "DESCONOCIDO"

    norm = _normalizar(texto)
    if not norm:
        return "DESCONOCIDO"

    # 1. Coincidencia exacta
    if norm in _MAPA:
        return _MAPA[norm]

    # 2. Frases de dos palabras
    for frase, cmd in FRASES.items():
        if frase in norm:
            return cmd

    # 3. Palabra por palabra — solo si el texto es corto (≤ 3 palabras)
    #    Evita falsos positivos como "y no hay algo que no hay" → NO
    palabras = norm.split()
    if len(palabras) <= 3:
        for palabra in palabras:
            if palabra in _MAPA:
                return _MAPA[palabra]

    return "DESCONOCIDO"
