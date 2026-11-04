import apiClient from "./client";

export const getDownloadLimits = (signal) => apiClient.get("/downloads/limits", { signal });

export const previewDownload = (url) => apiClient.post("/downloads/preview", { url });

export const createDownload = ({ url, quality }) =>
  apiClient.post("/downloads", { url, quality, rights_confirmed: true });

export const listDownloads = (signal) => apiClient.get("/downloads", { signal });

export const getDownload = (downloadId) => apiClient.get(`/downloads/${downloadId}`);

export const getDownloadFile = (downloadId) => apiClient.get(`/downloads/${downloadId}/file`);
