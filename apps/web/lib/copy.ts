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
    myLessons: "My lessons",
    add: "Add a clip",
  },

  hero: {
    // A2 "Count off". "Step by step" is the name, not a rule about length:
    // a loop is as long as the learner sets it (Counts and parts), never
    // "8 counts at a time". No processing time: nothing here has a job to
    // measure (see test/copy.test.ts).
    headlineLead: "Learn any dance,",
    headlineAccent: "step by step.",
    lede:
      "Loop the part that trips you up, as short or as long as you like. Slow it down, then build back up to full speed.",
    // Each one enforced in code: MAX_SECONDS in lib/submit.ts and the service,
    // process_clip.MAX_DANCERS = 6, no accounts (OPEN-DECISIONS D5).
    facts: ["Up to 60 seconds", "1 to 6 dancers", "Free, no account"],
  },

  // The count-off toy beside the headline. A drawn figure at a fixed tempo,
  // not a clip and not anyone's counts, and it says so.
  toy: {
    caption: "A drawn figure, not a real dancer. Try the controls.",
    build: "Build up",
    speed: (rate: number) => `${rate}×`,
    mirrorOn: "Mirror on",
    mirrorOff: "Mirror off",
  },

  // The on-video demo. No cleared clip exists yet (evaluation/clips.yaml's
  // demo-public slot is empty; the testing clips are rights: untested), so the
  // stage is an empty placeholder that says so. components/front/Demo.tsx
  // holds the one constant a cleared clip drops into.
  demo: {
    heading: "Your video, with the body on top.",
    // DESIGN.md §7h case 1: tracked through a turn is the honest claim, and
    // the other angles are labelled estimated in the lesson.
    body:
      "The real clip plays underneath, so the timing and style stay the dancer's own, with the 3D body drawn on top. When the dancer turns away the body is still tracked, so you can turn to another angle, estimated from that body, and see what their arms were doing.",
    onVideo: "On video",
    placeholder: "Demo clip coming soon",
    play: "Play the demo",
    open: "Open this lesson",
  },

  // What happens after you add a clip. Steps, not times: the only honest
  // time is the processing screen's, extrapolated from the live job.
  wait: {
    heading: "Your clip plays while we build the 3D.",
    body: "Slow it down or mirror it while you wait. You can close the tab and come back: the link keeps working.",
    steps: [
      { label: "Clip", body: "Your video plays straight away." },
      { label: "Dancers", body: "Each dancer is found and marked, frame by frame." },
      { label: "3D body", body: "A body is built for each dancer." },
      { label: "Lesson", body: "Loop any part, at any length. Your speed carries over." },
    ],
    // In the lesson today: the On video view, the 3D view's orbit (estimated
    // off the camera axis), loop handles under Counts and parts, the 0.5x to
    // 1x transport, Build up, Mirror, and the dancer picker.
    featuresLabel: "While you learn",
    features: [
      ["3D body on your video", ""],
      ["Turn to any angle", "estimated"],
      ["Loop one part, a run of parts, or all of it", ""],
      ["0.5× to 1×", ""],
      ["Build up", "faster each loop"],
      ["Mirror", ""],
      ["Switch dancers", ""],
    ] as [string, string][],
  },

  foot: {
    worksHeading: "Works best with",
  },
};

