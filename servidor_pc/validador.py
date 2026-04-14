# ============================================================
# validador.py — Normaliza texto de Whisper → comando canónico
#
# Combina dos fuentes de variantes:
#   1. Lenguaje natural (empieza, para, repite, etc.)
#   2. Fonética de Whisper (cómo el modelo transcribe errores)
#
# Pasos de búsqueda:
#   1. Coincidencia exacta con el vocabulario
#   2. Frases de dos palabras ("otra vez", "de nuevo")
#   3. Correcciones fonéticas / lenguaje natural (tabla VARIANTES)
#   4. Fuzzy matching con SequenceMatcher (palabras cortas ≤ 6 chars)
# ============================================================

import unicodedata
import re
from collections import Counter
from difflib import SequenceMatcher

# ─── Vocabulario canónico (espejo de vocabulario.h) ───────────────────────────
COLORES = ["ROJO", "VERDE", "AZUL", "AMARILLO"]

VOCABULARIO = {
    "ROJO", "VERDE", "AZUL", "AMARILLO",
    "START", "STOP", "PAUSA", "REPITE", "REINICIAR",
    "ARRIBA", "ABAJO", "IZQUIERDA", "DERECHA",
    "SI", "NO",
}

# ─── Variantes por comando ────────────────────────────────────────────────────
# Incluye:
#   - Palabras en español natural que el jugador puede decir
#   - Errores fonéticos típicos de Whisper (b/v, j/h, ll/y, z/s, rr/r)
#   - Variantes con y sin tilde, con puntuación suelta
VARIANTES: dict[str, list[str]] = {
    # ROJO: J española = H fuerte → Whisper: "roho", "roxo", "rogo"
    "ROJO": [
        "ROJO", "ROJA", "ROXO", "ROHO", "RROJO", "ROGO",
        "ROJI", "ROCO", "ROJO.", "ROJO,", "RO HO",
    ],

    # VERDE: b/v muy común en español → "berde", "verdi", "berdi"
    "VERDE": [
        "VERDE", "BERDE", "VERDI", "BERDI", "VERD", "BERD",
        "VERDE.", "VERDES", "VÉRDE", "BÉRDÉ",
    ],

    # AZUL: palabra corta (2 sílabas A-ZUL) → la más problemática para Whisper
    # z/s en español → "asul"; vocal inicial "a" puede perderse; tilde falsa
    "AZUL": [
        "AZUL", "ASUL", "ASÚL", "AZÚL", "AZUUL", "AZULL",
        "A ZUL", "A-ZUL", "AZOL", "ATZUL", "ASUUL",
        "AÇUL", "AZÚL.", "AZUL.", "A SUL", "ASOOL",
        "HASUL", "HAZUL", "ADUL", "AZAL",
    ],

    # AMARILLO: ll/y → "amarilo", "amariya"; acento mal puesto
    "AMARILLO": [
        "AMARILLO", "AMARILO", "AMARILLLO", "AMARILLA",
        "AMARIYA", "AMARILIA", "AMARÍLIA", "AMARÍLLO",
        "AMARILO.", "AMARIYO", "AMARIILLO",
    ],

    # START: el jugador dice "empieza", "inicia", "comienza", etc.
    # También variantes fonéticas del anglicismo "start"
    "START": [
        "START", "ESTART", "ESTÁRT", "ESTÁR", "ESTAL",
        "EMPIEZA", "EMPIECE", "EMPIEZE", "EMPIEZAR",
        "INICIA", "INICIE", "INIZIA", "INIZI",
        "COMIENZA", "COMIENCE",
        "JUGAR", "JUEGA", "JUEGO",
        "ARRANCA", "ARRANCATE", "ARRANCAR",
        "EMPEZAR", "INICIAR", "COMENZAR",
        "VAMOS", "YA", "LISTO", "SALE",
    ],

    # STOP: el jugador dice "para", "termina", "fin", etc.
    "STOP": [
        "STOP", "ESTOP", "ESTOB", "ESTOPE", "ESTOPH", "STOP.",
        "PARA", "PÁRATE", "PARATE", "PARAR",
        "TERMINA", "TERMINAR",
        "FIN", "SALIR", "DETENTE", "ALTO",
    ],

    # PAUSA: au → "pauca"; p/b → "bausa"
    "PAUSA": [
        "PAUSA", "PAUCA", "POSA", "PAÚSA", "BAUSA",
        "PAWSA", "PAUSA.", "PAÚSA.", "PAUZAR", "PAUZA",
        "PAUSAR", "ESPERA", "ESPERAR",
    ],

    # REPITE: e final puede perderse; acento; variantes naturales
    "REPITE": [
        "REPITE", "REPITA", "REPIT", "REPÍTE", "RÉPITE",
        "REPITEN", "REPITI", "REPITE.", "REPITA.", "REPITELO",
        "REPETIR", "REPITELA",
    ],

    # REINICIAR: palabra larga, varios puntos de falla
    "REINICIAR": [
        "REINICIAR", "REINICIA", "RENICIA", "REINISI",
        "REINISIAR", "REINISAR", "REINIZIA", "REINICEAR",
        "REINICIAR.", "RENISIAR", "REINICYA", "REINIZIO",
        "REINICIO", "RESET", "VOLVER",
    ],

    # ARRIBA: rr → r simple; b/v → "arriva"
    "ARRIBA": [
        "ARRIBA", "ARIBA", "ARIVA", "ARRIBA.", "ARRIVA",
        "ARRIBA,", "ARIBA.", "HARRIBA", "ARRIBO",
    ],

    # ABAJO: b/v → "avajo"; j/h → "abaho"
    "ABAJO": [
        "ABAJO", "AVAJO", "ABAHO", "ABAXO", "AVAHO",
        "ABAJO.", "ABAHO.", "HAVAJO", "ABAXHO", "AVAXO",
    ],

    # IZQUIERDA: iz → "is"/"es"; qu → "k"/"c"; ie → "e"
    "IZQUIERDA": [
        "IZQUIERDA", "ISQUIERDA", "IZQUERDA", "ESQUIERDA",
        "ISKIERDA", "IQUIERDA", "IZQUIERDA.", "ISKIERDA.",
        "ESQUERDA", "IZQUIERTA", "ISQUERDA", "ISCIERDA",
    ],

    # DERECHA: ch → "c"; acento; e/a finales
    "DERECHA": [
        "DERECHA", "DERECA", "DERECHE", "DERÉCHA",
        "DERECHA.", "DEREXA", "DERESHA", "DÉRECHA",
        "DERECHE.", "DERECHO", "DERÉCHO",
    ],

    # SI: muy corta → Whisper confunde con "sea", "ce", "chi"
    "SI": [
        "SÍ", "SI", "SÍ.", "SI.", "SEA", "CE", "SY",
        "SII", "SÍI", "CI", "CHI",
    ],

    # NO: corta pero relativamente difícil de confundir
    "NO": [
        "NO", "NO.", "NOO", "NOU", "NOH", "NO,",
    ],
}

