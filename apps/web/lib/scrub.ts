/**
 * What the browser is allowed to tell Sentry. Mirrors
 * services/motion-api/observability.py, with one difference that is the whole
 * reason this is not a copy: the browser's own page URL is useful (which lesson
 * broke) and is kept, minus its query string. Every other URL -- a pasted
 * TikTok/YouTube link, a presigned R2 URL with a live signature in it, the
 * Modal API behind the /api rewrite -- becomes "[url]".
 *
 * Runs over the whole event, not a list of fields: a fetch breadcrumb's
 * `data.url`, a console breadcrumb's message and an exception value all carry
 * URLs, and an allowlist is the list that misses one.
 */

const URL_WITH_SCHEME = /\b[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\s'"<>]+/g;
const SCHEMELESS_LINK =
  /\b(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.(?:com|be|net|org|io|tv|app|ly|co)\/[^\s'"<>]*/g;
const SOURCE_KEY = /\b(youtube|tiktok|instagram|vimeo|twitter|x|facebook)(?::[a-z]+)?:[A-Za-z0-9_-]+/g;
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const HANDLE = /(?<![\w/])@[\w.]{2,}/g;

export function scrubText(s: string, ownOrigin?: string): string {
  return s
    .replace(URL_WITH_SCHEME, (u) =>
      ownOrigin && (u === ownOrigin || u.startsWith(ownOrigin + "/"))
        ? u.split(/[?#]/)[0]
        : "[url]",
    )
    .replace(SCHEMELESS_LINK, "[url]")
    .replace(SOURCE_KEY, "$1:[id]")
    .replace(EMAIL, "[email]")
    .replace(HANDLE, "[handle]");
}

// Stack-frame fields are this app's own source, never user data.
const CODE_KEYS = new Set(["filename", "abs_path", "module", "function", "context_line", "pre_context", "post_context"]);

export function scrub<T>(value: T, ownOrigin?: string): T {
  if (typeof value === "string") return scrubText(value, ownOrigin) as T;
  if (Array.isArray(value)) return value.map((v) => scrub(v, ownOrigin)) as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) out[k] = CODE_KEYS.has(k) ? v : scrub(v, ownOrigin);
    return out as T;
  }
  return value;
}
