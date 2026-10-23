import { useEffect, useState } from "react";
import SiteLink from "../components/common/SiteLink";
import { getPacks } from "../api/billingApi";
import { useCredits } from "../hooks/useCredits";
import { siteDetails } from "../content/siteDetails";
import {
  FALLBACK_PACKS, PACK_DETAILS, SHORT_CREDIT_COST,
  displayPacks, formatPrice, packEquivalents, pricePer100Credits,
} from "../utils/pricing";
import "./PricingPage.css";

const freeTiers = [
  { name: "Guest", credits: 45, note: "No account needed", points: ["Videos up to 35 minutes", "10 questions a day"] },
  { name: "Free account", credits: 80, note: "Sign up free", points: ["Longer videos, within your credits", "50 questions a day", "Your video history"] },
];

const perks = [
  ["Kept for 7 days", "Your analyses and Shorts stay available for a week instead of 24 hours."],
  ["Priority processing", "Your videos skip the free queue and get reserved transcription capacity."],
  ["Ask freely", "Ask as many questions as you need about your videos."],
];

function YourCredits({ credits }) {
  if (!credits) return null;
  return (
    <p className="pricing-balance" role="status">
      You have <strong>{credits.free_left} free credits</strong> left today
      {credits.purchased_balance > 0 && <> and <strong>{credits.purchased_balance} purchased</strong></>}.
    </p>
  );
}

function PackCard({ pack, signedIn, onSignIn }) {
  const details = PACK_DETAILS[pack.code];
  const { videos, videoMinutes, shorts } = packEquivalents(pack.credits);
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
        <li>About {videos} videos of {videoMinutes} minutes</li>
        <li>or up to {shorts} Shorts</li>
        <li>{pricePer100Credits(pack)} per 100 credits</li>
        <li>Credits never expire</li>
      </ul>
      {signedIn
        ? <button type="button" className="pricing-buy" disabled>Coming soon</button>
        : <button type="button" className="pricing-buy" onClick={onSignIn}>Sign in to buy</button>}
    </article>
  );
}

export default function PricingPage({ signedIn = false, onSignIn }) {
  const [packs, setPacks] = useState(FALLBACK_PACKS);
  const credits = useCredits();

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
          Everyone gets free credits every day. When you need more, buy a pack once.
          No subscription, and purchased credits never expire.
        </p>
        <YourCredits credits={credits} />
      </header>

      <section className="pricing-section" aria-labelledby="credits-title">
        <h2 id="credits-title">How credits work</h2>
        <ul className="pricing-rules">
          <li><strong>1 credit</strong><span>per minute of video analyzed</span></li>
          <li><strong>{SHORT_CREDIT_COST} credits</strong><span>per Short you create</span></li>
          <li><strong>0 credits</strong><span>to ask questions about your video</span></li>
          <li><strong>Daily reset</strong><span>free credits renew at midnight IST</span></li>
        </ul>
      </section>

      <section className="pricing-section" aria-labelledby="free-title">
        <h2 id="free-title">Free every day</h2>
        <div className="pricing-free">
          {freeTiers.map((tier) => (
            <article className="pricing-tier" key={tier.name} aria-labelledby={`tier-${tier.credits}`}>
              <h3 id={`tier-${tier.credits}`}>{tier.name}</h3>
              <p className="pricing-credits"><span className="pricing-amount">{tier.credits}</span> credits a day</p>
              <ul className="pricing-points">
                {tier.points.map((point) => <li key={point}>{point}</li>)}
              </ul>
              {tier.name === "Free account" && !signedIn
                ? <button type="button" className="pricing-tier-cta" onClick={onSignIn}>{tier.note}</button>
                : <p className="pricing-tier-note">{tier.name === "Guest" ? tier.note : "You're signed in"}</p>}
            </article>
          ))}
        </div>
      </section>

      <section className="pricing-section" aria-labelledby="packs-title">
        <h2 id="packs-title">Credit packs</h2>
        <p className="pricing-section-intro">Packs add to your free daily credits. Free credits are always used first.</p>
        <div className="pricing-packs">
          {packs.map((pack) => <PackCard key={pack.code} pack={pack} signedIn={signedIn} onSignIn={onSignIn} />)}
        </div>
        <p className="pricing-footnote">Prices in US dollars. Online payments are launching soon.</p>
      </section>

      <section className="pricing-section" aria-labelledby="perks-title">
        <h2 id="perks-title">Included while you have purchased credits</h2>
        <ul className="pricing-perks">
          {perks.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}
        </ul>
      </section>

      <section className="pricing-section pricing-faq" aria-labelledby="faq-title">
        <h2 id="faq-title">Common questions</h2>
        <h3>What if a video fails?</h3>
        <p>If processing fails because of a problem on our side, your credits are returned automatically. Videos with no speech to transcribe still use their credits.</p>
        <h3>Do credits expire?</h3>
        <p>Purchased credits never expire. Free daily credits reset at midnight IST and don't carry over.</p>
        <h3>Can I get a refund?</h3>
        <p>Within 7 days of purchase, if you've used less than 10% of a pack, email <a href={`mailto:${siteDetails.supportEmail}`}>{siteDetails.supportEmail}</a>.</p>
        <h3>Why are guest credits shared?</h3>
        <p>Guests on the same network share a daily limit to keep the service fair. <SiteLink href="/faq">See more answers</SiteLink>.</p>
      </section>
    </article>
  );
}
