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
    openApp: "Add a clip",
  },

  hero: {
    // Flow redesign (direction A's paste-in-hero landing), replacing §7d's
    // "Every angle, from the one video you have." The claim is the count
    // structure plus a synthesised VIEWPOINT of a tracked body, both honest
    // under §7h. No processing time: see steps[1] below.
    headlineLead: "Learn any dance,",
    headlineAccent: "count by count.",
    lede:
      "Add a dance video up to 60 seconds long. You get each dancer as a 3D body you can walk around, split into 8-counts.",
    primary: "Try it free",
    // DESIGN.md §7e, verbatim.
    noAccount: "No account. Works in your browser.",
  },

  // The paste box in the hero. Same endpoint and same invite gate as /upload.
  paste: {
    label: "Video link",
    placeholder: "Paste a TikTok or YouTube link",
    submit: "Build the lesson",
    busy: "Fetching the video",
    orFile: "or add a video file",
    inviteLabel: "Invite code",
    // Says what still works for everyone, like upload.link.gated (§11).
    inviteNote: "Links need an invite code while we test. A video file works for everyone.",
    // The stage beside it is an abstract figure, not a clip: no cleared demo
    // clip exists (see app/page.tsx), so it says what it is showing.
    stageLabel: "Every lesson is counted in eights",
  },

  proof: {
    // Both lines are the corrected forms recorded in DESIGN.md §7h. The second
    // correction there was flagged as over-cautious about case 1; this wording
    // keeps the tracked-through-a-turn claim, which is legitimate and is the
    // best thing the product does.
    heading: "Filmed from the front. Watch it from the side.",
    body:
      "A phone films one angle. The step you need is often side-on or from above. When the dancer turns away the body is still tracked, so you can orbit round and see what their arms were doing.",
    leftLabel: "The clip, front only",
    rightLabel: "Same moment, from the side",
    caveat:
      "What the camera could not see is marked instead of invented: solid means seen, sketchy means unsure, dotted means out of frame.",
  },

  steps: {
    heading: "Three steps.",
    items: [
      {
        title: "Paste a link or add a file",
        // Reconciled against PRD §5 "Multi-dancer, revised 2026-09-18".
        // Deliberately not "one dancer" — that cap was removed.
        body:
          "Filmed on one camera, held still. Up to 60 seconds, no cuts. One to six dancers.",
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
  choose: "Choose a video file",
  drop: "or drop it here. Works for everyone.",
  or: "or",

  // The pasted-link door. PRD §5 listed paste-a-link as out of v1; the scope
  // note there was updated when this shipped, rather than left contradicting
  // the screen.
  //
  // Read docs/research/link-ingestion.md before touching the rights line
  // below. It is not the upload rights line with a word changed: a pasted
  // link is a weaker claim than a file, and the copy must not pretend
  // otherwise.
  link: {
    placeholder: "Paste a TikTok or YouTube link",
    submit: "Get the lesson",
    inviteLabel: "Invite code",
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
    // So this says what actually happens, and claims nothing about
    // permission. It used to add "Anyone in the clip can ask us to take it
    // down, and we will." POST /lessons/{id}/removal exists, but nothing on the
    // site lets anyone ask, so that half was a promise with no door (owner
    // rule, 2026-09-23: only what the product does today). Put it back in the
    // same commit as a removal link or contact route.
    //
    // It does not say "we check", "we verify" or "we have permission" (§7h bans all three, and §12.13 lists them), and it
    // does not ask for a tick — docs/research/rights-and-privacy.md §7a found
    // that a checkbox collects an attestation from the wrong person, since the
    // consent that matters is the dancer's and the person pasting cannot give
    // it.
    rights:
      "We fetch the video from the link and build a lesson from it.",
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
    "One to six dancers. You pick whose body you learn from.",
  ],

  // The rights line appears here, once, plainly — DESIGN.md §7d,
  // OPEN-DECISIONS.md D8.
  rights: "Only upload video you have the right to use.",

  // Errors say what happened and what to do, and never apologise — §11.
  errors: {
    tooLong:
      "That clip is longer than 60 seconds. Trim it to the part you want to learn and try again.",
    wrongType: "That file is not a video. Pick an mp4, mov, or webm.",
    uploadFailed: "The upload did not go through. Check your connection and try again.",
  },
};

/**
 * The processing screen: "practice while it builds" (flow redesign, direction
 * B, with A's per-step results). The page turns into a warm-up the moment the
 * counts land, so its title changes with what is actually known.
 */
export const processing = {
  // Before the counts. "Hear the beat" is literal: they come from the audio.
  title: "Start on the video while the 3D is built.",
  subtitle: "Slow it down and mirror it. If the music has a clear beat, the counts show up here.",
  // Once `milestones.counts` has landed.
  countsTitle: "The counts are in. Learn the first 8.",
  countsSubtitle: "This is how the lesson is split. Loop one 8-count until it sticks, then move on.",
  // At success: the handoff, carrying speed and loop into the lesson.
  readyTitle: "Ready. Same counts, now in 3D.",
  readySubtitle: "Your loop and speed carry over.",
  readyPlain: "Your lesson is ready.",
  open: "Open the lesson",

  videoLabel: "Your clip, playing now",
  paused: "Paused. Tap to play.",
  listening: "Listening for the beat",
  part: (from: number, to: number) => `Counts ${from} to ${to}`,
  // The counts are a PROPOSAL from the music, the same one the lesson opens
  // on and labels as a guess (lesson.counts). Tempo is "a minute", never BPM.
  tempo: (perMinute: number) => `${perMinute} a minute, from the music`,
  tempoWeak: (perMinute: number) => `${perMinute} a minute, a rough guess from the music`,
  practice: "Practice counts 1 to 8 at half speed",
  earlier: "Earlier 8",
  next: "Next 8",
  loopEight: (from: number, to: number) => `Loop ${from}–${to}`,
  soundOn: "Sound on",
  soundOff: "Sound off",

  // One at a time, rotated while the counts are up (direction B).
  tipLabel: "While you wait",
  tips: [
    "Say the counts out loud. The 5, 6, 7, 8 before a part is your cue to start.",
    "Mirror on flips the clip, so their right hand is on your right.",
    "Get the feet first. Add the arms once the steps feel automatic.",
    "Half speed is for learning the shape. Go back to full speed to learn the timing.",
  ],

  // A's steps, each with the result it produced. Every "done" note is a
  // milestone the service sent, never a guess from the progress fraction.
  steps: {
    clip: "Clip",
    playing: "Playing now",
    dancers: "Dancers",
    looking: "Looking frame by frame",
    dancersFound: (n: number) => (n === 1 ? "1 dancer" : `${n} dancers`),
    counts: "Counts",
    listening: "Listening",
    noneYet: "None yet. You can set them in the lesson.",
    countsInLesson: "Set in the lesson",
    countsTempo: (perMinute: number) => `${perMinute} a minute`,
    countsFound: (perMinute: number, eights: number) => `${perMinute} a minute, ${eights} eight-counts`,
    body: "3D body",
    frames: (done: number, total: number) => `Frame ${done} of ${total}`,
    eights: (done: number, total: number) => `${done} of ${total} eight-counts built`,
    finishing: "Finishing up",
    ready: "Ready",
  },
  waiting: "Waiting in the queue",
  unreachable: "We cannot reach the job right now. It keeps running, and this page will catch up.",

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
  loopOff: "Loop off",

  failedTitle: "This clip did not make it through",
  retry: "Try again",
};

export const lesson = {
  /**
   * Opening a lesson by its link, keyed by what services/motion-api answered.
   * An unknown job_id reads as "queued" there, not 404, so a mistyped link lands
   * on `notReady` — which is why that line does not promise the lesson exists.
   */
  load: {
    loading: "Loading the lesson.",
    jobTitle: "Your lesson",
    notReady: "This lesson is not ready yet.",
    notReadyLink: "See how it is going",
    removed: "This lesson was removed and is not coming back.",
    notFound: "There is no lesson at this link. Check the link, or add a clip to make one.",
    notFoundLink: "Add a clip",
    failed: "The lesson did not load. Reload the page to try again.",
  },

  /**
   * Where the counts on screen came from, while they are still a guess. One of
   * these shows above the count strip until the learner edits anything; after
   * that the grid is theirs and none of them applies.
   *
   * DESIGN.md §7h, pointed at the counts rather than at the 3D. A learner who
   * believes a wrong count 1 practises the whole dance off the beat, so this is
   * the one place the honesty rule is *more* load-bearing than it is on the
   * mesh, not less.
   *
   * The tempo is "a minute", never "BPM" — §11's plain voice, and the same
   * wording the navigation surface uses two lines below it.
   *
   * `MotionResult.proposed_counts.warnings` is deliberately NOT rendered
   * verbatim. Those strings are the producer's, written for a log
   * ("tempo 196 BPM is outside the typical 70-180 dance-practice range;
   * half/double-time confusion is the likely explanation (see alternates)") —
   * they are not this voice, and the ALL-CAPS rule in §5 would reject them. The
   * `confidence` number picks between these two instead.
   */
  counts: {
    proposed: (perMinute: number) =>
      `Counts proposed from the music, at ${perMinute} a minute. Count 1 is a guess — set it under Counts and parts.`,
    weak: (perMinute: number) =>
      `Counts are a weak guess from the music, at ${perMinute} a minute, and the tempo may be double or half that. Set them under Counts and parts.`,
    placeholder: (perMinute: number) =>
      `Counts are not set for this clip. The ${perMinute} a minute on screen is a placeholder, not the music — set count 1 and the tempo under Counts and parts.`,
  },

  /**
   * The hand/feet close-up panel. `crop_rects` is real video pixels, not a 3D
   * estimate, so there is no "estimated view" label to carry here — the honesty
   * work is entirely in `unavailable`, DESIGN.md §7h: a `null` sample means the
   * region was not confidently localized, and the panel has to say that plainly
   * rather than hold the last frame it drew. A frozen close-up shown as current
   * is exactly the confident-wrong-output failure this line exists to prevent.
   */
  crop: {
    hands: "Hands",
    feet: "Feet",
    left_hand: "L hand",
    right_hand: "R hand",
    left_foot: "L foot",
    right_foot: "R foot",
    unavailable: "Not confidently located here.",
    toggleOn: "Close-up on",
    toggleOff: "Close-up off",
    toggleHint: "hands and feet",
    /** Foot contact from the 3D (lib/footContact.ts): only down or lifted, never toe or heel. */
    down: "down",
    lifted: "lifted",
    leftShort: "L",
    rightShort: "R",
    showIn3d: (region: string) => `Show the ${region.toLowerCase()} in 3D`,
  },

  /** The lesson path (docs/DESIGN.md §7g: true facts only, no points or streaks). */
  path: {
    label: "Lesson path",
    learned: (n: number, total: number) => `${n} of ${total} learned`,
    learnedTag: "learned",
    steps: { watch: "Watch", slow: "Slow", build: "Build up", full: "Full speed" },
    stepSub: { watch: "1×, once", slow: "0.5×, 3 loops", build: "0.5× to 1×", full: "1×" },
    yourTurn: "Your turn",
    yourTurnHint: "Keep counting and do it yourself.",
    gotIt: "Got it",
    again: "Again",
    next: (label: string) => `Next: ${label}`,
    learnedDone: (label: string) => `${label} learned`,
    allDone: "All learned. Run the whole dance.",
    check: (label: string) => `How was ${label}?`,
    stepGroup: "Steps for this 8-count",
  },

  modes: { group: "How to practise", lesson: "Lesson", practise: "Just practise" },

  transport: {
    play: "Play",
    pause: "Pause",
    playUnit: (label: string) => `Play ${label}`,
    prev: "Previous",
    next: "Next",
    speed: "speed",
    speedLabel: "Speed",
    building: "building up",
    loopThis: "Loop this",
    wholeDance: "Whole dance",
    loopOn: "Loop on",
    loopOff: "Loop off",
    mirrorOn: "Mirror on",
    mirrorOff: "Mirror off",
    followOn: "Follow on",
    followOff: "Follow off",
    back: "All lessons",
  },

  views: {
    group: "View",
    video: "Video",
    overlay: "On video",
    threeD: "3D",
    angle: "Angle",
    addAngle: "Add an angle",
    removeAngle: "Remove this angle",
    inset: "Second angle",
    insetOff: "No second angle",
    closeups: "Close-ups",
    dancer: "Dancer",
  },

  /**
   * Count 1 correction. The beat tracker finds beats, not downbeats, so count 1 is
   * often off by whole counts; fixing it has to be one tap, not a settings page.
   */
  countOne: {
    tap: "Tap on 1",
    tapHint: "Tap while it plays, on a 1 you hear",
    earlier: "−1",
    later: "+1",
    earlierLabel: "Count 1 one count earlier",
    laterLabel: "Count 1 one count later",
    guess: "Count 1 is a guess",
    fixed: (n: number) => `Count 1 moved ${n > 0 ? "later" : "earlier"}`,
    heading: "Count 1",
  },

  dancers: {
    title: "Who are you learning?",
    lead: "Each body takes its dancer's colour. The counts stay the same when you switch.",
    name: (n: number) => `Dancer ${n}`,
    side: { left: "on the left", middle: "in the middle", right: "on the right" },
    start: "Start learning",
    change: "Change dancer",
    marker: (n: number) => `Dancer ${n}`,
  },

  help: {
    button: "About this view",
    noFloor: "No floor: feet not visible in this clip.",
    clipped: "The dancer is at the edge of the shot, so the crop stops there.",
    estimated: "Angles other than the camera's are estimated from the tracked body.",
    keys: "Keys: space play, arrows a count, shift and arrows an 8-count, M mirror, S speed, T tap on 1.",
    counts: "Counts and parts",
  },

  phone: {
    prop: "Prop it up",
    propSub: "hands-free",
    exitProp: "Leave prop it up",
    countInOn: "Count-in on",
    countInOff: "Count-in off",
    autoOn: "Auto next 8",
    autoOff: "Stay on this 8",
    hint: "Tap to play. Swipe up for the next 8. Hold for half speed.",
    hold: "Half speed while you hold",
    paused: "Paused",
    more: "More",
    less: "Less",
    zoneBack: "Back an 8-count",
    zoneNext: "Next 8-count",
  },

  menu: {
    button: "More for this lesson",
    removeMine: "Remove from my lessons",
    report: "Report or remove this video",
  },

  install: {
    lead: "Practising on this phone? Keep the lesson on your home screen.",
    ios: "Tap Share, then Add to Home Screen.",
    android: "Add to home screen",
    dismiss: "Not now",
  },
};

/**
 * /lessons. There are no accounts (OPEN-DECISIONS D5), so "my" lessons are the
 * ones this browser opened, kept in localStorage (lib/myLessons.ts). The page
 * says so in its subtitle rather than implying a synced library.
 */
export const myLessons = {
  title: "My lessons",
  subtitle: "Saved on this device. Lessons you open here are listed here, and nowhere else.",
  empty: "No lessons on this device yet. Add a clip to make one, or open a lesson link.",
  emptyLink: "Add a clip",
  remove: "Remove from my lessons",
  removeNote: "This only takes it off this list. The lesson itself stays up.",
  dancers: (n: number) => (n === 1 ? "1 dancer" : `${n} dancers`),
  duration: (s: number) => `${Math.round(s)} s`,
  opened: "Last opened",
  examplesHeading: "Examples",
  examplesNote: "Built-in samples made from generated test data, not from anyone's video.",
};

/**
 * The takedown dialog (components/RemoveLessonDialog.tsx). The body line is
 * the owner's wording, and every word of it is what
 * services/motion-api `POST /jobs/{job_id}/removal` does: it deletes the source
 * video and every 3D artifact at once, for the one shared lesson, and leaves
 * only a tombstone. It cannot be undone because nothing is kept to undo from.
 */
export const removal = {
  menuItem: "Report or remove this video",
  title: "Report or remove this video",
  body: "This deletes the video and the 3D lesson for everyone who has the link. It can't be undone.",
  relationshipLegend: "Which is closest?",
  relationships: {
    i_am_in_it: "I am in this video",
    i_own_the_rights: "I own the rights to this video",
    other: "Something else",
  },
  reasonLabel: "Anything else to add (optional)",
  submit: "Delete for everyone",
  submitting: "Deleting",
  cancel: "Cancel",
  close: "Close",
  pickOne: "Pick the option that fits best, then delete.",
  failed: "The removal did not go through. Check your connection and try again.",
  doneTitle: "Removed",
  done: "The video and the 3D lesson are deleted. Anyone opening the link now sees that it was removed.",
};

/**
 * /privacy. Every sentence here is checked against code; the file and line
 * that backs each one is listed next to it. If the code changes, the sentence
 * changes in the same commit (DESIGN.md §7h). No legal terms of use here —
 * that is a lawyer's text, not ours to invent.
 */
export const privacy = {
  title: "Privacy",
  intro:
    "What stepwise keeps, where it lives, and how it goes away. There are no accounts: we never ask for your name or email address.",
  sections: [
    {
      heading: "When you add a clip, we store",
      items: [
        // uploads Volume /{clip_id}.mp4 and R2 video key — api._store_and_dispatch, storage.py
        "The video you uploaded, or the video we fetched from the link you pasted.",
        // {clip_id}_track{n}.glb, motion-result.json.gz, beats.json — retention.clip_artifact_paths
        "What we build from it: a 3D body for each dancer, and the lesson data the viewer plays — timings, poses, hand and foot close-up areas, and counts proposed from the music.",
        // performance.json, job-status/job-meta, jobs table — modal_app.py, jobstore.py
        "Processing records: how the job went and how long each step took.",
        // fingerprints/index.json: sha256 + frame hashes, source_key — fingerprint.py, api._store_and_dispatch
        "A fingerprint of the video (a checksum and small frame hashes) and, for a pasted link, which post it came from. This is how the same video added twice becomes one lesson.",
        // {clip_id}.last-access.json — api._touch
        "When the lesson was last opened.",
      ],
    },
    {
      heading: "One lesson per video",
      items: [
        // api.upload_clip / ingest_clip_link dedupe hits return the existing clip_id
        "If a video is recognised as one that is already a lesson, whoever adds it gets that same lesson and link. So there is one copy, and removing it removes it for everyone who has the link.",
      ],
    },
    {
      heading: "Kept only in your browser",
      items: [
        // lib/myLessons.ts, lib/structure.ts, lib/reveal.ts — localStorage, never sent
        "My lessons (with a small picture from each video's first frame), the counts and parts you set, and whether a lesson has already done its opening turn. These are stored by your browser on this device and are never sent to us. Clearing this site's data in your browser deletes them.",
        // LessonLoader 410 -> forgetLesson
        "If a lesson is removed, its entry leaves My lessons the next time its link is opened on this device.",
      ],
    },
    {
      heading: "No accounts, and how limits work",
      items: [
        // ratelimit._ip_hash, 001_init.sql events has no ip column
        "To stop one person using up the day's processing, each new lesson and each removal is counted against a keyed hash of your IP address. The key changes every day, so one day's counts cannot be matched to the next. The address itself is not written to our database, and these counts are kept after a lesson is deleted.",
        // wrangler.jsonc (Cloudflare Worker), modal_app.py, storage.py (R2), layout.tsx (Fontshare)
        "The site runs on Cloudflare, processing runs on Modal, and files are stored on Modal and Cloudflare. Fonts load from Fontshare. Like any web host, these services see your requests, including your IP address.",
      ],
    },
    {
      heading: "Error reports",
      items: [
        // observability.py scrub(), lib/scrub.ts, instrumentation-client.ts
        "When something breaks, an error report goes to Sentry, our error tracker. Before it leaves, links, email addresses and @handles in it are replaced with placeholders. Addresses of pages on this site are kept, without anything after the question mark, so we can tell which lesson broke.",
        // api.remove_lesson -> observability.message("lesson removed", relationship, clip_id)
        "When a lesson is removed we get an alert with the lesson's id and which option was picked. The words you typed are not in it.",
      ],
    },
    {
      heading: "How long we keep it",
      items: [
        // retention.TTL_DAYS == 180, modal_app.sweep_expired daily
        "We keep the clip while the lesson exists. Lessons nobody opens for six months are deleted, and a removal request deletes one straight away.",
        // retention.delete_clip tombstone {clip_id, removed_at, reason, relationship}
        "After a deletion we keep a short note that the lesson was removed — when, the option picked and anything typed — so the link can say it was removed instead of pretending it never existed.",
      ],
    },
    {
      heading: "Removing a lesson",
      items: [
        // components/RemoveLessonDialog.tsx -> POST /jobs/{job_id}/removal
        "Use Report or remove this video on the lesson, or paste the lesson's link below. It deletes the video and the 3D lesson for everyone, straight away. Anyone with the link can do it; you do not have to be the person who added the clip.",
        // no contact address exists
        "You need the lesson's link. There is no email address for requests yet.",
      ],
    },
  ],
  linkLabel: "Lesson link",
  linkPlaceholder: "Paste the link to a lesson",
  linkSubmit: "Continue",
  linkInvalid: "That is not a lesson link from this site. It looks like /lesson/ followed by an id.",
  footer: "Privacy",
};

/**
 * The navigation surface's strings, swept by the same §11 lint as everything
 * above. `packages/navigation/src/copy.ts` asked for this line in its own
 * header; it is here now that the package is actually mounted in this app.
 */
export { copy as navigation } from "../../../packages/navigation/src/copy";
