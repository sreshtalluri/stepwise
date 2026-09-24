import type { Metadata } from "next";
import { privacy as copy } from "../../lib/copy";
import { RemoveByLink } from "../../components/RemoveLessonDialog";
import { SiteNav } from "../../components/StateScreen";

export const metadata: Metadata = { title: "Privacy — stepwise" };

/** Every line is in lib/copy.ts `privacy`, each with the code that backs it. */
export default function PrivacyPage() {
  const last = copy.sections.length - 1;
  return (
    <>
    <div className="fd"><SiteNav /></div>
    <main className="wrap app-screen" style={{ maxWidth: 720 }}>
      <h1 className="app-title">{copy.title}</h1>
      <p className="muted" style={{ marginTop: 8 }}>{copy.intro}</p>
      {copy.sections.map((section, i) => (
        <section key={section.heading} style={{ marginTop: 32 }}>
          <h2 className="constraints-heading">{section.heading}</h2>
          <ul style={{ margin: "8px 0 0 1.1em" }}>
            {section.items.map((item) => (
              <li key={item} style={{ padding: "4px 0", maxWidth: "65ch" }}>{item}</li>
            ))}
          </ul>
          {i === last && <RemoveByLink />}
        </section>
      ))}
    </main>
    </>
  );
}