export const upload = {
  title: "Add a clip",
  choose: "Add a video file",
  drop: "or drop it here. Works for everyone.",
  or: "or",

  // The pasted-link door, shared by the landing hero and /upload
  // (components/front/LinkDoor.tsx) so the two cannot drift.
  //
  // Read docs/research/link-ingestion.md before touching the rights line
  // below. It is not the upload rights line with a word changed: a pasted
  // link is a weaker claim than a file, and the copy must not pretend
  // otherwise.
  link: {
    label: "TikTok or YouTube link",
    // Longest first; the field shows the longest that fits its width (a
    // placeholder clips, it cannot wrap). The accessible label keeps the full name.
    placeholders: ["Paste a TikTok or YouTube link", "Paste a TikTok/YouTube link", "Paste a video link"],
    submit: "Learn the dance",
    busy: "Fetching the video",
    inviteLabel: "Invite code",
    // Says who it is open to and what still works for everyone else. Not
    // "coming soon": that names a date we have not got.
    gated:
      "Links are open to invited testers while we try this out. A video file works for everyone.",

    // The rights line for links, and deliberately NOT the upload one.
    //
    // DESIGN.md §7d's line ("Only upload video you have the right to use.")
    // is addressed to someone holding a file, who at least might hold the
    // right to it. Pasting a link is a weaker claim: you are asking us to
    // fetch someone else's post, and almost nobody pasting a TikTok has any
    // right to it at all. Saying "only paste video you have the right to use"
    // would be the same sentence pretending the same thing is true, and it is
    // not.
    //
    // So this says what actually happens, and claims nothing about
    // permission. The second sentence is true because every lesson's More
    // menu has "Report or remove this video" (components/RemoveLessonDialog,
    // POST /jobs/{id}/removal), which deletes it for everyone at once, and
    // /privacy has the same form for anyone holding only the link.
    //
    // It does not say "we check", "we verify" or "we have permission" (§7h bans all three, and §12.13 lists them), and it
    // does not ask for a tick: docs/legal/rights-and-privacy.md §7a found
    // that a checkbox collects an attestation from the wrong person, since the
    // consent that matters is the dancer's and the person pasting cannot give
    // it.
    rights:
      "We fetch the video from the link and build a lesson from it. Anyone in the clip can remove the lesson from its page, straight away.",
  },

  // Failures on the link path, in the vocabulary the service actually returns
  // (services/motion-api/ingest.py). Each says what happened and what to do
  // next, and none of them states a reason we did not observe: where the
  // platform's own answer is ambiguous, the copy stops at "we could not get
  // it" rather than guessing at private, deleted or blocked.
  linkErrors: {
    unreachable: "That did not go through. Check your connection and try again.",
  },

  // Framed as what works, not what we reject (DESIGN.md §7d).
  worksBestHeading: "Works best with",
  worksBest: [
    "Filmed from the front, on one camera held still.",
    "Up to 60 seconds, with no cuts between shots.",
    "One to six dancers. You pick whose body you learn from.",
  ],

  // The rights line appears here, once, plainly (DESIGN.md §7d,
  // OPEN-DECISIONS.md D8).
  rights: "Only upload video you have the right to use.",

  // Errors say what happened and what to do, and never apologise (§11).
  errors: {
    tooLong:
      "That clip is longer than 60 seconds. Trim it to the part you want to learn and try again.",
    wrongType: "That file is not a video. Pick an mp4, mov, or webm.",
    uploadFailed: "The upload did not go through. Check your connection and try again.",
    // A 413. The service's own detail is a bare "Clip is too large.", and a
    // file can also be stopped by the host in front of it before the service
    // sees it, so this names no byte count (MAX_UPLOAD_BYTES is 200 MB, but
    // the edge may stop a file sooner).
    tooLarge: "That file is too large to upload. Export it at a smaller size and try again.",
  },

  // The one action beside each failure (components/StateScreen.tsx StateNote).
  actions: {
    myLessons: "Open My lessons",
    addFile: "Add a video file",
    chooseFile: "Choose another file",
    tryAgain: "Try again",
  },
};

/**
 * The processing screen (A2, with the owner's change of 2026-09-23): the clip
 * plays, the job reports honestly, and at success one button opens the lesson.
 *
 * No counts here. The early `milestones.counts` were often off the beat and
 * landed count 1 on the intro before the dancer starts, so practising them
 * taught the wrong 1. The counts wait for the lesson, where the learner can
 * set them. (Future: early 8-count practice once count 1 is reliable.)
 */
export const processing = {
  title: "Building your lesson.",
  subtitle: "Your clip plays here while it builds. Slow it down or mirror it if you like.",
  readyTitle: "Ready to learn.",
  readySubtitle: "Open it to loop any part, slow it down, and see the 3D body on your video.",
  open: "Start learning",

  // The big numeral is a heartbeat, not the song: it ticks at a steady rate
  // that has nothing to do with the music, and the page says so.
  heartbeat: "A steady count to wait by. It is not the music's beat.",
  heartbeatDone: "Counted in.",

  videoLabel: "Your clip, playing now",
  paused: "Paused. Tap to play.",
  soundOn: "Sound on",
  soundOff: "Sound off",

  // Each step with the result it produced. Every "done" note is a milestone
  // the service sent, never a guess from the progress fraction.
  steps: {
    clip: "Clip",
    playing: "Playing now",
    dancers: "Dancers",
    looking: "Looking frame by frame",
    dancersFound: (n: number) => (n === 1 ? "1 dancer" : `${n} dancers`),
    body: "3D body",
    frames: (done: number, total: number) => `Frame ${done} of ${total}`,
    finishing: "Finishing up",
    ready: "Ready",
    waiting: "Waiting",
  },
  waiting: "Waiting in the queue",
  // Only what the page itself does: it keeps polling (lib/jobStatus.ts). It
  // cannot see the job while it cannot reach it, so it says nothing about it.
  unreachable: "We cannot reach the job right now. This page keeps checking.",

  // DESIGN.md §7c: honest about it being a queue, not a session.
  closeable: "You can close this. The link keeps working.",
  copyLink: "Copy the link",
  copied: "Link copied",

  queued: "Still in the queue.",
  // Loose, never a false-precision countdown (DESIGN.md §7c), and only ever
  // extrapolated from this job's own progress (lib/jobStatus.ts).
  remaining: (minutes: number) =>
    minutes <= 1 ? "About a minute left." : `About ${minutes} minutes left.`,
  almostDone: "Nearly there.",

  speed: (rate: number) => `${rate}× speed`,
  mirrorOn: "Mirror on",
  mirrorOff: "Mirror off",

  failedTitle: "This clip did not make it through.",
  // A retryable failure (pipeline_error, export_error) carries the raw
  // exception text as its message. That goes to Sentry, never to the page:
  // this line is what the learner reads instead. "May": the API only says a
  // retry could plausibly succeed.
  failedRetryable: "Building the lesson stopped with an error partway through. Trying again may work.",
  // POST /jobs/{id}/retry. The API allows two, then answers retries_exhausted
  // with its own sentence, which is shown as-is.
  retry: "Try again",
  retrying: "Trying again",
  retryFailed: "That did not go through. Check your connection and try again.",
  addDifferent: "Add a different clip",
};

