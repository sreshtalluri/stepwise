/**
 * /admin: the owner's analytics view. Not linked from anywhere, not indexed.
 *
 * Server-rendered by this route handler, so nothing of it is in the client
 * bundle: GET is a one-field form, POST sends the typed key to
 * services/motion-api `GET /metrics` (x-stepwise-admin-key, checked there
 * against the STEPWISE_ADMIN_KEY Modal Secret) and renders the answer. The key
 * is not stored: no cookie, no session. Wrong key -> the API's 404, shown as
 * "not accepted".
 */
const API = process.env.MOTION_API_URL ?? "http://127.0.0.1:8811";

const esc = (v: unknown) =>
  String(v ?? "—").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

function page(body: string, status = 200) {
  return new Response(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>stepwise metrics</title>
<style>body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#111;background:#fff}
@media (prefers-color-scheme:dark){body{color:#eee;background:#111}th,td{border-color:#333!important}}
table{border-collapse:collapse;margin:8px 0 24px;width:100%}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #ddd}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}h2{margin-top:28px;font-size:17px}
.kpi{display:flex;gap:24px;flex-wrap:wrap}.kpi div{min-width:140px}.kpi b{display:block;font-size:24px}</style></head>
<body>${body}</body></html>`,
    { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex" } },
  );
}

const form = (note = "") => `<h1>Metrics</h1>${note ? `<p>${esc(note)}</p>` : ""}
<form method="post"><label>Admin key <input type="password" name="key" autocomplete="current-password" required></label>
<label> Days <input type="number" name="days" value="30" min="1" max="400" style="width:5em"></label>
<button type="submit">Show</button></form>`;

function table(cols: string[], rows: unknown[][]) {
  const head = cols.map((c, i) => `<th${i ? ' class="n"' : ""}>${esc(c)}</th>`).join("");
  const body = rows.map((r) => `<tr>${r.map((v, i) => `<td${i ? ' class="n"' : ""}>${esc(v)}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${cols.length}">none yet</td></tr>`}</tbody></table>`;
}

interface Metrics {
  since: string;
  days: number;
  daily: { day: string; visitors: number; uploads?: number; gpu_runs?: number; finished?: number; succeeded?: number }[];
  completion_rate: number | null;
  jobs_finished: number;
  top_failures: { code: string; n: number }[];
  features: { name: string; events: number; visitors: number }[];
  lesson_visits: number;
  count_one_correction_rate: number | null;
  median_play_seconds: number | null;
  loops: { via: string; snapped: boolean; n: number }[];
  loop_lengths: { counts: number; n: number }[];
  referrers: { host: string; n: number }[];
}

function render(m: Metrics) {
  return `<h1>Metrics <small>since ${esc(m.since)}</small></h1>
<div class="kpi"><div><b>${esc(Math.max(0, ...m.daily.map((d) => d.visitors)))}</b>peak daily visitors</div>
<div><b>${pct(m.completion_rate)}</b>jobs completed (${esc(m.jobs_finished)})</div>
<div><b>${pct(m.count_one_correction_rate)}</b>lesson visits correcting count 1 (${esc(m.lesson_visits)})</div>
<div><b>${m.median_play_seconds == null ? "—" : `${Math.round(m.median_play_seconds)} s`}</b>median play per lesson visit</div></div>
<h2>Daily</h2>${table(["Day", "Visitors", "Uploads", "GPU runs", "Finished", "Succeeded"],
    m.daily.map((d) => [d.day, d.visitors, d.uploads ?? 0, d.gpu_runs ?? 0, d.finished ?? 0, d.succeeded ?? 0]))}
<h2>Top failure codes</h2>${table(["Code", "Jobs"], m.top_failures.map((f) => [f.code, f.n]))}
<h2>Feature use</h2>${table(["Event", "Events", "Visitor-days"], m.features.map((f) => [f.name, f.events, f.visitors]))}
<h2>Loops</h2>${table(["From", "Snapped", "Loops"], m.loops.map((l) => [l.via, l.snapped, l.n]))}
${table(["Most-used length (counts)", "Loops"], m.loop_lengths.map((l) => [l.counts, l.n]))}
<h2>Lesson referrers</h2>${table(["Host", "Opens"], m.referrers.map((r) => [r.host, r.n]))}
<p>Visitors are distinct one-day hashes; they cannot be added across days. <a href="/admin">Lock</a></p>`;
}

export async function GET() {
  return page(form());
}

export async function POST(req: Request) {
  const data = await req.formData();
  const key = String(data.get("key") ?? "");
  const days = Math.min(400, Math.max(1, Number(data.get("days")) || 30));
  const headers: Record<string, string> = { "x-stepwise-admin-key": key };
  if (process.env.STEPWISE_ORIGIN_KEY) headers["x-stepwise-origin-key"] = process.env.STEPWISE_ORIGIN_KEY;
  try {
    const res = await fetch(`${API}/metrics?days=${days}`, { headers, cache: "no-store" });
    if (res.status === 404) return page(form("That key was not accepted."), 403);
    if (!res.ok) return page(form(`The API answered ${res.status}: ${await res.text()}`), 502);
    return page(render((await res.json()) as Metrics));
  } catch {
    return page(form("Could not reach the API."), 502);
  }
}

export const dynamic = "force-dynamic";
