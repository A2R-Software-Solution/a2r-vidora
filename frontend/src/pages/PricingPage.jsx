import { useEffect, useRef, useState } from "react";
import SiteLink from "../components/common/SiteLink";
import { createOrder, getPacks, verifyPayment } from "../api/billingApi";
import { refreshCredits, useCredits } from "../hooks/useCredits";
import { checkoutError, openCheckout } from "../utils/checkout";
import { usePlans } from "../hooks/usePlans";
import { siteDetails } from "../content/siteDetails";
import {
  FALLBACK_PACKS, PACK_DETAILS,
  displayPacks, formatHours, formatPrice, pricePer100Credits,
} from "../utils/pricing";
import "./PricingPage.css";

const perks = (plans) => [
  [`Kept for ${formatHours(plans.paid_retention_hours)}`,
    `Your analyses and Shorts stay available for ${formatHours(plans.paid_retention_hours)} instead of ${formatHours(plans.free_retention_hours)}.`],
  ["Priority processing", "Your videos skip the free queue and get reserved transcription capacity."],
  ["Ask freely", "Ask as many questions as you need about your videos."],
];

function YourCredits({ credits }) {
  // Hold the pill's space until the balance arrives, so the page below doesn't jump.
  if (!credits) return <p className="pricing-balance balance-pending" aria-hidden="true">&nbsp;</p>;
  return (
    <p className="pricing-balance" role="status">
      You have <strong>{credits.free_left} free credits</strong> left
      {credits.purchased_balance > 0 && <> and <strong>{credits.purchased_balance} purchased</strong></>}.
    </p>
  );
}

function PackCard({ pack, signedIn, onSignIn, onBuy, busy, buying }) {
  const details = PACK_DETAILS[pack.code];
  return (
    <article className={`pricing-pack${details.featured ? " pricing-pack--featured" : ""}`} aria-labelledby={`pack-${pack.code}`}>
      {details.featured && <p className="pricing-pack-flag">Best value</p>}
      <h3 id={`pack-${pack.code}`}>{details.name}</h3>
      <p className="pricing-price">
        <span className="pricing-amount">{formatPrice(pack.amount_cents, pack.currency)}</span>
        <span className="pricing-once">one-time</span>
      </p>
      <p className="pricing-credits">{pack.credits} credits</p>
      <p className="pricing-blurb">{details.blurb}</p>
      <ul className="pricing-points">
        <li>{pricePer100Credits(pack)} per 100 credits</li>
        <li>Credits never expire</li>
      </ul>
      {signedIn
        ? <button type="button" className="pricing-buy" onClick={() => onBuy(pack)} disabled={busy}>
            {buying ? "Opening payment…" : `Buy ${pack.credits} credits`}</button>
        : <button type="button" className="pricing-buy" onClick={onSignIn}>Sign in to buy</button>}
    </article>
  );
}

function FreeCard({ plans, signedIn, onSignIn }) {
  return (
    <article className="pricing-pack" aria-labelledby="pack-free">
      <h3 id="pack-free">Free</h3>
      <p className="pricing-price">
        <span className="pricing-amount">Free</span>
        <span className="pricing-once">one-time</span>
      </p>
      <p className="pricing-credits">{plans.user_monthly_credits} credits</p>
      <p className="pricing-blurb">Sign up and start with free credits.</p>
      <ul className="pricing-points">
        <li>{plans.user_daily_questions} questions a day</li>
        <li>Your video history</li>
        <li>One-time bonus, does not renew</li>
      </ul>
      {signedIn
        ? <p className="pricing-tier-note">You're signed in</p>
        : <button type="button" className="pricing-buy" onClick={onSignIn}>Sign up free</button>}
    </article>
  );
}

export default function PricingPage({ signedIn = false, onSignIn }) {
  const [packs, setPacks] = useState(FALLBACK_PACKS);
  const [buying, setBuying] = useState("");
  const [result, setResult] = useState(null);
  const busy = useRef(false);
  const credits = useCredits();
  const plans = usePlans();

  // Razorpay credits a captured payment at once; a slower one is credited by its webhook, so re-check a few times.
  const waitForCredits = async () => {
    for (const delay of [0, 3000, 6000, 12000]) {
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      await refreshCredits();
    }
  };

  const buy = async (pack) => {
    if (busy.current) return;
    busy.current = true;
    setBuying(pack.code);
    setResult(null);
    try {
      const { data: order } = await createOrder(pack.code);
      const paid = await openCheckout(order, { description: `${order.credits} Vidora AI credits` });
      setBuying("");
      const { data } = await verifyPayment(paid);
      if (data.status === "paid") {
        setResult({ ok: true, text: `Payment received. ${data.credits} credits were added to your account.` });
        void refreshCredits();
      } else {
        setResult({ ok: true, text: "Payment received. Your credits will show up in a moment." });
        void waitForCredits();
      }
    } catch (error) {
      const text = checkoutError(error);
      if (text) setResult({ ok: false, text });
    } finally {
      busy.current = false;
      setBuying("");
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    getPacks(controller.signal).then(({ data }) => setPacks(displayPacks(data))).catch(() => {});
    return () => controller.abort();
  }, []);

  return (
    <article className="public-page pricing-page">
      <header className="public-header pricing-header">
        <p className="public-eyebrow">Pricing</p>
        <h1>Start free. Top up when you need more.</h1>
        <p className="public-intro">
          Sign up free and get {plans.user_monthly_credits} free credits as a one-time bonus. When you need more, buy a pack once.
          No subscription, and purchased credits never expire.
        </p>
        <YourCredits credits={credits} />
      </header>

      <section className="pricing-section" aria-labelledby="packs-title">
        <h2 id="packs-title">Credit packs</h2>
        <p className="pricing-section-intro">Packs add to your free signup credits. Free credits are always used first.</p>
        {result && <p className={`pricing-result pricing-result--${result.ok ? "ok" : "error"}`} role={result.ok ? "status" : "alert"}>{result.text}</p>}
        <div className="pricing-packs">
          <FreeCard plans={plans} signedIn={signedIn} onSignIn={onSignIn} />
          {packs.map((pack) => <PackCard key={pack.code} pack={pack} signedIn={signedIn} onSignIn={onSignIn}
            onBuy={buy} busy={!!buying} buying={buying === pack.code} />)}
        </div>
        <p className="pricing-footnote">Prices in US dollars. Payments are handled securely by Razorpay.</p>
      </section>

      <section className="pricing-section" aria-labelledby="perks-title">
        <h2 id="perks-title">Included while you have purchased credits</h2>
        <ul className="pricing-perks">
          {perks(plans).map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}
        </ul>
      </section>

      <section className="pricing-section pricing-faq" aria-labelledby="faq-title">
        <h2 id="faq-title">Common questions</h2>
        <h3>What if a video fails?</h3>
        <p>If processing fails because of a problem on our side, your credits are returned automatically. Videos with no speech to transcribe still use their credits.</p>
        <h3>Do credits expire?</h3>
        <p>Purchased credits never expire. Your free signup credits are a one-time bonus; they are given once and do not renew.</p>
        <h3>Can I get a refund?</h3>
        <p>Within 7 days of purchase, if you've used less than 10% of a pack, email <a href={`mailto:${siteDetails.supportEmail}`}>{siteDetails.supportEmail}</a>.</p>
        <h3>Do I need an account?</h3>
        <p>Yes. Analyzing videos, asking questions, Shorts, Song Merger and downloads all need a free account. <SiteLink href="/faq">See more answers</SiteLink>.</p>
      </section>
    </article>
  );
}
