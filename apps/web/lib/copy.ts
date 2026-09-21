/**
 * Every user-facing string on the marketing, upload, processing and reveal
 * surfaces lives here, so that `test/copy.test.ts` can lint all of it in one
 * pass against docs/DESIGN.md §11 (banned words, sentence case, no emoji) and
 * §7h (the honesty boundary).
 *
 * Read docs/DESIGN.md §7h before changing a single line in this file. The
 * overclaim it bans was written twice during the design pass by the person who
 * wrote the rule against it. The test for any line here:
 *
 *   would someone who understood exactly how this works feel misled?
 *
 * Promising a synthesised *viewpoint* of a body the model tracked is honest.
 * Promising a recovered *moment* the model never saw is not.
 */

export const PRODUCT_NAME = "stepwise"; // working name; OPEN-DECISIONS.md D10

export const marketing = {
  nav: {
    examples: "Examples",
    howItWorks: "How it works",
    openApp: "Open the app",
  },

  hero: {
    // Verbatim from DESIGN.md §7d, where the banned overclaim ("Every angle,
    // even ones the camera never shot") was corrected to exactly this line.
    headlineLead: "Every angle,",
    headlineAccent: "from the one video you have.",
    lede:
      "Upload a clip filmed on one camera. Get the dancer back as a 3D body you can spin, slow down, and take one count at a time.",
    primary: "Try it free",
    secondary: "See how it works",
    // DESIGN.md §7e, verbatim.
    noAccount: "No account. Works in your browser.",
    dragHint: "Drag to spin",
  },

  // Non-front presets are labelled "estimated view" and the front one
  // "camera view" — DESIGN.md §4. The labels are not decoration: they are the
  // honesty affordance, and they appear on the marketing hero too.
  views: [
    { id: "front", label: "Front", note: "camera view" },
    { id: "side", label: "Side", note: "estimated view" },
    { id: "back", label: "Back", note: "estimated view" },
    { id: "top", label: "Top", note: "estimated view" },
  ],

  proof: {
    // Both lines are the corrected forms recorded in DESIGN.md §7h. The second
    // correction there was flagged as over-cautious about case 1; this wording
    // keeps the tracked-through-a-turn claim, which is legitimate and is the
    // best thing the product does.
    heading: "Filmed from the front. Watch it from the side.",
    body:
      "A phone films one angle. The step you need is often side-on or from above. When the dancer turns away the body is still tracked, so you can orbit round and see what their arms were doing.",
    leftLabel: "The clip — front only",
    rightLabel: "Same moment, from the side",
    caveat:
      "What the camera could not see is marked instead of invented: solid means seen, sketchy means unsure, dotted means out of frame.",
  },

  steps: {
    heading: "Three steps.",
    items: [
      {
        title: "Upload a clip",
        // Reconciled against PRD §5 "Multi-dancer, revised 2026-09-18".
        // Deliberately not "one dancer" — that cap was removed.
        body:
          "Filmed on one camera, held still. Up to 60 seconds, no cuts. One dancer or several.",
      },
      {
        title: "We build the body",
        // No processing-time number here on purpose: the 2–4 minute figure
        // derives from an FPS claim the PRD says could not be re-verified
        // (PRD §3, §7). The processing screen states time remaining from the
        // live job, not from a constant.
        body:
          "Your video plays the whole time it is working, so you can slow it, mirror it, and loop it straight away.",
      },
      {
        title: "Learn it count by count",
        body:
          "The dance splits into parts. Loop the one that is fighting you until it is not.",
      },
    ],
  },

  close: {
    heading: "Put a dance in.",
    body: "It costs nothing to try.",
    primary: "Try it free",
  },
};

