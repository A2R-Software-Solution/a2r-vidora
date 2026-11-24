import apiClient from "./client";

export const getPacks = (signal, currency = "USD") => apiClient.get("/billing/packs", { signal, params: { currency } });
export const getCredits = (signal) => apiClient.get("/credits", { signal });
export const getPlans = (signal) => apiClient.get("/credits/plans", { signal });
export const createOrder = (packCode, currency = "USD") =>
  apiClient.post("/billing/orders", { pack_code: packCode, currency });
export const verifyPayment = (result) => apiClient.post("/billing/verify", {
  razorpay_order_id: result.razorpay_order_id,
  razorpay_payment_id: result.razorpay_payment_id,
  razorpay_signature: result.razorpay_signature,
});
