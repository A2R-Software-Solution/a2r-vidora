import apiClient from "./client";

export const getOverview = (signal) => apiClient.get("/admin/overview", { signal });
export const getList = (resource, params, signal) => apiClient.get(`/admin/${resource}`, { params, signal });
export const getUserDetail = (id, signal) => apiClient.get(`/admin/users/${id}`, { signal });
export const adjustCredits = (id, amount, reason) =>
  apiClient.post(`/admin/users/${id}/credits`, { amount, reason });
