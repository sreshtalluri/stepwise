import Link from "next/link";
import { Lockup } from "../components/brand/Mark";
import CountOff from "../components/front/CountOff";
import Demo from "../components/front/Demo";
import LinkDoor from "../components/front/LinkDoor";
import { marketing as copy, upload } from "../lib/copy";

/**
 * The landing, A2 "Count off" (docs/DESIGN.md §7d, §7e). Paper room, loud at
 * the front door.
 *
 * - Hero: headline and the two doors (paste a link, add a file) beside the
 *   count-off toy. Two grid cells, never layered.
 * - Demo: the on-video demo, a labelled placeholder until a cleared clip is
 *   dropped into components/front/Demo.tsx's DEMO constant.
 * - The wait as steps (no times: nothing here has a job to measure), then
 *   what the lesson can do, then what works best and the rights lines.
 */
export default function MarketingPage() {
  return (
    <main className="fd">
      <nav className="fd-nav">
        <Lockup />
        <div className="fd-nav-r">
          <Link href="/lessons">{copy.nav.myLessons}</Link>
          <Link href="/upload" className="fd-btn fd-btn-sm">{copy.nav.add}</Link>
        </div>
      </nav>

      <section className="fd-hero">
        <div>
          <h1 className="fd-h1">
            {copy.hero.headlineLead} <span className="fd-hl">{copy.hero.headlineAccent}</span>
          </h1>
          <p className="fd-lede">{copy.hero.lede}</p>
          <div className="fd-doors">
            <LinkDoor id="hero" />
            <div>
              <Link href="/upload" className="fd-btn fd-btn-ghost">{upload.choose}</Link>
            </div>
          </div>
          <ul className="fd-facts" aria-label={upload.worksBestHeading}>
            {copy.hero.facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
        <CountOff />
      </section>

      <Demo />

      <section className="fd-band">
        <h2 className="fd-h2">{copy.wait.heading}</h2>
        <p className="fd-lede">{copy.wait.body}</p>
        <ol className="fd-timeline">
          {copy.wait.steps.map((s) => (
            <li key={s.label}>
              <b>{s.label}</b>
              <span>{s.body}</span>
            </li>
          ))}
        </ol>
        <ul className="fd-bits" aria-label={copy.wait.featuresLabel}>
          {copy.wait.features.map(([text, aside]) => (
            <li key={text}>
              {text}
              {aside && <em> ({aside})</em>}
            </li>
          ))}
        </ul>
      </section>

      <footer className="fd-foot">
        <div>
          <h3>{copy.foot.worksHeading}</h3>
          <ul>
            {upload.worksBest.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
        <div className="fd-note">
          <p>{upload.rights}</p>
          <p>{upload.link.rights}</p>
        </div>
      </footer>
    </main>
  );
}
