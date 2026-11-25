import apiClient from "./client";

export const checkAdmin = (signal) => apiClient.get("/admin/me", { signal });
export const getOverview =(signal) => apiClient.get("/admin/overview", { signal });
export const getCreditsSummary = (signal) => apiClient.get("/admin/credits-summary", { signal });
export const getList = (resource, params, signal) => apiClient.get(`/admin/${resource}`, { params, signal });
export const getUserDetail = (id, signal) => apiClient.get(`/admin/users/${id}`, { signal });
export const getSettings = (signal) => apiClient.get("/admin/settings", { signal });
// values: { key: number, or null to reset that setting to its default }
export const saveSettings = (values) => apiClient.put("/admin/settings", { values });
export const banUser = (id, reason) => apiClient.post(`/admin/users/${id}/ban`, { reason });
export const unbanUser = (id) => apiClient.post(`/admin/users/${id}/unban`);
export const adjustCredits = (id, amount, reason) =>
  apiClient.post(`/admin/users/${id}/credits`, { amount, reason });
export const getTimeseries = (days, signal) => apiClient.get("/admin/timeseries", { params: { days }, signal });
export const getActivity = (limit, signal) => apiClient.get("/admin/activity", { params: { limit }, signal });
export const getCoupons = (signal) => apiClient.get("/admin/coupons", { signal });
export const createCoupon = (coupon) => apiClient.post("/admin/coupons", coupon);
// Fields left out stay as they are; null clears a limit.
export const updateCoupon = (id, fields) => apiClient.patch(`/admin/coupons/${id}`, fields);
