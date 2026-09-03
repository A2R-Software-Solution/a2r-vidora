import apiClient from "./client";

export const createOrGetUser = (payload) => {
  return apiClient.post("/users", payload);
};

export const getUser = (userId) => {
  return apiClient.get(`/users/${userId}`);
};