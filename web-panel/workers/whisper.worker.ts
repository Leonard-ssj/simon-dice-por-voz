// ============================================================
// workers/whisper.worker.ts — Whisper WASM en Web Worker
// Corre en un hilo separado para no bloquear la UI.
// ============================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
import { pipeline, env } from "@huggingface/transformers";

// Usar caché del browser (IndexedDB) para no re-descargar el modelo
env.allowLocalModels   = false;
env.useBrowserCache    = true;

// Vocabulario como initial_prompt en minúsculas para que Whisper lo use como contexto.
// Debe estar en minúsculas — el modelo fue entrenado con texto en minúsculas/mixto, no ALL CAPS.
const INITIAL_PROMPT =
  "rojo verde azul amarillo empieza inicia comienza para pausa repite reinicia " +
  "arriba abajo izquierda derecha sí no";

// Umbral de energía mínima del audio antes de llamar a Whisper.
// Evita que Whisper alucine texto a partir de silencio o ruido de fondo muy bajo.
const RMS_MIN_PARA_TRANSCRIBIR = 0.012;

// Calcula el RMS máximo en bloques de 50ms para detectar si hay voz real.
function calcRmsMax(audio: Float32Array): number {
  const blockSize = 800; // 50ms a 16kHz
  let maxRms = 0;
  for (let i = 0; i + blockSize <= audio.length; i += blockSize) {
    const block = audio.subarray(i, i + blockSize);
    let suma = 0;
    for (let j = 0; j < block.length; j++) suma += block[j] * block[j];
    const rms = Math.sqrt(suma / block.length);
    if (rms > maxRms) maxRms = rms;
  }
  return maxRms;
}

type MensajeWorkerEntrada =
  | { tipo: "cargar" }
  | { tipo: "transcribir"; audio: Float32Array };

type MensajeWorkerSalida =
  | { tipo: "listo" }
  | { tipo: "progreso"; mensaje: string }
  | { tipo: "resultado"; texto: string }
  | { tipo: "error"; mensaje: string };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let transcriber: any = null;

function enviar(msg: MensajeWorkerSalida) {
  self.postMessage(msg);
}

async function cargarModelo() {
  try {
    enviar({ tipo: "progreso", mensaje: "Descargando modelo Whisper..." });

    transcriber = await (pipeline as any)(
      "automatic-speech-recognition",
      "onnx-community/whisper-tiny",
      {
        dtype: "q8",  // cuantización 8-bit — ~40MB, se cachea en IndexedDB
        progress_callback: (progreso: { status: string; progress?: number }) => {
          if (progreso.status === "downloading" && progreso.progress !== undefined) {
            const pct = Math.round(progreso.progress);
            enviar({ tipo: "progreso", mensaje: `Descargando modelo: ${pct}%` });
          } else if (progreso.status === "loading") {
            enviar({ tipo: "progreso", mensaje: "Cargando modelo en memoria..." });
          }
        },
      }
    );

    enviar({ tipo: "listo" });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    enviar({ tipo: "error", mensaje: `Error cargando modelo: ${msg}` });
  }
}

async function transcribir(audio: Float32Array) {
  if (!transcriber) {
    enviar({ tipo: "error", mensaje: "Modelo no cargado" });
    return;
  }

  // Verificar que el audio tenga suficiente energia antes de llamar a Whisper.
  // Si el RMS maximo es menor al umbral, el audio es silencio o ruido muy bajo
  // y Whisper alucinaria texto inventado. Retornar "" directamente es mas rapido.
  const rmsMax = calcRmsMax(audio);
  if (rmsMax < RMS_MIN_PARA_TRANSCRIBIR) {
    enviar({ tipo: "resultado", texto: "" });
    return;
  }

  try {
    const resultado = await (transcriber as any)(audio, {
      language:          "es",
      task:              "transcribe",
      initial_prompt:    INITIAL_PROMPT,
      return_timestamps: false,
    });

    const texto =
      typeof resultado === "object" && resultado !== null && "text" in resultado
        ? String((resultado as { text: string }).text).trim()
        : "";

    enviar({ tipo: "resultado", texto });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    enviar({ tipo: "error", mensaje: `Error transcribiendo: ${msg}` });
    enviar({ tipo: "resultado", texto: "" }); // continuar el flujo
  }
}

// Manejar mensajes del hilo principal
self.onmessage = (event: MessageEvent<MensajeWorkerEntrada>) => {
  const msg = event.data;
  if (msg.tipo === "cargar") {
    cargarModelo();
  } else if (msg.tipo === "transcribir") {
    transcribir(msg.audio);
  }
};