export const lesson = {
  /**
   * The credit on a link lesson, linking to the video it was made from
   * (GET /jobs/{id}/source; docs/legal/legal-public-learning.md §6(a)2).
   * "Original" is the video, nothing more: it does not say the creator made
   * this lesson or agreed to it. No handle in the metadata: the host only.
   */
  credit: (host: string, creator: string | null) =>
    creator ? `Original by ${creator} on ${host}` : `Original on ${host}`,
  /**
   * Opening a lesson by its link, keyed by what services/motion-api answered.
   * An unknown job_id reads as "queued" there, not 404, so a mistyped link lands
   * on `notReady` — which is why that line does not promise the lesson exists.
   */
  load: {
    loading: "Getting the dance ready",
    jobTitle: "Your dance",
    notReady: "This lesson is not ready yet.",
    notReadyBody: "Its processing page shows how it is going.",
    notReadyLink: "See how it is going",
    // 410 is written by a removal request and by the sweeper
    // (retention.TTL_DAYS = 180 since last opened) alike, so it names both.
    removed: "This lesson was removed.",
    removedBody: "Lessons are deleted when someone asks, or after six months unopened. This one is not coming back.",
    removedLink: "Go to the home page",
    notFound: "There is no lesson at this link.",
    notFoundBody: "Check the link, or add a clip to make one.",
    notFoundLink: "Add a clip",
    // Also offline: there is no service worker, so offline is a failed fetch.
    failed: "The lesson did not load.",
    failedBody: "Reload the page to try again. If this device is offline, reconnect first.",
    failedLink: "Reload the page",
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

  /**
   * The chips: the one row that drives practice, one per part (an eight until the
   * learner edits them). The tick is a true fact (these counts were looped at full
   * speed in this browser), DESIGN.md §7g — no points, no streaks.
   */
  chips: {
    group: "Parts of the dance",
    scrub: "Position in the dance",
    all: "All",
    done: "looped at full speed",
    doneCount: (n: number, total: number) => `${n} of ${total} counts at full speed`,
    next: (span: string) => `Next: ${span.toLowerCase()}`,
  },

  /**
   * The timeline: the whole dance, one tick a count, a taller one on each 1. Tap to
   * go there, drag across it to loop exactly those counts, drag a handle to adjust.
   */
  timeline: {
    label: "Position in the dance. Drag across it to loop those counts.",
    hint: "Drag across the timeline to loop any counts",
    hintFree: "Hold Alt to drag without snapping to the counts",
    clear: "Stop looping",
    section: "Section start · Loop this section",
    start: "Loop start",
    end: "Loop end",
    earlier: (edge: string) => `${edge}: half a count earlier`,
    later: (edge: string) => `${edge}: half a count later`,
  },

  /**
   * The click. Honest about what it is: our count grid, which is a guess from the music
   * until the learner sets count 1 (DESIGN.md §7h).
   */
  click: {
    toggle: "Click",
    toggleHint: "A click on each count, locked to the video",
    settings: "Click settings and volume",
    heading: "Click",
    on: "Click on",
    off: "Click off",
    counts: "Counts",
    ands: "Counts + and",
    volume: "Click volume",
    music: "Music volume",
    guess: "It clicks on our counts, a guess from the music until you set count 1.",
    yours: "It clicks on the counts you set.",
  },

  /** How many counts a chip or a preset loops. Nothing is forced to be an eight. */
  loopLen: {
    label: "Counts per loop",
    lead: "Loop",
    unit: "counts",
    all: "All",
    option: (n: number) => (n === 0 ? "Loop the whole dance" : `Loop ${n} counts`),
    fromCount: (c: number, n: number) => `Loop ${n} counts from count ${c}`,
    countHint: "Click to loop from this count. Shift-click or drag to loop just these counts.",
  },

  transport: {
    play: "Play",
    pause: "Pause",
    speedLabel: "Speed",
    speedNext: (s: number) => `Speed ${s}×. Tap for the next speed`,
    build: "Build up",
    buildHint: "Starts the loop at 0.5× and adds 0.1× each time round, up to 1×",
    more: "More",
    mirrorOn: "Mirror on",
    mirrorOff: "Mirror off",
    followOn: "Follow on",
    followOff: "Follow off",
    back: "Home",
  },

  /** The top bar: each view a toggle, every one on is a panel. */
  views: {
    group: "Views",
    video: "Video",
    videoCropped: "Video, cropped",
    overlay: "On video",
    front: "Front",
    side: "Side",
    back: "Back",
    top: "Top",
    hands: "Hands",
    feet: "Feet",
    mirror: "Mirror",
    mirrored: "mirrored",
    est: "est.",
    dancer: "Dancer",
  },

  /**
   * Count 1 correction. The beat tracker finds beats, not where the dancer's eight
   * starts, so count 1 is often off by whole counts; fixing it is one tap.
   */
  countOne: {
    tap: "Tap on 1",
    tapHint: "While it plays, press Tap on 1 as you hear a 1.",
    earlier: "−1",
    later: "+1",
    earlierLabel: "Count 1 one count earlier",
    laterLabel: "Count 1 one count later",
    guess: "is a guess",
    heading: "Count 1",
    tryAnother: "Try another 1:",
    altLabel: (shift: number) => `Count 1 ${Math.abs(shift)} ${Math.abs(shift) === 1 ? "count" : "counts"} ${shift > 0 ? "later" : "earlier"}`,
    now: (n: number) => (n ? `Count ${n}` : "Before count 1"),
  },

  dancers: {
    title: "Who are you learning?",
    lead: "Only the dancer you pick is drawn in 3D. The counts stay the same when you switch.",
    name: (n: number) => `Dancer ${n}`,
    side: { left: "on the left", middle: "in the middle", right: "on the right" },
    start: "Start",
    change: "Change dancer",
    /** A toggle (aria-pressed): the other dancers, faint and grey, for the formation. */
    everyone: "Show everyone",
  },

  help: {
    button: "About this view",
    legend: "Solid is seen. Grey and hatched is unsure. A short stub means that part is out of frame.",
    noFloor: "No floor: feet not visible in this clip.",
    clipped: "The dancer is at the edge of the shot, so the crop stops there.",
    estimated: "Angles other than the camera's are estimated from the tracked body.",
    keys: "Keys: space play, arrows a count, shift and arrows the next or previous counts, L loop, S speed, B build up, M mirror, T tap on 1.",
  },

  phone: {
    prop: "Prop it up",
    exitProp: "Leave prop it up",
    countInOn: "Count-in on",
    countInOff: "Count-in off",
    autoOn: "Auto next",
    autoOff: "Stay on these counts",
    hint: "Tap to play. Swipe up for the next counts. Hold for half speed.",
    hold: "Half speed while you hold",
    paused: "Paused",
    less: "Close",
    zoneBack: "Previous counts",
    zoneNext: "Next counts",
  },

  menu: {
    heading: "This lesson",
    removeMine: "Remove from my lessons",
    report: "Report or remove this video",
    privacy: "Privacy",
  },

  install: {
    lead: "Practising on this phone? Add this lesson to your Home Screen.",
    ios: "Tap Share, then Add to Home Screen.",
    android: "Add to Home Screen",
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
  emptyTitle: "No lessons on this device yet.",
  emptyBody: "Add a clip to make one, or open a lesson link.",
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
    under_18: "Someone in this video is under 18",
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
 * The site's own state screens: app/not-found.tsx and app/global-error.tsx.
 * global-error wraps every route, so it never says "lesson".
 */
export const site = {
  notFound: {
    title: "There is no page here.",
    body: "Check the address, or start from the home page.",
    action: "Go to the home page",
  },
  crashed: {
    title: "This page stopped working.",
    // A render crash is in this tab only: nothing on the service or in this
    // browser's storage is touched by it.
    body: "Reload to try again. Your lessons and clips are not affected.",
    action: "Reload the page",
  },
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
        "My lessons (with a small picture from each video's first frame), the counts and parts you set, and whether a lesson has already done its opening turn. These are stored by your browser on this device and are never sent to us (the usage notes below carry a loop's length and start and how far count 1 moved, not your saved counts and parts). Clearing this site's data in your browser deletes them.",
        // LessonLoader 410 -> forgetLesson
        "If a lesson is removed, its entry leaves My lessons the next time its link is opened on this device.",
      ],
    },
    {
      heading: "No accounts, and how limits work",
      items: [
        // ratelimit._ip_hash, 001_init.sql events has no ip column
        "To stop one person using up the day's processing, each new lesson and each removal is counted against a keyed hash of your IP address. The key changes every day, so one day's counts cannot be matched to the next. The address itself is not written to our database, and these counts are kept after a lesson is deleted.",
        // wrangler.jsonc (Cloudflare Worker), modal_app.py, storage.py (R2), layout.tsx (Google Fonts, Fontshare)
        "The site runs on Cloudflare, processing runs on Modal, and files are stored on Modal and Cloudflare. Fonts load from Google Fonts and Fontshare. Like any web host, these services see your requests, including your IP address.",
      ],
    },
    {
      heading: "Usage counts",
      items: [
        // lib/analytics.ts EVENTS, LessonViewer.tsx, ProcessingScreen CopyLink -> POST /api/events
        "To learn which parts of stepwise help people practise, the lesson page sends us a short note when you open a lesson, for every 30 seconds of playing, and when you make a loop (its length, where it starts and how you made it), change the speed, Build up, the click or a view, correct count 1, pick a dancer, or copy a link. Each note has the control, its setting and the lesson's id. Nothing you type, no mouse movements, no screen recordings, nothing from the video.",
        // analytics.CLIENT_EVENTS lesson_opened.ref, referrerHost()
        "When you open a lesson we note which website sent you there: its name only, not the page.",
        // api._created (job_created), analytics.record_finished (job_finished)
        "On our side we count each clip added (how long it is, file or link) and how each job ended: finished or which error, how many retries, how long it took, and how many dancers.",
        // analytics.day_hash, migrations/002 analytics_salts; no storage in lib/analytics.ts
        "Nothing is stored in your browser for this. We group the notes by a keyed hash of your IP address and browser name. The key is random, is used for one day and is then deleted, so we can count visitors each day but cannot link one day to the next. The address itself is not saved.",
        // lib/analytics.ts optedOut()
        "If your browser sends Global Privacy Control or Do Not Track, no notes are sent.",
        // analytics.rollup from modal_app.sweep_expired
        "In our own database the notes are kept for 13 months, then reduced to daily totals and deleted.",
        // analytics.forward (server-side, after ingest), POSTHOG_KEY in modal_app.py POSTHOG_SECRET; no SDK in apps/web
        "To draw charts of these counts we pass a copy of the same notes to PostHog, an analytics company hosted in the US, which processes them for us. It gets exactly what is in each note plus the day's keyed hash, from our server, never from your browser: no cookies, no PostHog code on the page, and not your IP address or browser name. We tell it not to build a profile of you or look up your location. PostHog keeps its copy under its own retention period.",
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
        // privacy.contact: a free Gmail forwarding to the owner until the domain exists
        "You need the lesson's link. For anything else (a rights claim, a question, or if the button does not work) email stepwisedance.help@gmail.com. A person reads it and replies by hand.",
      ],
    },
  ],
  linkLabel: "Lesson link",
  linkPlaceholder: "Paste the link to a lesson",
  linkSubmit: "Continue",
  linkInvalid: "That is not a lesson link from this site. It looks like /lesson/ followed by an id.",
  footer: "Privacy",
  contact: "stepwisedance.help@gmail.com",
  // Shown where a video is handed over (the paste box and the upload page), so
  // the promise is read at the moment it matters, not only in the footer.
  // Every clause is code: retention.TTL_DAYS == 180 since last open (the same
  // fact as the /privacy sentence), and "Report or remove this video" on every
  // lesson deletes it for everyone at once. No accounts, so nothing else to say.
  atHandover: "We keep a clip only while its lesson gets used: six months unopened and it is deleted. Anyone in it can remove it from the lesson page.",
  atHandoverLink: "How we handle videos",
};

/**
 * The navigation surface's strings, swept by the same §11 lint as everything
 * above. `packages/navigation/src/copy.ts` asked for this line in its own
 * header; it is here now that the package is actually mounted in this app.
 */
export { copy as navigation } from "../../../packages/navigation/src/copy";
