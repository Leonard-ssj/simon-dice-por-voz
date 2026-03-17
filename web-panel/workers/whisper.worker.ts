// ============================================================
// workers/whisper.worker.ts — Whisper WASM en Web Worker
// Corre en un hilo separado para no bloquear la UI.
// ============================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
import { pipeline, env } from "@huggingface/transformers";

// Usar caché del browser (IndexedDB) para no re-descargar el modelo
env.allowLocalModels   = false;
env.useBrowserCache    = true;

// Vocabulario como initial_prompt — igual que audio_pc.py
const INITIAL_PROMPT =
  "ROJO VERDE AZUL AMARILLO START STOP PAUSA REPITE REINICIAR " +
  "EMPIEZA INICIA COMIENZA PARA ESPERA VOLVER";

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
      "onnx-community/whisper-small",
      {
        dtype: "q8",  // cuantización 8-bit — reduce el tamaño de ~244MB a ~125MB
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