# ─── Frases de dos palabras ───────────────────────────────────────────────────
FRASES: dict[str, str] = {
    "OTRA VEZ":  "REPITE",
    "DE NUEVO":  "REPITE",
    "OTRA VES":  "REPITE",
    "DE MUEVO":  "REPITE",
}

def _normalizar(texto: str) -> str:
    """Mayúsculas, sin acentos, sin puntuación."""
    texto = texto.upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^A-Z0-9 ]", "", texto)
    return texto.strip()


# ─── Mapa inverso: variante normalizada → comando canónico ───────────────────
_MAPA: dict[str, str] = {}
for _cmd, _vars in VARIANTES.items():
    for _v in _vars:
        _MAPA[_normalizar(_v)] = _cmd

_VOCAB = set(_MAPA.keys())


def _es_alucinacion(texto: str) -> bool:
    """
    Detecta alucinaciones de Whisper:
    - Texto vacío
    - Ninguna palabra del vocabulario presente
    - Repetición de la misma palabra más de 3 veces (loop de alucinación)
    """
    palabras = _normalizar(texto).split()
    if not palabras:
        return True
    if not (set(palabras) & _VOCAB):
        return True
    conteo = Counter(palabras)
    if conteo.most_common(1)[0][1] > 3:
        return True
    return False


def texto_a_comando(texto: str) -> str:
    """
    Convierte texto transcrito por Whisper en un comando canónico del juego.
    Retorna 'DESCONOCIDO' si no hay coincidencia.
    """
    if not texto or not texto.strip():
        return "DESCONOCIDO"

    if _es_alucinacion(texto):
        return "DESCONOCIDO"

    norm = _normalizar(texto)
    if not norm:
        return "DESCONOCIDO"

    # Paso 1: coincidencia exacta con el mapa de variantes
    if norm in _MAPA:
        return _MAPA[norm]

    # Paso 2: frases de dos palabras ("otra vez", "de nuevo")
    for frase, cmd in FRASES.items():
        if _normalizar(frase) in norm:
            return cmd

    # Paso 3: palabra por palabra (≤ 3 palabras para evitar falsos positivos)
    palabras = norm.split()
    if len(palabras) <= 3:
        for palabra in palabras:
            if palabra in _MAPA:
                return _MAPA[palabra]

    # Paso 4: fuzzy matching para palabras cortas (AZUL, SI, NO, ROJO, STOP)
    # Solo cuando el texto es 1-2 palabras para evitar colisiones
    if len(palabras) <= 2:
        mejor_palabra = None
        mejor_ratio   = 0.0
        for token in palabras:
            for cmd in VOCABULARIO:
                # Umbral más bajo para palabras cortas (≤6 chars)
                umbral = 0.70 if len(cmd) <= 6 else 0.82
                ratio  = SequenceMatcher(None, cmd, token).ratio()
                if ratio >= umbral and ratio > mejor_ratio:
                    mejor_ratio   = ratio
                    mejor_palabra = cmd
        if mejor_palabra:
            if DEBUG_VALIDADOR:
                print(f'  [VALID] Fuzzy: "{norm}" → {mejor_palabra} ({mejor_ratio:.2f})')
            return mejor_palabra

    return "DESCONOCIDO"


# Modo debug (activable desde config.py vía servidor.py)
DEBUG_VALIDADOR = False
