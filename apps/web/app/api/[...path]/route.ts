/**
 * `/api/*` -> services/motion-api. A route handler, not a next.config rewrite,
 * because the proxy now has to add two headers the browser must not be able
 * to set (next.config.mjs (2) said this would happen the moment one was needed):
 *
 *   x-stepwise-origin-key  STEPWISE_ORIGIN_KEY (a Worker secret). With the same
 *                          value in Modal, the API answers only this Worker.
 *   x-stepwise-client-ip   the learner's address. Behind a Worker the API
 *                          otherwise sees Cloudflare's egress, which would
 *                          put every learner in one rate-limit bucket.
 *
 * Both are stripped from the incoming request first, so a client cannot
 * forge either. Redirects pass through untouched (`/assets/*` answers 302 to
 * R2, which the browser follows itself, Range header and all).
 */
const API = process.env.MOTION_API_URL ?? "http://127.0.0.1:8811";

// Hop-by-hop, or recomputed by fetch; forwarding them breaks the request.
const DROP_REQUEST = ["host", "connection", "keep-alive", "transfer-encoding", "content-length",
  "x-stepwise-origin-key", "x-stepwise-client-ip"];

async function proxy(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = `${API}/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;

  const headers = new Headers(req.headers);
  for (const h of DROP_REQUEST) headers.delete(h);
  const key = process.env.STEPWISE_ORIGIN_KEY;
  if (key) headers.set("x-stepwise-origin-key", key);
  const ip = req.headers.get("cf-connecting-ip");
  if (ip) headers.set("x-stepwise-client-ip", ip);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const res = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    redirect: "manual",
    // Streams the upload instead of buffering it (Node's fetch requires it).
    ...(hasBody ? { duplex: "half" } : {}),
  } as RequestInit);

  // fetch has already decoded a compressed body; passing the encoding on
  // would make the browser decode it a second time.
  const out = new Headers(res.headers);
  if (out.has("content-encoding")) {
    out.delete("content-encoding");
    out.delete("content-length");
  }
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: out });
}

export const dynamic = "force-dynamic";
export { proxy as GET, proxy as HEAD, proxy as POST, proxy as PUT, proxy as DELETE };
