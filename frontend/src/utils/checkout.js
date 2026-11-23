// Razorpay Checkout: loads their script on first use and opens the payment popup.
const SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";
let loading = null;

export function loadRazorpay() {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error("razorpay missing")));
      script.onerror = () => { script.remove(); loading = null; reject(new Error("razorpay blocked")); };
      document.head.appendChild(script);
    });
  }
  return loading;
}

// Resolves with Razorpay's {razorpay_order_id, razorpay_payment_id, razorpay_signature},
// or rejects with { dismissed: true } when the person closes the popup, or { failed: true } when the payment fails.
export async function openCheckout(order, { email, name, description } = {}) {
  const Razorpay = await loadRazorpay();
  return new Promise((resolve, reject) => {
    const popup = new Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount_cents,
      currency: order.currency,
      name: "Vidora AI",
      description,
      prefill: { email, name },
      theme: { color: "#f26522" },
      handler: resolve,
      modal: { ondismiss: () => reject({ dismissed: true }) },
    });
    popup.on("payment.failed", () => reject({ failed: true }));
    popup.open();
  });
}

// Plain-language text for a failed purchase step; never shows server text.
export function checkoutError(error) {
  if (error?.dismissed) return "";
  if (error?.failed) return "The payment didn't go through. You weren't charged. Please try again or use another method.";
  const status = error?.response?.status;
  if (status === 503) return "Payments aren't available right now. Please try again later.";
  if (status === 429) return "Too many attempts. Wait a minute and try again.";
  if (status === 401) return "Please sign in to buy credits.";
  if (status === 400 || status === 404) return "We couldn't confirm your payment. If you were charged, your credits will arrive shortly or email support.";
  if (error?.message === "razorpay blocked") return "The payment window couldn't load. Turn off ad blockers for this page and try again.";
  if (error?.code === "ERR_NETWORK") return "We couldn't connect. Check your internet connection and try again.";
  return "Something went wrong. If you were charged, your credits will arrive shortly.";
}
