# Keeping the real audio: every legitimate path, compared

> **This is research, not legal advice.** Neither the author nor the builder is a lawyer. It builds
> on [`system-review-2026-09.md`](system-review-2026-09.md) (SR), [`legal-public-learning.md`](legal-public-learning.md)
> (LPL), [`rights-and-privacy.md`](rights-and-privacy.md) (R&P) and
> [`../research/link-ingestion.md`](../research/link-ingestion.md). Sources were read on 2026-09-25;
> platform terms change without notice. §9 lists what a lawyer has to confirm; §10 lists what I
> could not verify.

**The owner's question.** The lesson has to keep the actual song, because "the dance has to work
with the audio". Is there a legitimate way to keep the original audio (and video)? Could we
partner with TikTok, or sell to them?

## 1. One-screen answer

- **There is no licence you can buy this year that lets stepwise host and stream a trending
  commercial song, slowed and looped, to anyone with a link.** The only real licence is a direct
  label deal plus publisher deals. Those cost tens of thousands of dollars up front and take months
  to years, and even funded companies lose tracks when deals lapse (§4).
- **But three legitimate ways keep the real audio in the lesson, and together they cover the
  product.**
  1. **Embed-first.** The original video *with its audio* plays inside TikTok's or YouTube's own
     player, under their licences. YouTube supports slow-down (`setPlaybackRate`, 0.25–2×); TikTok's
     player does not. On TikTok links, the real song plays at 1×, and slow practice uses our 3D with
     the click (§2).
  2. **"Your copy stays on your phone."** The learner saves the TikTok using TikTok's own download
     button and adds it. We process it and keep only the 3D and the counts. **The lesson plays the
     audio from the file on the learner's own device**, at any speed, with pitch preserved. This is
     how practice apps like Anytune and Moises slow commercial music with no label deal: the user
     supplies the audio. It is the only path that keeps *real audio at 0.25–1.25×* for TikTok clips
     without a licence (§3).
  3. **Uploads others watch, hosted under DMCA §512**: the paradigm "stored at the direction of a
     user" case. It is defensible once the agent, Terms and a repeat-infringer policy exist. It is
     not a licence, and it weakens if we *encourage* uploading hit songs (§5).
