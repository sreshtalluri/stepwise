import Link from "next/link";
import DemoStage, { type DemoClip } from "../components/DemoStage";
import StageFigure from "../components/StageFigure";
import { marketing, PRODUCT_NAME } from "../lib/copy";

/**
 * The marketing site — docs/DESIGN.md §7d, §7e.
 *
 * Loud: 60px+ display type, the accent used boldly, a dark full-bleed proof
 * band, and a live demo lesson in the hero. Loudness is allowed at the front
 * door and forbidden in the room (§7e) — nothing here sets the register for
 * /lesson/*.
 *
 * Sections, in order: hero with demo → proof band → three steps as an
 * asymmetric list (never three equal cards) → closing call to action.
 */

/**
 * No cleared demo clip exists yet. `evaluation/clips.yaml`'s `demo-public`
 * slot is `needs-permission` and empty; the private testing clips are
 * `rights: untested` and must never appear on a public page. Until a dancer
 * gives explicit permission this stays null and the hero shows the
 * placeholder body, which claims nothing about any real person.
 */
const DEMO_CLIP: DemoClip | null = null;

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

      <section className="wrap hero">
        <div>
          <h1 className="display">
            {marketing.hero.headlineLead}
            <br />
            <em>{marketing.hero.headlineAccent}</em>
          </h1>
          <p className="lede">{marketing.hero.lede}</p>
          <div className="hero-cta">
            <Link href="/upload" className="btn btn-lg">
              {marketing.hero.primary}
            </Link>
            <Link href="#steps" className="btn btn-lg btn-ghost">
              {marketing.hero.secondary}
            </Link>
          </div>
          <p className="meta" style={{ marginTop: 12 }}>
            {marketing.hero.noAccount}
          </p>
        </div>

        <DemoStage clip={DEMO_CLIP} height={380} />
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
          <Link href="/upload" className="btn btn-lg">
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
