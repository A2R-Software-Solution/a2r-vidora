import apiClient from "./client";

// Uploads can be up to 25 MB, far slower than the JSON calls' default.
const UPLOAD_TIMEOUT_MS = 120000;

export const getMergeLimits = (signal) => apiClient.get("/audio-merges/limits", { signal });

export const createAudioMerge = ({ spec, files }) => {
  const form = new FormData();
  form.append("spec", JSON.stringify(spec));
  files.forEach((file) => form.append("files", file, file.name));
  return apiClient.post("/audio-merges", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: UPLOAD_TIMEOUT_MS,
  });
};

export const listAudioMerges = (signal) => apiClient.get("/audio-merges", { signal });

export const getMergeDownload = (mergeId, download = true) =>
  apiClient.get(`/audio-merges/${mergeId}/download`, { params: { download } });