- **TikTok partnership: not a door that is open today.** There is no partner programme for
  education or dance apps. The developer terms forbid copying content and "compet[ing] with or
  replicat[ing]" TikTok. The realistic integrations are small: Share Kit and Green Screen Kit
  (send the learner's practice video *back* to TikTok) and Effect House. **Selling to TikTok is not
  a plan.** ByteDance buys scale or core tech and clones small apps, and TikTok already has
  slow-motion playback (§6).
- **Labels are the long-shot upside.** Labels *want* dance trends, and UMG's Aug 2026 deal with
  Hook shows a major will license slowing and manipulating tracks inside an app, after two years of
  work. A per-track "official lesson" promo licence for a label-seeded dance is plausible *once there
  is traction* (§4, §7).

**Recommendation in one line:** keep today's model for the invite beta. At public launch, ship
**embed-first plus "your copy stays on your phone"**. Pursue label promo licences and TikTok
Share Kit at scale. Never build a hosted catalogue of trending songs without a label licence.

### Comparison

| Path | Real audio? | Slow 0.25–1.25× with the song? | Video? | Who licenses the music | Cost / time | Legal strength | Stage |
|---|---|---|---|---|---|---|---|
| **A. Today: fetch + host + stream** | Yes | Yes | Yes | Nobody | $0 | Weak. No licence, ToS breach on fetch, §512 thin for copies we fetched (SR §4) | Invite beta only |
| **B. Embed-first, TikTok** | Yes, in TikTok's player | **No**: 1× only. Slow practice = 3D + click, song muted | Yes (official player) | TikTok, under its licences | Low build cost | Strong for playback. The fetch for the GPU pass is still a ToS issue (§2.4) | Public launch |
| **C. Embed-first, YouTube** | Yes | **Yes**: `setPlaybackRate` 0.25–2× | Yes, never overlaid | YouTube | Low | Strong for playback. The fetch is still a ToS issue and possibly §1201 (SR row 1) | Public launch |
| **D. Your copy stays on your phone** (user's own file, played on-device) | Yes | **Yes** | Yes, on the learner's device | Nobody needed for a private playback of the user's own copy | Medium build (local storage, a second audio source) | Strong: no public performance or distribution by us. Processing copy is transient | Public launch |
| **E. Hosted upload, shared by link, §512** | Yes | Yes | Yes | Nobody (uploader's responsibility) | $6 agent + lawyer-reviewed Terms | Medium. Safe harbour, not a licence. Weakens with inducement or curation | Beta (agent now) → public |
| **F. Creator opt-in, "Made with permission"** | Only if the song is the creator's own (original sound) | Yes, for original sounds | Yes | The creator, *for their own video and choreography only* | Outreach time | Strong for video. **Does not license a label's song** | Public → library |
| **G. Label promo licence per track** | Yes | Yes, if the licence says so (Hook's does) | Yes | Label + publishers | Negotiated. Needs traction | Strong | Scale |
| **H. Aggregator catalogue** (Feed.fm, Tuned Global, Songtradr/7digital) | Yes, for *their* catalogue | Depends on the licence | Only our own content | Aggregator | Monthly subscription, prices not public | Strong, but it cannot follow whatever song is trending | Scale, if ever |
| **I. Production music** (Epidemic, Artlist) | No: not the trend's song | n/a | n/a | Library | Cheap | Strong, but useless for "the dance has to work with *the* audio" | Marketing only |
| **J. TikTok partnership / acquisition** | Would be ideal | Would be ideal | Yes | TikTok | Years; needs scale | n/a | Not a plan |

## 2. Embed-first: what the platforms' players actually allow

### 2.1 TikTok Embed Player

The player is `https://www.tiktok.com/player/v1/{video_id}`. It is controlled by `postMessage`
([Embed Player docs](https://developers.tiktok.com/doc/embed-player)).

- **Parameters:** `controls`, `progress_bar`, `play_button`, `volume_control`,
  `fullscreen_button`, `timestamp`, `loop` (default 0), `autoplay` (default 0), `music_info`,
  `description`, `rel`, `native_context_menu`, `closed_caption`, `muted`.
- **Commands:** `play`, `pause`, `seekTo`, `mute`, `unMute`.
- **Events:** `onPlayerReady`, `onStateChange`, `onCurrentTime` (current time and duration),
  `onMute`, `onVolumeChange`, `onPlayerError`.
- **There is no playback rate.** Video.js's wrapper confirms this: "No playback rate". It also
  reports that the player is built lazily and "silently drops commands" until playback starts,
  and that there is no command to set the volume ([Video.js tiktok-video](https://videojs.org/docs/framework/html/reference/tiktok-video)).
- The embed shows "the video creator, video description and background sound". A video removed
  in the app disappears from the embed too ([Embed Videos](https://developers.tiktok.com/docs/en/embed-videos)).

**Terms.** The embed player is part of TikTok's "Services" (US Terms §1, last updated 2026-07-15,
operator TikTok USDS Joint Venture LLC; [US Terms](https://www.tiktok.com/legal/page/us/terms-of-service/en)).
The Developer Terms (updated 2025-12-26; [Developer Terms](https://www.tiktok.com/legal/page/global/tik-tok-developer-terms-of-service/en))
forbid:
- altering the developer services (§III.3(a));
- obscuring proprietary notices (§III.3(n));
- superimposing branding on developer content (§III.3(t));
- using the services "to compete with or replicate any TikTok Services" (§III.3(p)).

Nothing forbids placing our own 3D *beside* the player and following its time.

**Don't draw on top of the embed.** A ghost or skeleton overlay drawn across the TikTok iframe
risks "alter" and "obscure". Keep our layers in their own panel.

**What TikTok's music licence says.** Sounds are licensed to users for videos "shared only within
the Platform". Use outside it needs rights "directly from all necessary rights holders"
([Music Terms](https://www.tiktok.com/legal/page/global/music-terms-eea/en)). This matters in two
ways:
- **The embed is the platform's own sharing feature.** That is why embed-first is clean.
- **Downloading the audio and hosting it ourselves is not covered.** No TikTok licence reaches us.

### 2.2 YouTube IFrame Player (including Shorts)

The API has `seekTo`, `getCurrentTime`, `setPlaybackRate` and `getAvailablePlaybackRates`.
`setPlaybackRate` is a "suggested" rate with no guarantee; you confirm it with
`onPlaybackRateChange` ([IFrame API](https://developers.google.com/youtube/iframe_api_reference)).
A Short embeds as `/embed/{id}`.

**Policies** ([Developer Policies](https://developers.google.com/youtube/terms/developer-policies);
[Required Minimum Functionality](https://developers.google.com/youtube/terms/required-minimum-functionality)).

Forbidden:
- anything that would "separate, isolate, or modify the audio or video components". So no
  audio-only lesson with the video hidden, and no background playback;
- anything that would "download, import, backup, cache, or store copies";
- any overlays "in front of any part of a YouTube embedded player".

Required:
- a viewport of at least 200 × 200 px;
- autoplay only while more than half of the player is visible;
- "must not make changes to the YouTube player that are not explicitly described by the API
  documentation". `setPlaybackRate` *is* described, so slowing through the API is the sanctioned
  route.

Also note the "significant independent value" test (§I.1) and the rule on ads beside API data
(§G.1.d). Our 3D and counts are the independent value.

### 2.3 Instagram

Meta made the oEmbed endpoints tokenless on 15 June 2026 (secondary source:
[Spotlight](https://spotlightwp.com/instagram-embed-wordpress/); [Meta oEmbed docs](https://developers.facebook.com/docs/instagram-platform/oembed/)).
The embed has **no JavaScript playback API**: no seek, no time events, no rate. Reels often click
through to instagram.com. An Instagram lesson can show the embed as "the original", but it cannot
sync to it. Treat Instagram as link-and-credit only.

### 2.4 What an embed-first lesson looks like

- **Full speed, TikTok or YouTube:** the real video and audio in the official player, with our 3D
  and count numerals in a panel beside it (not over it). The panel follows `onCurrentTime` /
  `getCurrentTime`.
  - TikTok's time events are coarse compared with today's `requestVideoFrameCallback` clock
    (`apps/web/components/lesson/hooks.ts`). So the 3D interpolates on `performance.now()`
    between events and re-snaps on each one.
  - Expect roughly tens of milliseconds of drift, not frame-exact sync. **Measure this before
    committing to it** (§10).
- **Loops (A-B snapped to counts):** `seekTo(A)` on reaching B. That works on both players, but a
  loop point lands on a keyframe on YouTube, and TikTok needs a warm-up play first.
- **Slow practice, YouTube:** `setPlaybackRate(0.25–1)`. The real song plays slowed, pitch handled
  by YouTube. This is most of today's product.
- **Slow practice, TikTok:**
  - the embed is paused or muted at the loop start;
  - our 3D plays at 0.25–1× with our metronome on the count grid;
  - a "Hear it at full speed" button plays the loop in the embed at 1×.

  This is honest, and it is the trade the SR accepted. **It does not meet the owner's bar of
  "the song at 0.5×". Path D does.**
- **Mobile:** unmuted autoplay needs a user gesture (browser policy). The TikTok embed ignores
  commands until it has started playing. The first tap must start the embed, not our 3D.
- **What embed-first does not fix:** our GPU pass still needs the file. Fetching it with yt-dlp is
  still the ToS breach in SR row 1, even if the copy is transient. The Display API returns
  embed links, not files, and TikTok's developer products do not hand third parties video files.
  Path D's "the learner downloads it themselves" is the clean fetch.

## 3. Path D: "your copy stays on your phone"

The practice-app model. Anytune, Moises and Transcribe! slow commercial songs with no label
deals because the user brings a file they already have. The app never distributes or publicly
performs it. Applied to stepwise:

1. **The learner gets the file legitimately.** TikTok's own "Save video" works when the creator
   has allowed downloads. It gives a watermarked file the learner holds under TikTok's terms for
   personal use. (link-ingestion §6 already names this as the first-party alternative.)
2. **The learner adds it** through the upload path. We process it (3D, beats, counts), which is a
   transient copy made at the user's direction. We keep **only derived facts**, and delete the
   uploaded MP4 once processing succeeds.
3. **The lesson plays the audio (and video) from the learner's own device.** The browser holds the
   file in IndexedDB or the Origin Private File System. It plays with `playbackRate` 0.25–1.25× and
   `preservesPitch`, exactly as `LessonViewer.tsx` does today, but from a local blob instead of R2.
   The server never streams it.
4. **Someone else opening the lesson link** gets the embed (path B/C) plus the 3D. They can add
   their own copy to unlock slowed audio.

**Why this is strong.** A person privately playing their own copy on their own phone is not a
*public* performance (§106(4)/(6) cover public performance only). We send nothing, so we
distribute and perform nothing. The fair-use question moves from "a startup streaming whole songs"
to "a person slowing a song they hold, for practice", which is the classic personal-use case.

**What is still exposed:**
- the transient server copy during processing (§512(c) plus the uploader's representation; short
  retention);
- whether the "Save video" file's licence covers use in another app (TikTok's personal-use terms;
  a lawyer question);
- clips whose creators disabled downloads, which this path cannot serve.

**Cost.**
- Browser storage can be evicted, so show "re-add your video" gracefully.
- The iOS Safari storage quota and eviction rules need a test.
- The lesson needs two sources: a local file when present, else the embed.

## 4. Licensing the music ourselves (paths G, H, I)

**What is needed.** Streaming a commercial recording on demand, synced to our visuals, needs:
- **the master** (the label) *and* **the composition** (every publisher that owns a share);
- sync or synchronisation-style rights, plus reproduction/mechanical and public performance.

The §114 statutory licence covers only *non-interactive* digital radio. Looped, seekable,
on-demand playback is interactive, so labels license directly. PROs (ASCAP, BMI, SESAC, GMR)
license **public performance of the composition only**: never the master, never sync.

**Time-stretching.** Slowing a track is playback, not a new arrangement, but labels treat
"manipulating" a recording as a right to be granted. UMG's Aug 2026 Hook deal lets artists switch
creative tools on or off *per song*
([Variety](https://variety.com/2026/digital/news/hook-ai-powered-music-remixing-app-strikes-umg-deal-1236838121/);
[Music Ally](https://musically.com/2026/08/20/remix-startup-hook-lands-umg-deal-after-two-year-collaboration/):
"after two-year collaboration"). Any deal must name slow-down and looping explicitly.

**Precedents:**
- **Peloton.** Publishers sued in 2019 over songs used in classes without sync licences, and
  settled in 2020 (SR row 9; [Billboard](https://www.billboard.com/pro/peloton-nmpa-music-publishers-legal-costs-settlement-49-million/)).
  This is the closest fact pattern to ours: music inside instructional video.
- **STEEZY** (dance classes). It holds UMG and WMG deals but "hasn't been able to come to an
  agreement to renew one", so it pulled classes and re-uploaded them without music
  ([STEEZY help](https://steezy.zendesk.com/hc/en-us/articles/360061629151-Why-is-there-no-music-in-some-of-the-classes-I-am-taking);
  [class removal notice](https://milled.com/steezy/class-removal-and-republishing-update-YWHqm2XBV9KhlzIY)).
  This is our category, funded, and it still lost music.
- **Just Dance+.** 56 routines were removed on 3 Sep 2026 because "licensing agreements [were]
  coming to an end" ([NME](https://www.nme.com/news/gaming-news/just-dance-is-losing-56-songs-from-its-library-and-fans-are-angry-3960929)).
- **Hook.** A licensed remix app with UMG (Aug 2026), reached after two years and 30+
  artist campaigns (above).

**Aggregators.**
- Feed.fm sells "pre-cleared major-label" music to fitness, wellness and education apps. Its
  Feed Clips product is 60-second clips of popular songs for video tools. Pricing is a monthly
  subscription that is not published ([Feed.fm major-label](https://www.feed.fm/major-label-music);
  [pricing](https://www.feed.fm/pricing-page)).
- Tuned Global and Songtradr (which absorbed 7digital) are similar B2B catalogues.
- **None of them guarantees that *this week's* TikTok sound is in their catalogue.** None
  publishes whether slow-down is licensed.
- Epidemic, Artlist and Musicbed are production music. They are fine for marketing (SR row 13) and
  useless for learning a trend to its song.

**Cost and time.** The research pass reported label minimums in the tens of thousands of dollars,
processing or legal cost of roughly $25k or more, and timelines up to about two years. I could not
confirm these figures from a primary source. Treat them as order-of-magnitude.

**Verdict.** Not for a pre-revenue solo project. Revisit at scale, per track, through label
marketing (§7) rather than as a catalogue.

## 5. Safe harbour and fair use, honestly

**DMCA §512(c)** protects a host from damages for material "stored at the direction of a user".
It extends to automated access functions like transcoding and streaming (*UMG v. Shelter Capital*,
9th Cir. 2013; [Justia](https://law.justia.com/cases/federal/appellate-courts/ca9/09-55902/09-55902-2013-03-14.html)).
Our slow-down happens in the viewer's browser (`playbackRate`), so no new copy is made.

It requires:
- a designated agent (tracker 10);
- expeditious removal (done);
- no actual or red-flag knowledge;
- no direct financial benefit where we have the right and ability to control;
- a reasonably implemented repeat-infringer policy (§512(i); tracker 11 and 13).

**The warning.** In *Capitol Records v. Vimeo* (2d Cir., Jan 2025; amended Sep 2025), Vimeo kept
its safe harbour over "lip-dub" videos with unlicensed music. The court said, though, that there is
"force in the argument that encouraging users to make infringing lip-dubs should trigger
forfeiture". The labels had waived the point, and the September amendment kept it open for
Supreme Court review ([Manatt](https://www.manatt.com/insights/newsletters/client-alert/vimeo-prevails-on-dmca-safe-harbor-defense-against);
[NatLawReview](https://natlawreview.com/article/dmca-safe-harbor-prelude-supreme-court-encore)).
A dance-trend app that markets "upload any TikTok dance" invites exactly that argument.

**So:**
- market the 3D and the counts, never "free music";
- never curate a hosted catalogue of hit songs (*Mavrix*, LPL §4);
- never run ads beside hosted audio.

*Cox v. Sony* (U.S. 2026, SR row 5) narrows contributory liability to intent. That helps a general
tool, but it does not change §512(i).

**Fair use (§107) for hosted, slowed, looped audio.** The purpose (teaching) is better than
entertainment. But *Warhol* (2023) asks whether the use shares the original's purpose, and a
learner dancing to the song is using it *as a song to dance to*. The whole song is used. The market
harm is real, because labels do license fitness and dance apps (Peloton, STEEZY, Just Dance), so
there is a licensing market we would be skipping. **Honest strength: weak** for our hosting. It is
**stronger** for a person's private practice with their own copy (path D), and strong for the
3D and counts, which carry no audio.

**Choreography plus song.** Clearing the song does not clear a registered routine (*Hanagami*,
LPL §2), and a creator's permission does not clear the song. A "Made with permission" badge must
say *what* was permitted: "video and choreography by @x, with permission; music plays from TikTok."

## 6. TikTok (and Meta, YouTube): partner, or sell?

**Developer products.**
- **Login Kit + Display API:** a user's own videos as metadata and embed links, not files.
- **Content Posting API, Share Kit and Green Screen Kit:** send content *to* TikTok.
- **Research API:** non-commercial academic use only.
- **Commercial Content API:** ads transparency.
- **Effect House:** AR effects, with a creator rewards programme.

None of these gives a third party the video or audio file. App review wants a live public site and
demo videos. The Developer Terms bar competing with or replicating TikTok (§III.3(p)), and TikTok
may suspend access "at any time" (§VI).

**Who you would be dealing with (US).** TikTok USDS Joint Venture LLC closed on 22 Jan 2026:
Oracle, Silver Lake and MGX at 15% each, ByteDance 19.9%
([Variety](https://variety.com/2025/digital/news/tiktok-us-joint-venture-deal-close-date-oracle-silver-lake-1236612315/);
[Pulse](https://www.pulse-advertising.com/resources/social-media-news/tiktok-us-deal-2026/)).
It operates the US platform and is the contracting party in the US Terms. The research pass
suggests commercial and music partnerships still run through TikTok's global business teams. Ask
both.

**Realistic integrations, cheapest first:**
1. **Share Kit / Green Screen Kit:** "post your practice to TikTok". The learner records themselves
   *in TikTok*, where TikTok's music licence applies, with our 3D as a green-screen backdrop or
   reference. This sends users *to* TikTok, which is the only thing TikTok's developer programme is
   built to reward. It also solves the silent-export problem (tracker 36).
2. **Embed Player + Display API** for users who log in with TikTok: their own and liked videos as
   lesson sources, with no pasting of links. Still no file, so pair it with path D.
3. **Effect House:** a "count overlay" or "mirror practice" effect inside TikTok. It is small, but
   it puts the brand in front of dancers.
4. **A real partnership** (TikTok supplies the file or hosts the lesson): only with traction. You
   need a public product with measurable learning retention, a clean legal posture (embed-first),
   and a named sponsor inside TikTok's creator, education or music teams. Contact routes: TikTok for
   Developers support (developers.tiktok.com), the TikTok Marketing Partners directory for
   business-development introductions, and warm introductions through label digital teams
   (§7).

**Sell to TikTok?** Not realistic as a plan.
- ByteDance has bought scale (Musical.ly, 2017) and core technology (Jukedeck, 2019; Pico, 2021).
  The research pass found no creator-tool acquisitions since 2022.
- When a small app's feature matters, TikTok builds it (TikTok Now after BeReal; Lemon8). It
  already offers slow playback in-app.
- Acquirers look for users and retention they cannot build cheaply, or a technical moat.
- stepwise's plausible moat is **monocular 3D dance reconstruction plus count-aware practice**. It
  is more likely valued as a technology licence or acqui-hire than as a product, and only after
  it is visibly used. Build for dancers; do not build for an exit to TikTok.

**Meta and YouTube.**
- Instagram embeds cannot be synced (§2.3).
- YouTube is the friendliest *player* (rate control), but its policies forbid the download our
  pipeline needs, and SR row 1 flags §1201.
- YouTube Shorts is a candidate for the same "learner records in-app" loop as TikTok (Shorts
  Remix). I did not verify any YouTube dance-learning partner programme; none surfaced.

**Other partners:**
- **STEEZY:** licensed classes, a choreographer revenue share, and the same music problem. It is a
  possible customer for the 3D engine rather than a music source.
- **Competition circuits:** they own their routines, and often their mixes are licensed for events,
  not for streaming.
- **Labels** (§7).

## 7. Labels: the one party that can say yes to the song

Labels spend marketing money to seed dance trends. That is the business reason a label might
license a track to stepwise *per campaign*: an "official lesson" for the label's own dance, with the
song, slowed, credited, linked to streaming. Hook got UMG to license manipulation by pitching fan
engagement, not royalties.

**The pitch:**
- "your dance trend, learnable in 3D, linking to the song";
- metrics the label's digital team cares about: lessons started, completions, click-outs to
  streaming, posts back to TikTok via Share Kit.

**The ask:** a short-term, royalty-free promotional licence for one master, and the publisher
split for the same use.
- **Publishers are the harder half:** several may own shares.
- Start with a label-signed artist whose song is **self-written, or from an indie label and
  publisher** (fewer parties), or with an independent artist via a distributor.

This is a scale path, not a launch dependency. Its first step costs nothing: one conversation with
one label digital-marketing person, with a demo.

## 8. Recommendation by stage

### (a) Invite beta, now

**Experience:** unchanged. The hosted video plays with its audio at 0.25–1.25×.

**Do:**
1. Register the DMCA agent. Tracker 10: it is already overdue, because uploads are open.
2. Stay small: links stay invite-only (tracker 9), and keep the credit line.
3. Build nothing that markets "the song": copy is about the 3D and counts (§5).
4. **Spike the two unknowns that decide the launch design** (a half-day each, no production change):
   - TikTok embed sync: measure `onCurrentTime` cadence and drift on iPhone Safari and Android
     Chrome;
   - on-device playback from IndexedDB/OPFS on iOS Safari, including eviction.

### (b) Public launch

**Experience:**
- **Link lesson opened by anyone:** the official TikTok or YouTube player with the real audio, and
  our 3D beside it.
  - YouTube: slow-down with the real song.
  - TikTok: full speed with the song; slow practice with 3D and click; "Hear it at full speed" for
    each loop.
- **"Practice with the song, slowed":** "Save the video from TikTok, then add it here". The lesson
  plays that file on *your* device at 0.25–1.25×. **This is the owner's product, legitimately, for
  anyone willing to do one extra tap.**
- **Uploads meant to be shared** (the learner's own filming, class recordings) stay hosted under
  §512.

**Do:**
1. Embed-first for links (tracker 14 and 23). Delete fetched MP4s after processing.
2. Build path D (local-audio lessons): a two-source clock, with the embed as fallback.
3. Terms with a user representation and a repeat-infringer policy (tracker 11), plus creator tokens
   (tracker 13).
4. Decide whether server-side fetching continues at all (SR row 1). Path D makes it optional:
   "download, then add" is the clean route.
5. No overlays on third-party players, no audio-only YouTube, no ads on lesson pages.

### (c) Scale

**Experience:** "Official lessons" with the song hosted and slowed, under a label licence, beside
creator-permitted lessons (LPL §6(c)).

**Do:**
1. Run a "Made with permission" creator opt-in (tracker 21), worded so it licenses video and
   choreography, not music.
2. Label promo licences per track (§7), with slow-down and loop named in the grant.
3. TikTok Share Kit / Green Screen Kit integration. Open a partnership conversation only with
   retention numbers in hand.
4. Only if a catalogue is ever needed: price an aggregator (Feed.fm, Tuned Global) for *background*
   practice music. It will not cover trends.

### Next-step list

| # | Who / what | Action | When |
|---|---|---|---|
| 1 | US Copyright Office DMCA directory | Register the agent ($6) | Now |
| 2 | Builder | Spike: TikTok embed time-sync drift on two phones | Beta |
| 3 | Builder | Spike: local-file lesson playback (IndexedDB/OPFS, iOS eviction) | Beta |
| 4 | Lawyer | The §9 questions below, in one session with the Terms review | Before public launch |
| 5 | TikTok for Developers | Register an app; apply for Login Kit, Display API, Share Kit and Green Screen Kit once a public site exists | Public launch |
| 6 | One label digital-marketing contact (warm introduction) | Demo plus a one-track promo-licence ask | After first retention numbers |
| 7 | Three creators whose sounds are original | Pilot "Made with permission" with their audio (they own it) | Public launch |
| 8 | Feed.fm / Tuned Global | Pricing request, for the record only | Scale |

## 9. Questions for a lawyer

1. Path D: does playing a user's own "Save video" file on their own device, inside our web app,
   make us liable for anything (performance, contributory)? Does TikTok's personal-use licence for
   saved videos permit it?
2. Is a transient processing copy of an uploaded file, deleted after processing, covered by
   §512(c)? Does it matter that the file came from TikTok's own download button?
3. Does positioning around trending dances (inherently set to label music) risk the *Vimeo*
   "encouragement" argument? What copy and features to avoid?
4. Is syncing a separate 3D panel to the TikTok embed's time events consistent with Developer Terms
   §III.3(a), (p) and (t)?
5. For a label promo licence: the minimum grant language for slow-down, looping and link sharing;
   and the publisher side.
6. Is a creator's "Made with permission" enough for their *original sound*, given that TikTok's
   terms license it to TikTok and other users?

## 10. What I could not verify

- The TikTok embed's `onCurrentTime` cadence and real sync drift. It is not documented, hence spike 2.
- Whether the TikTok embed ever mutes music that is licensed in-app. Secondary sources show only
  in-app muting for unlicensed or business-account music.
- Label deal minimums, processing fees and timelines (tens of thousands of dollars, about $25k or
  more, up to about 2 years): reported by the research pass without a primary source.
- Aggregator prices and whether they license slow-down: not published.
- TikTok's in-app slow playback, and the claim of "no creator-tool acquisitions since 2022":
  research pass, not independently checked.
- Which TikTok entity signs music or commercial partnerships in the US after the JV.
- The Instagram tokenless oEmbed change (secondary source only).
- *UMG v. Shelter Capital*, *Mavrix* and the Peloton history are cited from earlier docs and
  summaries, not re-read in full.

## 11. Sources

**Platforms**
- TikTok Embed Player — https://developers.tiktok.com/doc/embed-player
- TikTok Embed Videos — https://developers.tiktok.com/docs/en/embed-videos
- TikTok Developer Terms (2025-12-26) — https://www.tiktok.com/legal/page/global/tik-tok-developer-terms-of-service/en
- TikTok Terms (US, 2026-07-15) — https://www.tiktok.com/legal/page/us/terms-of-service/en
- TikTok Music Terms (Jul 2025) — https://www.tiktok.com/legal/page/global/music-terms-eea/en
- TikTok Content Sharing Guidelines — https://developers.tiktok.com/docs/en/content-sharing-guidelines
- Video.js TikTok wrapper notes — https://videojs.org/docs/framework/html/reference/tiktok-video
- YouTube IFrame API — https://developers.google.com/youtube/iframe_api_reference
- YouTube Developer Policies — https://developers.google.com/youtube/terms/developer-policies
- YouTube Required Minimum Functionality — https://developers.google.com/youtube/terms/required-minimum-functionality
- Meta oEmbed — https://developers.facebook.com/docs/instagram-platform/oembed/ ; tokenless change — https://spotlightwp.com/instagram-embed-wordpress/
- TikTok US JV — https://variety.com/2025/digital/news/tiktok-us-joint-venture-deal-close-date-oracle-silver-lake-1236612315/ ; https://www.pulse-advertising.com/resources/social-media-news/tiktok-us-deal-2026/

**Music**
- Hook × UMG (Aug 2026) — https://variety.com/2026/digital/news/hook-ai-powered-music-remixing-app-strikes-umg-deal-1236838121/ ; https://musically.com/2026/08/20/remix-startup-hook-lands-umg-deal-after-two-year-collaboration/
- STEEZY music — https://steezy.zendesk.com/hc/en-us/articles/360061629151-Why-is-there-no-music-in-some-of-the-classes-I-am-taking ; https://milled.com/steezy/class-removal-and-republishing-update-YWHqm2XBV9KhlzIY ; https://www.billboard.com/pro/steezy-dance-app-choreographers-credit-revenue-viral-trends/
- Just Dance+ removals — https://www.nme.com/news/gaming-news/just-dance-is-losing-56-songs-from-its-library-and-fans-are-angry-3960929
- Peloton / NMPA — https://www.billboard.com/pro/peloton-nmpa-music-publishers-legal-costs-settlement-49-million/
- Feed.fm — https://www.feed.fm/major-label-music ; https://www.feed.fm/pricing-page

**Law**
- 17 U.S.C. §512 — https://www.law.cornell.edu/uscode/text/17/512
- *UMG v. Shelter Capital*, 718 F.3d 1006 (9th Cir. 2013) — https://law.justia.com/cases/federal/appellate-courts/ca9/09-55902/09-55902-2013-03-14.html
- *Capitol Records v. Vimeo* (2d Cir. 2025) — https://law.justia.com/cases/federal/appellate-courts/ca2/21-2949/21-2949-2025-01-13.html ; https://www.manatt.com/insights/newsletters/client-alert/vimeo-prevails-on-dmca-safe-harbor-defense-against ; https://natlawreview.com/article/dmca-safe-harbor-prelude-supreme-court-encore
- *Warhol*, *Hanagami*, *Cox v. Sony*, *Mavrix*: see [`system-review-2026-09.md`](system-review-2026-09.md) §8 and [`legal-public-learning.md`](legal-public-learning.md) §8
