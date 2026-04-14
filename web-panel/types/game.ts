// ============================================================
// types/game.ts — Tipos TypeScript del protocolo Simon Dice
// ============================================================

export type EstadoJuego =
  | "IDLE"
  | "SHOWING"
  | "LISTENING"
  | "EVALUATING"
  | "CORRECT"
  | "LEVEL_UP"
  | "WRONG"
  | "GAMEOVER"
  | "PAUSA";

export type ColorJuego = "ROJO" | "VERDE" | "AZUL" | "AMARILLO";

export type ResultadoTurno = "CORRECT" | "WRONG" | "TIMEOUT";

// Mensajes que llegan desde el servidor WebSocket
export type MensajeWS =
  | { tipo: "ready"; raw: string; ts: number; whisperDisponible?: boolean; whisperModelo?: string; tiempoTimeout?: number }
  | { tipo: "state"; estado: EstadoJuego; raw: string; ts: number }
  | { tipo: "detected"; palabra: string; raw: string; ts: number }
  | { tipo: "result"; resultado: ResultadoTurno; raw: string; ts: number }
  | { tipo: "sequence"; secuencia: ColorJuego[]; raw: string; ts: number }
  | { tipo: "expected"; esperado: ColorJuego; raw: string; ts: number }
  | { tipo: "led"; color: ColorJuego | null; raw: string; ts: number }
  | { tipo: "level"; nivel: number; raw: string; ts: number }
  | { tipo: "score"; puntuacion: number; raw: string; ts: number }
  | { tipo: "gameover"; raw: string; ts: number }
  | { tipo: "voz"; texto: string; comando: string; raw?: string; ts: number }
  | { tipo: "log"; raw: string; ts: number };

// Estado completo del juego en el cliente
export interface EstadoCliente {
  conectado: boolean;
  estado: EstadoJuego;
  nivel: number;
  puntuacion: number;
  secuencia: ColorJuego[];
  esperado: ColorJuego | null;
  ledActivo: ColorJuego | null;          // LED encendido en este momento (durante SHOWING)
  ultimaDeteccion: string | null;        // comando reconocido (ROJO, VERDE...)
  ultimoTextoWhisper: string | null;     // texto crudo de Whisper antes de validar
  ultimoResultado: ResultadoTurno | null;
  whisperCargado: boolean;               // modelo Whisper listo en el browser
  whisperTranscribiendo: boolean;        // grabando/procesando audio ahora mismo
  dispositivoMic: string | null;         // nombre del micrófono activo
  dispositivoSpeaker: string | null;     // nombre del altavoz activo
  whisperModelo: string | null;          // modelo Whisper que se está usando
  log: EntradaLog[];
}

export interface EntradaLog {
  id: number;
  ts: number;
  mensaje: string;
  tipo: "info" | "correcto" | "error" | "voz" | "sistema";
}

export const COLOR_CLASES: Record<ColorJuego, string> = {
  ROJO:     "bg-red-500",
  VERDE:    "bg-green-500",
  AZUL:     "bg-blue-500",
  AMARILLO: "bg-yellow-400",
};

export const ESTADO_TEXTO: Record<EstadoJuego, string> = {
  IDLE:       "Esperando...",
  SHOWING:    "Mostrando secuencia",
  LISTENING:  "Escuchando...",
  EVALUATING: "Procesando respuesta",
  CORRECT:    "¡Correcto!",
  LEVEL_UP:   "¡Nivel superado!",
  WRONG:      "Incorrecto",
  GAMEOVER:   "Fin del juego",
  PAUSA:      "Juego en pausa",
};
