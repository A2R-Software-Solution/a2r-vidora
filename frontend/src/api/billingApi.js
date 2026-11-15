import apiClient from "./client";

export const getPacks = (signal) => apiClient.get("/billing/packs", { signal });
export const getCredits = (signal) => apiClient.get("/credits", { signal });
export const getPlans = (signal) => apiClient.get("/credits/plans", { signal });
