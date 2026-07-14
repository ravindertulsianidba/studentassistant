// Chunked, resumable, retrying upload of a recorded lecture file, then triggers
// server-side transcription. Local audio is preserved until the server confirms
// completion. Works with large (90+ min) recordings by streaming in chunks so we
// never hit proxy body limits.
//
// NOTE: real recording + upload only works in a build (mic + file access).
import { Platform } from "react-native";
import { File, Paths } from "expo-file-system";
import { api } from "@/src/api";

const CHUNK = 512 * 1024; // 512 KB
const MAX_RETRY = 3;

async function postChunk(uploadId: string, index: number, chunkUri: string) {
  const form = new FormData();
  form.append("index", String(index));
  form.append("file", { uri: chunkUri, name: `chunk_${index}.bin`, type: "application/octet-stream" } as any);
  let lastErr: any;
  for (let attempt = 0; attempt < MAX_RETRY; attempt++) {
    try {
      const res = await fetch(`${api.base}/uploads/${uploadId}/chunk`, {
        method: "POST", headers: { ...api.authHeader() } as any, body: form,
      });
      if (res.ok) return await res.json();
      lastErr = new Error(`chunk ${index} failed (${res.status})`);
    } catch (e) { lastErr = e; }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1))); // backoff before retry
  }
  throw lastErr;
}

export type UploadProgress = (done: number, total: number) => void;

/**
 * @returns { transcript_id, text } — the local file is only safe to delete AFTER this resolves.
 */
export async function uploadRecording(
  uri: string,
  meta: { title: string; course?: string | null; filename?: string },
  onProgress?: UploadProgress,
): Promise<{ transcript_id: string; text: string }> {
  if (Platform.OS === "web") throw new Error("Recording upload requires a device build.");

  const src = new File(uri);
  const bytes = await src.bytes();
  const total = Math.max(1, Math.ceil(bytes.length / CHUNK));

  const init = await api.post("/uploads/init", {
    filename: meta.filename || "lecture.m4a", title: meta.title,
    course: meta.course || null, total_chunks: total,
  });
  const uploadId = init.upload_id;

  for (let i = 0; i < total; i++) {
    const slice = bytes.subarray(i * CHUNK, Math.min((i + 1) * CHUNK, bytes.length));
    const tmp = new File(Paths.cache, `sa_chunk_${uploadId}_${i}.bin`);
    try {
      tmp.create({ overwrite: true });
      tmp.write(slice);
      await postChunk(uploadId, i, tmp.uri);
    } finally {
      try { tmp.delete(); } catch {}
    }
    onProgress?.(i + 1, total);
  }
  // Assemble + transcribe on the server.
  return api.post(`/uploads/${uploadId}/complete`, {});
}
