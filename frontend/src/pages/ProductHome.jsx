import SiteLink from "../components/common/SiteLink";
import "./ProductHome.css";

export default function ProductHome() {
  return <section className="product-home">
    <span className="badge">ONE VIDEO. TWO POSSIBILITIES.</span>
    <h1>Make more of<br /><span>every video.</span></h1>
    <p className="product-intro">Turn a long video into your next reel, or get straight to the answers. Where do you want to start?</p>
    <div className="product-options">
      <SiteLink href="/reels" className="product-option product-option--reels">
        <span className="product-icon" aria-hidden="true">▶</span>
        <span className="product-kicker">CREATE SOMETHING NEW</span>
        <h2>Big video.<br />Short highlights.</h2>
        <p>Find standout moments in your YouTube video and turn them into vertical reels with captions.</p>
        <span className="product-details">Clip suggestions · Preview · MP4 download</span>
        <span className="product-cta">Try Our Reel <span aria-hidden="true">↗</span></span>
      </SiteLink>
      <SiteLink href="/analyze" className="product-option">
        <span className="product-icon" aria-hidden="true">✦</span>
        <span className="product-kicker">UNDERSTAND IT FASTER</span>
        <h2>Less watching.<br />More understanding.</h2>
        <p>Explore the summary, ask your questions, and jump to the exact moments that answer them.</p>
        <span className="product-details">Summary · Q&A · Linked timestamps</span>
        <span className="product-cta">Try Our Analyze <span aria-hidden="true">↗</span></span>
      </SiteLink>
    </div>
    <p className="product-footnote">Start with a YouTube link. Choose what you want to do with it.</p>
  </section>;
}