export const upload = {
  title: "Add a clip",
  subtitle: "One video, filmed on one camera. It stays yours.",
  choose: "Choose a video",
  drop: "or drop it here",

  // The pasted-link door. PRD §5 listed paste-a-link as out of v1; the scope
  // note there was updated when this shipped, rather than left contradicting
  // the screen.
  //
  // Read docs/research/link-ingestion.md before touching the rights line
  // below. It is not the upload rights line with a word changed: a pasted
  // link is a weaker claim than a file, and the copy must not pretend
  // otherwise.
  link: {
    heading: "Or paste a link",
    placeholder: "TikTok or YouTube link",
    submit: "Get the lesson",
    inviteLabel: "Invite code",
    invitePlaceholder: "Your code",
    // Says who it is open to and what still works for everyone else. Not
    // "coming soon" — that names a date we have not got.
    gated:
      "Links are open to invited testers while we try this out. Adding a video file works for everyone.",

    // The rights line for links, and deliberately NOT the upload one.
    //
    // DESIGN.md §7d's line — "Only upload video you have the right to use." —
    // is addressed to someone holding a file, who at least might hold the
    // right to it. Pasting a link is a weaker claim: you are asking us to
    // fetch someone else's post, and almost nobody pasting a TikTok has any
    // right to it at all. Saying "only paste video you have the right to use"
    // would be the same sentence pretending the same thing is true, and it is
    // not.
    //
    // So this says what actually happens and who can stop it, and claims
    // nothing about permission. It does not say "we check", "we verify" or
    // "we have permission" (§7h bans all three, and §12.13 lists them), and it
    // does not ask for a tick — docs/research/rights-and-privacy.md §7a found
    // that a checkbox collects an attestation from the wrong person, since the
    // consent that matters is the dancer's and the person pasting cannot give
    // it.
    rights:
      "We fetch the video from the link and build a lesson from it. Anyone in the clip can ask us to take it down, and we will.",
  },

  // Failures on the link path, in the vocabulary the service actually returns
  // (services/motion-api/ingest.py). Each says what happened and what to do
  // next, and none of them states a reason we did not observe — where the
  // platform's own answer is ambiguous, the copy stops at "we could not get
  // it" rather than guessing at private, deleted or blocked.
  linkErrors: {
    unreachable: "That did not go through. Check your connection and try again.",
  },

  // Framed as what works, not what we reject — DESIGN.md §7d.
  worksBestHeading: "Works best with",
  worksBest: [
    "Filmed from the front, on one camera held still.",
    "Up to 60 seconds, with no cuts between shots.",
    "One dancer or several — you pick whose body you learn from.",
  ],

  // The rights line appears here, once, plainly — DESIGN.md §7d,
  // OPEN-DECISIONS.md D8.
  rights: "Only upload video you have the right to use.",

  // Errors say what happened and what to do, and never apologise — §11.
  errors: {
    tooLong:
      "That clip is longer than 60 seconds. Trim it to the part you want to learn and try again.",
    wrongType: "That file is not a video. Pick an mp4, mov, or webm.",
  },
};

export const processing = {
  title: "Building your lesson",
  subtitle: "You can already use the video while the 3D is made.",
  videoLabel: "Your clip — playing now",
  toolsNote: "These work on the video right now.",

  // DESIGN.md §7c: honest about it being a queue, not a session.
  closeable: "You can close this. The link keeps working.",
  copyLink: "Copy the link",
  copied: "Link copied",

  queued: "Still in the queue.",
  // Loose, never a false-precision countdown — DESIGN.md §7c.
  remaining: (minutes: number) =>
    minutes <= 1 ? "About a minute left." : `About ${minutes} minutes left.`,
  almostDone: "Nearly there.",

  speed: (rate: number) => `${rate}× speed`,
  mirrorOn: "Mirror on",
  mirrorOff: "Mirror off",
  loopOn: "Loop on",
  loopOff: "Loop off",

  failedTitle: "This clip did not make it through",
  retry: "Try again",
};

export const reveal = {
  // The orbit itself is the teaching moment — no tooltip, no modal (§7f).
  // This single line is the fallback for people in reduced-motion, who never
  // see the orbit.
  hint: "Drag the body to look from another side.",
};

/** Legend under every 3D stage — DESIGN.md §4, one persistent line. */
export const legend = "Solid = seen · sketchy = unsure · dotted = out of frame";
