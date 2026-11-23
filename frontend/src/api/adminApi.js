import apiClient from "./client";

export const getOverview = (signal) => apiClient.get("/admin/overview", { signal });
export const getList = (resource, params, signal) => apiClient.get(`/admin/${resource}`, { params, signal });
export const getUserDetail = (id, signal) => apiClient.get(`/admin/users/${id}`, { signal });
export const getSettings = (signal) => apiClient.get("/admin/settings", { signal });
// values: { key: number, or null to reset that setting to its default }
export const saveSettings = (values) => apiClient.put("/admin/settings", { values });
export const banUser = (id, reason) => apiClient.post(`/admin/users/${id}/ban`, { reason });
export const unbanUser = (id) => apiClient.post(`/admin/users/${id}/unban`);
export const adjustCredits = (id, amount, reason) =>
  apiClient.post(`/admin/users/${id}/credits`, { amount, reason });
