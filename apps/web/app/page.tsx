import Link from "next/link";
import CountingStage from "../components/CountingStage";
import PasteHero from "../components/PasteHero";
import StageFigure from "../components/StageFigure";
import { marketing, PRODUCT_NAME } from "../lib/copy";

/**
 * The marketing site: docs/DESIGN.md §7d, §7e, and the flow redesign.
 *
 * The hero is direction A's: the paste box IS the primary action, so a link
 * becomes a running job in one step. Beside it, direction B's count strip
 * ticks over a body, teaching the 8-count the lesson is built on before
 * anyone uploads. Loud at the front door, calm in the room (§7e).
 *
 * No cleared demo clip exists yet. `evaluation/clips.yaml`'s `demo-public`
 * slot is `needs-permission` and empty; the private testing clips are
 * `rights: untested` and must never appear on a public page. So the hero's
 * stage is an abstract figure that claims nothing about any real person
 * (components/CountingStage.tsx), and says so.
 *
 * Below the fold, in order: proof band, three steps as an asymmetric list
 * (never three equal cards), closing call to action.
 */
export default function MarketingPage() {
  return (
    <main>
      <nav className="wrap site-nav">
        <span className="logo">{PRODUCT_NAME}</span>
        <div className="site-nav-right">
          <Link href="#proof" className="site-nav-link">{marketing.nav.examples}</Link>
          <Link href="#steps" className="site-nav-link">{marketing.nav.howItWorks}</Link>
          <Link href="/upload" className="btn btn-sm">
            {marketing.nav.openApp}
          </Link>
        </div>
      </nav>

      <section className="wrap hero" id="top">
        <div>
          <h1 className="display">
            {marketing.hero.headlineLead}
            <br />
            <em>{marketing.hero.headlineAccent}</em>
          </h1>
          <p className="lede">{marketing.hero.lede}</p>
          <PasteHero />
        </div>

        <CountingStage />
      </section>

      <section className="wrap" id="proof">
        <div className="band">
          <h2 className="band-heading">{marketing.proof.heading}</h2>
          <p className="band-body">{marketing.proof.body}</p>
          <div className="band-pair">
            <div className="band-panel">
              <span className="stage-label">{marketing.proof.leftLabel}</span>
              <StageFigure azimuth={0} height={120} />
            </div>
            <div className="band-panel">
              <span className="stage-label">{marketing.proof.rightLabel}</span>
              <StageFigure azimuth={90} height={120} />
            </div>
          </div>
          <p className="band-caveat">{marketing.proof.caveat}</p>
        </div>
      </section>

      {/* Asymmetric list. Three equal cards is a banned pattern (§12.10). */}
      <section className="wrap steps" id="steps">
        <h2 className="section-heading">{marketing.steps.heading}</h2>
        <ol>
          {marketing.steps.items.map((step, i) => (
            <li key={step.title} className="step-row">
              <span className="step-num">{i + 1}</span>
              <div>
                <h3 className="step-title">{step.title}</h3>
                <p className="step-body">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="wrap">
        <div className="close-band">
          <h2 className="close-heading">{marketing.close.heading}</h2>
          <p className="muted" style={{ margin: "10px 0 20px" }}>
            {marketing.close.body}
          </p>
          <Link href="#top" className="btn btn-lg">
            {marketing.close.primary}
          </Link>
          <p className="meta" style={{ marginTop: 12 }}>
            {marketing.hero.noAccount}
          </p>
        </div>
      </section>
    </main>
  );
}
