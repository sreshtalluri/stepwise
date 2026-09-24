# Rights and privacy — what a stranger uploading a dance clip actually creates

Resolves `docs/OPEN-DECISIONS.md` **D8** ("Who can upload video of whom?"). Written for the case the
builder confirmed: **a public platform anyone can sign up for and use**, free, operated by one person.

I am not a lawyer and neither is the builder. The point of this document is to be *specific* — to say
which risks are real, which are folklore, what each mitigation costs, and which questions genuinely
need an hour of a lawyer's time before strangers can sign up. Where a question is unsettled, it says
so and says what would resolve it. Every citation below was opened and read; §9 lists what I could
not verify.

---

## 1. The one-paragraph answer

The largest real exposure is not a lawsuit. It is **a dancer finding their own body reconstructed on
a site they never heard of and wanting it gone, with no way to ask.** That is the likely event, it
costs nothing to prevent, and preventing it also happens to be the decent thing. Build the removal
path first.

Behind that, in order: the uploaded **video** is somebody's copyrighted work (the *dance* usually is
not — see §3); an Illinois biometric claim is a **weak but non-zero** fit because the statute names a
closed list that body geometry is not on (§4); and the European third-party-data-subject problem is
**real but narrower than it looks**, because Article 9 only bites when you process biometric data
*for the purpose of uniquely identifying someone*, which this pipeline does not do (§5).

Concretely: the current passive one-liner on the upload screen is the right *shape* of answer and
should stay. It is addressed to the wrong risk, though, and needs one more sentence. **Do not add a
blocking checkbox** (§7). Do add a removal link, a retention policy, and — before the day sign-up
opens to strangers — a registered takedown agent (§6).

---

## 2. What the system actually holds today (verified against `w4-jobservice`)

Any rights analysis that is not grounded in what the code stores is decoration. This is what is
there, read from the branch this document sits on.

| Artifact | Where | Contains | Read by anything? | Deleted? |
|---|---|---|---|---|
| Source clip | Modal Volume `stepwise-uploads`, `/{clip_id}.mp4` (`services/motion-api/api.py:115`) | The original upload, verbatim | Yes — the pipeline, and the viewer plays it beside the 3D | **No. There is no deletion, expiry or retention code anywhere in the service.** |
| `{clip_id}.npz` | Modal Volume `stepwise-results` | Pickled per-frame estimator output per track: `skel_state`, `shape_params` (45), `expr_params` (72), `hand_pose_params`, `pred_vertices` (18 439 × 3), segmentation `mask`, 2D/3D keypoints (`sam_3d_body_estimator.py:375–400`) | **Only `skel_state` and `shape_params` are ever read again** (`api.py:262`, `modal_app.py:828`) | No |
| Exported GLB | `stepwise-results` | Per-frame pose on a **stock** MHR `lod3.fbx` character (`modal_app.py:703`, `:874`) — *not* the person's fitted body shape | Yes, this is what the viewer renders | No |
| `MotionResult` JSON | Served to the browser (`api.py:315`) | Includes `persons[].shape_params.vector` — **45 floats describing that person's body proportions** | The `source` field is used for honesty labelling. **The 45 numbers themselves are not consumed by anything.** | n/a |

Four findings fall straight out of that table, and they shape every recommendation below.

1. **Nothing is ever deleted.** Not the source video, not the reconstruction. The landing mockup's
   promise "we keep the clip while the lesson exists" (D6) is currently not true in either direction.
2. **The rendered body is not the dancer's body.** The GLB uses the stock LOD-3 character driven by
   the dancer's pose. Shape personalisation is not wired in. Whatever the mesh reveals about the
   person, it is *motion*, not *proportions*.
3. **…but the proportions are shipped anyway.** The 45-dim `shape_params.vector` travels to every
   browser that loads a lesson and does nothing there. It is the single most person-specific number
   in the system and it is currently dead weight in the payload.
4. **Facial expression coefficients and an 18 439-vertex point cloud are persisted per frame and
   never read.** `expr_params` and `pred_vertices` are byproducts of one forward pass, written to the
   npz because `save_clip_result` pickles the whole dict.

The MHR skeleton is 127 joints and does include `c_head`, `c_jaw`, `l_eye`, `r_eye`
(`services/motion-api/mhr_joint_hierarchy.json`). So the *skeleton* carries face joints regardless of
whether expression is applied.

---

## 3. Copyright — the video is protected, the dance usually is not

This is the distinction that matters and it is routinely collapsed.

### 3a. The dance itself

The U.S. Copyright Office's published guidance is unambiguous and quotable. From
[Circular 52, *Copyright Registration of Choreography and Pantomime*](https://www.copyright.gov/circs/circ52.pdf)
(rev. 10/2022), p. 3:

> Individual movements or dance steps by themselves are not copyrightable, such as the basic waltz
> step, the hustle step, the grapevine, or the second position in classical ballet. The U.S.
> Copyright Office cannot register short dance routines consisting of only a few movements or steps
> with minor linear or spatial variations, even if a routine is novel or distinctive.

And on social dance, same page:

> The drafters of the copyright law also made clear that choreographic works do not include social
> dance steps and simple routines. Registrable choreographic works are typically intended to be
> executed by skilled performers before an audience. By contrast, uncopyrightable social dances are
> generally intended to be performed by members of the public for the enjoyment of the dancers
> themselves. Social dances, simple routines, and other uncopyrightable movements cannot be
> registered as separate and distinct works of authorship, even if they contain a substantial amount
> of creative expression.

A fifteen-second dance designed to be copied by the general public on a phone is close to the
paradigm case of what the Office will not register. **The coordinator's calibration is correct: most
short social-media dances are not protectable choreography.**

**The honest counterweight.** Do not over-read that.
[*Hanagami v. Epic Games, Inc.*, No. 22-55890 (9th Cir. Nov. 1, 2023)](https://law.justia.com/cases/federal/appellate-courts/ca9/22-55890/22-55890-2023-11-01.html)
reversed a dismissal that had rested on exactly the "it's only two seconds, it's only poses"
reasoning. The Ninth Circuit held that choreography is not reducible to poses — it also comprises
body position, shape, actions, transitions, use of space, timing, pauses, energy, canon, motif,
contrast and repetition — that a selection-and-arrangement theory applies, and that **length alone is
not dispositive**. Hanagami's five-minute "How Long" routine was registered.

So the real line is: *a viral dance nobody registered* is usually not a protectable work; *a
registered routine by a working choreographer* is, and a short excerpt of it can still infringe. The
second category exists in the exact content pool this product targets.

### 3b. The video

There is no ambiguity here. The clip is an **audiovisual work** fixed by whoever filmed it, and it
almost always carries a **sound recording** and a **musical composition** the filmer did not own
either. Hosting it and playing it back is a reproduction, a distribution and a public display. Being
free does not change that. "It was posted publicly" is not a licence — the poster granted a licence
to *TikTok*, under TikTok's terms, not to you.

### 3c. Is the 3D reconstruction a derivative work?

Genuinely unsettled, and I found no case addressing it. Two honest readings:

- **Probably not, for the motion.** If the underlying dance is not a protectable work (§3a), a
  representation of that dance cannot be a derivative of nothing. What is copied is unprotectable
  subject matter.
- **Possibly yes, for a registered routine.** After *Hanagami*, a 3D playback of a registered
  routine's "selection and arrangement" of movements is a plausible derivative. The transformative
  argument here is unusually strong, though — the output is a stick-figure-grade stock body with no
  performer, no music, no framing, produced for the purpose of teaching the viewer to perform the
  movements themselves. That is a better fair-use posture than most.

Do not rely on fair use as a plan. It is a defence you argue after being sued, which is the outcome
we are trying to avoid. Rely on it as a reason not to panic.

### 3d. Safe harbour — what §512 actually requires of a solo operator

This is cheap and available. [17 U.S.C. § 512](https://www.law.cornell.edu/uscode/text/17/512),
read directly, imposes three things that a one-person platform must actually do:

1. **Designate an agent** — §512(c)(2). The contact details must be posted "on its website in a
   location accessible to the public" *and* filed with the Copyright Office, which maintains the
   public directory. Filing is electronic only since December 2016; paper is not accepted
   ([Copyright Office DMCA Designated Agent Directory](https://www.copyright.gov/dmca-directory/)).
   [37 C.F.R. § 201.38(a)(4)](https://www.ecfr.gov/current/title-37/chapter-II/subchapter-A/part-201/section-201.38)
   makes the designation **expire after three years** unless renewed. The fee is small — the 2016
   rulemaking publicised $6 for online registration versus $105 for paper — but see §9, the fee
   schedule at § 201.3 has been amended since.
2. **Adopt, reasonably implement, and inform users of a repeat-infringer termination policy** —
   §512(i)(1)(A), which conditions *all* of §512's limitations on it. Verbatim: the provider must
   have "adopted and reasonably implemented, and informs subscribers and account holders … of, a
   policy that provides for the termination in appropriate circumstances of subscribers and account
   holders … who are repeat infringers."
3. **Act expeditiously to remove on notice** — §512(c)(1)(C).

Two things follow. First, "reasonably implemented" and "subscribers and account holders" both
presuppose **identity**. Without accounts (D5) there is no subscriber to terminate and no repeat
infringer to track, which weakens the safe-harbour posture. Second, §512 is a copyright shield only —
it does nothing for a privacy or publicity complaint. The takedown path in §6 therefore has to accept
more than copyright notices.

### 3e. Right of publicity — the under-discussed one

The Illinois Right of Publicity Act (765 ILCS 1075) defines "identity" broadly (name, signature,
photograph, image, likeness, voice) and turns on **commercial purpose**, with § 35(b) exemptions for
non-commercial uses and for use in an audio-visual work that is not itself an advertisement. A free
learning tool sits comfortably in the exemption. Two ways that changes: **charging money**, and
**using a reconstruction in marketing**. `evaluation/README.md` already draws exactly this line for
the demo clip — `permission-granted` vs `untested` — and the instinct there is correct and should be
extended to any reconstruction that appears on the marketing site or in the §7g share clip.

I read § 35(b) and the January 2025 digital-replica amendments (P.A. 103-836) through secondary
sources only; see §9.

---

## 4. Biometric statutes — the enumerated-list answer, and the better argument behind it

### 4a. What BIPA actually says

[740 ILCS 14/10](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57), verbatim:

> "Biometric identifier" means a retina or iris scan, fingerprint, voiceprint, or scan of hand or
> face geometry. Biometric identifiers do not include writing samples, written signatures,
> photographs, human biological samples used for valid scientific testing or screening, demographic
> data, tattoo descriptions, or physical descriptions such as height, weight, hair color, or eye
> color.

And the companion term:

> "Biometric information" means any information, regardless of how it is captured, converted, stored,
> or shared, based on an individual's biometric identifier used to identify an individual. Biometric
> information does not include information derived from items or procedures excluded under the
> definition of biometric identifiers.

**Direct answer to the question asked: torso-and-limb body geometry is outside that list.** The list
is closed and it is short. It names five things. A 45-dimensional body-shape coefficient vector, a
root trajectory, a 127-joint pose stream, and an 18 439-vertex body mesh are none of them. Nor is
gait, which commentators classify as a *behavioural* characteristic rather than one of BIPA's
enumerated physiological identifiers. The enumerated hooks that could conceivably apply to this
pipeline are **hand geometry** and **face geometry**, exactly as the coordinator read it. Feet are
not on the list at all and were never a privacy question — only a quality one.

Two textual exclusions do further work. First, **"physical descriptions such as height, weight"** are
expressly carved out — which is a fair description of a good deal of what a shape vector encodes.
Second, **"photographs"** are carved out, and the photograph carve-out flows through to derived data
via the "Biometric information does not include information derived from items or procedures excluded"
sentence. That second carve-out is contested for *face templates*: Illinois district courts have
consistently held that a faceprint extracted from a photo is still a scan of face geometry, because
reading the exclusion to cover derived templates would defeat the statute (see *Monroy v.
Shutterfly*). But nobody has argued the point for a body mesh, because nobody has litigated a body
mesh.

### 4b. The argument that does more work than any feature change: it has to identify

The coordinator is right that this matters more than removing a feature, and the authority is real.

The controlling gloss in the case law is that an enumerated scan only becomes a "biometric
identifier" when it is capable of identifying the person. The strongest decision is appellate:

**[*Zellmer v. Meta Platforms, Inc.*, 104 F.4th 1117 (9th Cir. June 17, 2024)](https://law.justia.com/cases/federal/appellate-courts/ca9/22-16925/22-16925-2024-06-17.html).**
A non-user sued over "face signatures" Facebook generated from photos his friends uploaded — factually
the closest published case to our situation, because the plaintiff was a **third-party data subject
who never interacted with the service**. The Ninth Circuit *rejected* the district court's reasoning
that BIPA does not protect non-users, holding the plain text applies to everyone whose data the
company holds. It then affirmed on an alternative ground: face signatures **cannot identify a person**
and therefore are not biometric identifiers or biometric information under BIPA. The court emphasised
that the signature is "essentially a string of numbers representing a particular facial image," that
it does not reveal facial features or the distances between them, that it could not be
reverse-engineered, and — separately — that it **exists only momentarily and is neither saved nor
stored after initial use**. Zellmer's argument that a signature could predict gender and age was held
insufficient: categorising is not identifying.

District courts read the requirement into the text the same way. *Martell v. X Corp.* (N.D. Ill.
2024) held that to qualify as a biometric identifier, a retina or iris scan, fingerprint, voiceprint,
or scan of hand or face geometry **must identify an individual**, and rejected as conclusory the
assertion that hashing a photo containing a face necessarily creates a scan of facial geometry
([Covington, *Inside Privacy*](https://www.insideprivacy.com/privacy-and-data-security/illinois-federal-court-dismisses-bipa-suit-against-x-holding-biometric-identifiers-must-identify-individuals/)).
*Daichendt v. CVS Pharmacy, Inc.*, 2022 WL 17404488, at \*5 (N.D. Ill. Dec. 2, 2022) required
plaintiffs to allege the collection made the defendant "capable of determining identities." *Rivera v.
Google Inc.*, 238 F. Supp. 3d 1088, 1096 (N.D. Ill. 2017) and *Carpenter v. McDonald's Corp.*, 580 F.
Supp. 3d 512, 515 (N.D. Ill. 2022) are to the same effect; so is
[Morrison Foerster's survey of the split](https://www.mofo.com/resources/insights/240503-getting-bipa-right-biometric-identifiers-must-identify).

**Be honest about the counterweight.** The split is real and it is not resolved by any Illinois
appellate court. *Colombo v. YouTube, LLC*, 2023 WL 4240226, at \*3 (N.D. Cal. June 28, 2023)
expressly rejected the requirement that a plaintiff allege the collected data can identify people in
uploaded videos. *Wilcosky v. Amazon.com, Inc.*, 517 F. Supp. 3d 751 (N.D. Ill. 2021) let claims
proceed for someone who merely spoke near an Alexa. And the courts that *do* apply an identification
requirement mostly frame it as **capability**, not actual use — which is the version of the test that
a body-shape vector fares worst under, because body-shape and gait recognition are genuine research
fields and a 45-dim anthropometric vector is, in the abstract, re-identifying.

**Net:** the identification argument is strong, it applies to the whole system, and it survives the
product keeping hands, feet and face. It is a "document why this does not apply" argument, not a
"redesign the product" argument — which is what the coordinator suspected and is what the sources
support. It is not a certainty, and the honest description is *strong defence, unresolved split*.

### 4c. Damages, so the number is not imagined

[740 ILCS 14/20](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57): $1,000
liquidated per negligent violation, $5,000 per intentional or reckless violation, plus attorneys'
fees, plus injunctive relief. *Rosenbach v. Six Flags Ent. Corp.*, 2019 IL 123186 held a bare
statutory violation is enough — no actual injury needed. That combination is why BIPA generates the
litigation it does.

The 2024 amendment materially reduces the tail. **P.A. 103-769 (SB 2979), signed 2 August 2024**,
provides that an entity that obtains the same biometric identifier from the same person by the same
method more than once has committed **a single violation**, "for which the aggrieved person is
entitled to, at most, one recovery," and confirms written release may be given by electronic
signature
([Covington](https://www.insideprivacy.com/data-privacy/illinois-enacts-bipa-amendment-limiting-violation-accrual/),
[Davis Wright Tremaine](https://www.dwt.com/blogs/privacy--security-law-blog/2024/08/illinois-bipa-biometrics-law-amended-for-damages)).
That overrides the per-scan accrual of *Cothron v. White Castle*. For a platform, this converts the
worst case from per-frame arithmetic to per-person — still serious at class scale, no longer absurd.

### 4d. The other three statutes, briefly and accurately

- **Texas CUBI**, [Tex. Bus. & Com. Code § 503.001](https://codes.findlaw.com/tx/business-and-commerce-code/bus-com-sect-503-001/):
  "biometric identifier" means "a retina or iris scan, fingerprint, voiceprint, or record of hand or
  face geometry." Same closed list, so body geometry is outside it in the same way. Two differences
  that cut opposite ways: CUBI has **no photograph exclusion at all**, and the Texas AG has argued it
  does not require that the identifier uniquely identify anyone
  ([FPF](https://fpf.org/blog/old-laws-new-tech-as-courts-wrestle-with-tough-questions-under-us-biometric-laws-immersive-tech-raises-new-challenges/)).
  But there is **no private right of action** — enforcement is exclusively the Attorney General, at up
  to $25,000 per violation. That makes CUBI a single-large-regulatory-action risk aimed at
  billion-user platforms (Meta, $1.4bn, 2024; Google, $1.375bn, 2025), not a risk profile a free tool
  with a six-person cohort sits in.
- **Washington, [RCW 19.375.010](https://app.leg.wa.gov/RCW/default.aspx?cite=19.375.010)**: defines
  biometric identifier as data from automatic measurements of biological characteristics "used to
  identify a specific individual," and then excludes **"a physical or digital photograph, video or
  audio recording or data generated therefrom."** A reconstruction computed from an uploaded video is
  literally data generated from a video recording. Washington's dedicated biometric statute does not
  reach this product, and it has no private right of action anyway.
- **Washington My Health My Data Act, [RCW 19.373.010(4)](https://app.leg.wa.gov/RCW/default.aspx?cite=19.373.010)** —
  the broadest US definition and the one most worth knowing about, because it *does* have a private
  right of action (via the Consumer Protection Act): "data generated by the measurement or
  technological processing of an individual's physiological, biological, or behavioral characteristics
  that identifies a consumer," expressly including "[k]eystroke patterns or rhythms and gait patterns
  or rhythms that contain identifying information." Gait is named. **But** MHMDA only regulates
  biometric data that is *consumer health data*, and a dance lesson is not health data, and the
  definition still keys on "identifies a consumer." Watch it; do not redesign for it.
- **Comprehensive state laws** (Colorado HB24-1130, effective 1 July 2025, amending the CPA;
  Texas TDPSA; Connecticut) treat biometric data as sensitive requiring opt-in consent and use
  broader definitions than BIPA's enumerated list. Colorado adds retention-policy, deletion-protocol
  and access obligations and prohibits sale of biometric identifiers, enforced by the AG with **no
  private right of action** ([Venable](https://www.venable.com/insights/publications/2024/06/colorado-amends-state-privacy-law-to-include)).
  Most of these carry revenue or volume thresholds a pre-launch product does not meet. This is the
  category where the 45-dim shape vector is most likely to be "biometric data" — which is one more
  reason to stop shipping it (§6.2).

### 4e. Does the video-crop plan for hands change the legal picture, or is it cosmetic?

Mostly cosmetic for BIPA, genuinely useful at the margin, and correct for reasons that have nothing
to do with law.

- A video crop of a hand **is a video recording**. BIPA excludes photographs by name; Washington
  excludes "video … recording or data generated therefrom" by name. Showing the learner real footage
  of the hand does not create anything on the enumerated list.
- A persisted **per-person articulated hand model** is the artifact that most resembles "a scan of
  hand geometry," because that phrase in 2008 meant an access-control reader measuring finger lengths
  and knuckle widths to authenticate someone. The crop plan avoids creating one. That is a real, if
  modest, difference — and *Zellmer* shows why it is not nothing: the Ninth Circuit leaned partly on
  the fact that face signatures "exist only momentarily and are neither saved nor stored."
- But the plan was chosen for accuracy, not law (a hand is ~30px in a full-body phone clip;
  `evaluation/clips.yaml:129` `stress-hands` records "Specific hand shapes carry meaning" and predicts
  hands will be unreliable). It stays chosen for accuracy. The legal benefit is a bonus, not a reason.

**If a dedicated hand-pose model is added later** — running on the `lhand_bbox` / `rhand_bbox` crops
the estimator already emits (`sam_3d_body_estimator.py:406`, `:426`) — the analysis shifts, but less
than it sounds:

- **Per-frame hand *pose* is choreography.** "The fingers were splayed at t = 1.2 s" is a fact about
  a movement, not a measurement of a hand's geometry. It varies frame to frame, which is the opposite
  of what an identifier does.
- **A per-person hand *template* is the thing to avoid** — any time-invariant fitted representation
  of that individual's hand proportions, frozen once and stored. That is structurally the same object
  as `shape_params` is for the body, and it is the one artifact whose name matches the statute.
- So the rule to build to, stated now so it can be designed in rather than retrofitted: **keep the
  pose, do not persist a per-person hand shape fit.** Costs the feature nothing — the learner needs to
  see what the fingers did, not how long they are.

Same principle for face. Expressions are a real if secondary product requirement and should not be
discarded for convenience. Rendering a jaw and eyelids driven by per-frame expression coefficients is
performance, not identification. What you should not accumulate is a stored, time-invariant facial
geometry fit per person. Right now the system stores `expr_params` and reads them never — the worst
of both, and free to fix (§6.2).

---

## 5. GDPR / UK GDPR — the third-party data subject, calibrated

### 5a. Is it special category data?

Only sometimes, and the qualifier is the whole answer.
[Article 4(14)](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679), verbatim:

> 'biometric data' means personal data resulting from specific technical processing relating to the
> physical, physiological or behavioural characteristics of a natural person, which allow or confirm
> the unique identification of that natural person, such as facial images or dactyloscopic data;

The reconstruction is unambiguously **personal data** — it relates to an identifiable person. Whether
it is *biometric* data turns on "allow or confirm the unique identification." But the operative
provision is narrower still.
[Article 9(1)](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679), verbatim:

> Processing of personal data revealing racial or ethnic origin, political opinions, religious or
> philosophical beliefs, or trade union membership, and the processing of genetic data, **biometric
> data for the purpose of uniquely identifying a natural person**, data concerning health or data
> concerning a natural person's sex life or sexual orientation shall be prohibited. *(emphasis added)*

**Purpose is on the face of the text.** This pipeline's purpose is to show a learner what a body did
so they can copy it. It runs no matching, no enrolment, no template database, no 1:1 or 1:N
comparison. It is not processing biometric data for the purpose of uniquely identifying anyone.
Recital 51 confirms the same logic for the nearest analogue:

> The processing of photographs should not systematically be considered to be processing of special
> categories of personal data as they are covered by the definition of biometric data only when
> processed through a specific technical means allowing the unique identification or authentication
> of a natural person.

So: **Article 9 probably does not engage.** Ordinary GDPR does. That is a large difference — Article 9
means "prohibited unless an exception applies"; ordinary GDPR means "needs a lawful basis and the
usual rights."

### 5b. The genuinely hard part

The dancer never interacted with the service and cannot be asked. You cannot get their consent and
you cannot pretend you have. The available routes:

- **Legitimate interests, Art. 6(1)(f)**, with a documented balancing test. This is the realistic
  basis, and it is not a fudge — the interest (letting someone learn a dance) is legitimate, the
  processing is proportionate, and the expectation of a person who posted a dance publicly for others
  to learn is not badly violated by someone learning it. Recital 47 makes reasonable expectations
  central to the balance. What makes this basis *work* rather than merely *asserted* is having an
  objection route that functions — Art. 21 gives an absolute right to object, and honouring it is the
  removal path in §6.1.
- **Article 9(2)(e)**, verbatim: "processing relates to personal data manifestly made public by the
  data subject." This is the closest legal home for the builder's argument that a publicly-posted
  dance was posted to be watched. It is a real, quotable exception and it is the right one to cite —
  but note two limits: it is an Article *9* exception, so it only matters if Article 9 engaged at all
  (which §5a says it probably did not), and "manifestly" is read strictly, so it covers the original
  poster, not a person who happened to be in frame behind them.
- **Article 14** requires notice to a data subject whose data you obtained from someone else, but
  **Art. 14(5)(b)** disapplies it where notice "proves impossible or would involve a disproportionate
  effort." A solo operator with no way to contact an anonymous dancer is close to the paradigm case.
  It is not a free pass — the same article expects compensating measures, and a public, findable
  removal route is exactly that.

**The honest summary for a solo builder:** the European exposure is real but it is a
*documentation-and-responsiveness* problem, not a consent problem you can solve by collecting
something. The three things that actually move it are (a) publish a plain privacy notice that says
what is processed and why, (b) make removal work and answer it fast, (c) retain less and for less
time. All three are on the list in §6 anyway. A FAANG-scale compliance programme is not the
proportionate answer and building one would be a mistake.

The one structural decision worth naming: **geographic restriction** — simply not serving EU/UK users
— removes this section entirely. I do **not** recommend it (§6.7).

---

## 6. Mitigations, ranked by risk reduced per unit of cost

### 6.1 Build the removal path. Highest value, lowest cost, do it first
**Cost: a few hours. Removes the single most likely bad outcome.**

A link on every lesson page and a monitored address. It must accept more than copyright notices — the
person most likely to use it is the dancer, who has no copyright claim at all. Three states:
acknowledged, removed, declined-with-a-reason. A stated response target you can actually hit (48
hours is credible for one person; 24 is not).

This is simultaneously the answer to the realistic risk, the thing that makes the Art. 6(1)(f)
balance defensible, the Art. 21 objection route, and the decent thing to do. Nothing else on this
list has that ratio.

**Interaction with D5 (not mine to resolve).** Without accounts, anyone holding a lesson link can
request its removal, which is fine for a *dancer* asking and awkward for an *uploader* whose lesson a
stranger deleted. The cheap resolution that does not require solving D5: removal requests take the
lesson down; restoring it requires whoever created it, which a magic-link account would make trivial
and which without accounts means a per-case email. Note this in D5's write-up as a dependency rather
than resolving it here.

### 6.2 Stop persisting what nothing reads
**Cost: near zero, touches no feature, no product decision.**

Three edits to one function (`tools/process_clip.py:save_clip_result`) and one line in `api.py`:

- **Do not write `expr_params` to the npz.** Nothing reads it. Facial expression coefficients are the
  single most face-shaped artifact in the store and they exist by accident, because the whole
  estimator dict is pickled. Keeping the *ability* to render expression later costs nothing — the model
  emits it on demand; it is the persistence that is gratuitous. This is the honest version of
  "retain less face geometry" and it costs the product nothing, unlike removing the feature.
- **Do not write `pred_vertices` to the npz.** 18 439 × 3 floats per person per frame, never read; the
  export path reconstructs geometry from `lod3.fbx` plus `skel_state`. This is also the largest single
  thing in the file, so it is a storage-cost win independent of privacy.
- **Drop `shape_params.vector` from the served `MotionResult`; keep `shape_params.source`.** The 45
  numbers are the most person-specific data in the system, they are broadcast to every browser that
  opens a lesson, and nothing consumes them — the mesh is a stock LOD-3 character. `source`
  (`well_observed_frames` / `default_assumed`) is what the honesty labelling needs and is what should
  stay. This is a schema change to a frozen contract, so it is a minor-version bump and a
  fixture update, not a free edit — but it is the one item here that removes the artifact most likely
  to be called "biometric data" under the broader comprehensive state definitions (§4d).

None of this touches hands, feet, face rendering, or any product capability. It is deleting exhaust.

### 6.3 Actually delete things
**Cost: small. Also makes an existing public claim true.**

There is no retention logic anywhere today (§2). Two decisions, both the builder's to make:

- **Source clip:** delete when the lesson is deleted, and on a ceiling regardless (90 days is a
  defensible default for a practice tool). The clip is needed for playback beside the 3D, so it cannot
  be deleted right after reconstruction — the landing mockup's "we keep the clip while the lesson
  exists" is the right policy and just needs to become true in both directions.
- **Reconstruction:** dies with the lesson. Deleting a lesson must delete the GLB, the npz and the
  `MotionResult`, not just hide the page.

This closes D6 and D7 and is a precondition for any privacy notice being accurate.

### 6.4 Register a takedown agent and write the repeat-infringer policy
**Cost: an afternoon plus a small fee. Required before strangers can upload.**

Per §3d: electronic filing with the Copyright Office, contact details posted publicly on the site,
**calendar the three-year renewal** (37 C.F.R. § 201.38(a)(4)) — a lapsed registration silently
forfeits the safe harbour. The repeat-infringer policy needs to exist in writing, be linked from the
terms, and be one you actually follow. It is genuinely short.

Not needed while invite-only, because §512 protects you from *users'* infringement and six named
cohort members are not that threat model.

### 6.5 Terms of service and a privacy notice
**Cost: a day of drafting plus real lawyer review of two clauses (§8).**

The terms are where the uploader's representation lives — that they have the right to upload, and an
indemnity if they did not. That is what a blocking checkbox is usually trying and failing to
accomplish (§7). The privacy notice is what makes the GDPR posture in §5 defensible: what is
processed, why, on what basis, how long, how to object.

### 6.6 Stay invite-only through the W12 pilot
**Cost: zero — it is already the plan. Buys the time to do 6.1–6.5.**

This materially changes the early picture, for specific reasons rather than a vague "we're small":

- The six named cohort members **can** consent, in writing, for clips they film or appear in. That is
  a real consent, from the right person, which no amount of upload-screen copy ever produces.
- No public index means the "dancer discovers their reconstruction" scenario (§1) has near-zero
  probability.
- §512 safe harbour matters only when strangers upload.
- It is not a legal exemption. BIPA, CUBI and GDPR have no small-operator carve-out, and MHMDA's
  small-business threshold is 100,000 consumers, which is not a shield you would ever need.

**Name the tripwire explicitly:** the day sign-up opens to people you have not met is the day 6.1,
6.4 and 6.5 must already be done. Put that in `TASKS.md`, not in someone's memory.

### 6.7 Geographic restriction — recommended against
**Cost: a real slice of the audience. Benefit: removes §5 wholesale.**

Blocking EU/UK traffic would eliminate the third-party-data-subject problem in one line of config.
Do not do it. The GDPR posture in §5 is defensible with the measures already recommended, and a dance
tool that cannot be used in Europe is a worse product for no proportionate gain. **Reconsider if** any
of these become true: you start charging, you begin retaining `shape_params` long-term after all, or
you add any identification, matching or "find this dancer" capability. Any of those changes the
analysis enough to revisit.

### 6.8 Feature changes for legal reasons — recommended against
Do not remove hands, feet or face to reduce legal risk. Hands and feet carry choreographic meaning,
face carries expression, and §4 shows that removing them buys much less than the identification
argument already provides. The crop plan for hands stays because it is more accurate; the legal
benefit is incidental (§4e). The one forward-looking constraint worth designing in now is **per-frame
pose yes, persisted per-person shape fit no** — for hands as for the body.

---

## 7. The upload screen — recommended copy, and no blocking gate

Read `docs/DESIGN.md` §7d, §7h, §11 and §12 before changing any of this. The lint in
`apps/web/test/copy.test.ts` enforces §11 mechanically; everything below passes it (no banned words,
no exclamation marks, no emoji, no ALL-CAPS runs, sentence case).

### 7a. Confirm W7's decision: no blocking checkbox

W7 deliberately shipped a passive one-liner and no gate. **That was the right call and it should
stand.** Both grounds:

**Legal.** A checkbox collects an attestation from the wrong person. The consent that every statute
in §4 and §5 cares about is the *dancer's*, and the uploader cannot give it on their behalf. What a
checkbox actually buys is (a) a contractual representation and (b) evidence of notice — and both of
those are delivered by terms-of-service acceptance at signup, which D5 will create anyway, without
putting friction on the conversion step. I found no authority treating a click-through attestation as
curing a third-party consent problem, and the structure of BIPA §15(b) — which requires a written
release *from the subject* — is squarely against it. The real danger is that a checkbox *feels* like
it resolved D8 and stops anyone building the removal path, which is the thing that actually works.

**UX.** This is the single most important conversion step in the product. `DESIGN.md` §7h names both
failure modes: a rights line that implies verification that did not happen, and a scary wall of text
nobody reads. A blocking checkbox is the second one with a click attached. §7d's framing — constraints
stated as *what works*, not *what we reject* — applies here too.

**Where a gate *is* warranted: publication, not upload.** The act that creates the risk in §1 is a
reconstruction becoming *visible to people who did not make it* — a featured lesson, the marketing
site, the §7g share clip. `evaluation/README.md` already reasons exactly this way about the demo clip
(`untested` / `personal-test-only` / `permission-granted` / `needs-permission`), and that three-tier
thinking transfers directly. If and when a "make this public" or "post this clip" action ships, an
affirmative "everyone in this said yes" belongs on *that* button. Not on upload.

### 7b. What is wrong with the current line

`apps/web/lib/copy.ts` today:

```ts
subtitle: "One video, filmed on one camera. It stays yours.",
rights: "Only upload video you have the right to use.",
```

Two problems, neither fatal:

1. **It addresses the less likely risk.** "The right to use" is a copyright instruction. The person
   most likely to complain is the dancer, who has no copyright claim. The screen currently says
   nothing about the people *in* the video — which is precisely what D8 asks about.
2. **"It stays yours" is currently not true.** Nothing is ever deleted (§2). The line is a promise
   about ownership that reads as a promise about control. Either 6.3 lands, or the line changes.

### 7c. Recommended copy

Minimal diff — one line edited, one line added, one link added on the lesson page.

```ts
export const upload = {
  title: "Add a clip",
  subtitle: "One video, filmed on one camera. It stays yours.",
  // ...
  // The rights line appears here, once, plainly — DESIGN.md §7d,
  // OPEN-DECISIONS.md D8. Two sentences, not one: the first is about the
  // clip, the second is about the people in it. Neither claims we checked.
  rights:
    "Only upload video you have the right to use. Anyone in a clip can ask us to take it down, and we will.",
};
```

And on the lesson page, a quiet link — a plain label, not a button:

```ts
export const lesson = {
  remove: "Ask us to remove this lesson",
};
```

Why this wording:

- **"Only upload video you have the right to use"** is kept verbatim. It is already in `DESIGN.md`
  §7d, it is plain, and it does not claim verification.
- **"Anyone in a clip can ask us to take it down, and we will"** is the sentence D8 was missing. It
  names the dancer, states what they can do, and commits to an outcome. It is a promise the builder
  must actually keep — which is the point: §6.1 is the highest-value item and this line is what makes
  it visible.
- It does **not** say "we check", "we verify", "we have permission", "secure", or "protected". It
  states a mechanism, not a guarantee, which is the §7h test: *would someone who understood exactly
  how this works feel misled?* No — the mechanism described is the mechanism that exists.
- It does not say "by uploading you agree that you have obtained consent from all persons depicted",
  which is the standard formulation and is a wall of text that shifts blame while protecting nobody.
- Two sentences, one line of body text. It stays out of the way.

**Conditional on 6.3 shipping**, add the retention line, which closes D6 honestly:

```ts
keeps: "We keep your clip while the lesson exists. Delete the lesson and the clip goes too.",
```

Do not ship that line before the deletion code exists. A false retention promise is worse than no
retention promise, and §7h treats it as the same failure as an overclaim about the 3D.

---

## 8. What genuinely needs a lawyer, and what does not

### Needs a lawyer before strangers can sign up — five items, one to three hours of counsel

1. **The terms of service and privacy notice.** Specifically the licence grant from uploader to
   platform (what rights do you need to host, transcode, reconstruct, and display?) and the
   indemnity. Do not draft these from a template — the licence grant is the clause that makes
   everything else in this document operable and getting it narrow-but-sufficient is exactly what a
   lawyer is fast at.
2. **Whether serving EU/UK users triggers a DPIA under Art. 35, an Art. 30 record, and an Art. 27
   representative.** §5 concludes Art. 9 probably does not engage, which if right takes you out of
   the "large scale special category" DPIA trigger. That conclusion is worth an hour of confirmation
   because getting it wrong is the difference between a one-page notice and a compliance programme.
3. **The SAM License's compliance clause against a public consumer product.** §1.b.iii requires that
   use "comply with applicable laws and regulations, including … applicable privacy and data
   protection laws," and §8 lets Meta amend the agreement unilaterally, effective immediately, with
   continued use constituting acceptance (`SAM Materials/LICENSE`; already flagged in PRD §2 G2 and
   §9). This is a contract question with a counterparty who can change the terms, not a privacy
   question, and it is the one item here that could invalidate the whole approach rather than adjust
   it.
4. **Right of publicity if a paid tier ever appears**, or if any reconstruction is used in marketing.
   §3e says the free non-commercial posture is comfortable; the moment money or promotion is involved,
   "commercial purpose" is live and the transformative-use analysis for a deliberately faithful
   reconstruction is not favourable (*Hart v. Electronic Arts*).
5. **Only if you decide to keep `shape_params.vector`:** whether a 45-dim anthropometric vector is
   "biometric data" under Colorado's HB24-1130 definitions and MHMDA. If you take recommendation 6.2
   and drop it, this question disappears and you can skip it.

### The builder can decide these alone — no lawyer needed

- **Blocking checkbox: no** (§7a). This is a product and UX decision with a legal input, and the legal
  input points the same way as the UX input.
- **The upload copy** (§7c). Plain-language notice is not legal drafting.
- **Whether to persist `expr_params`, `pred_vertices`, and ship `shape_params.vector`: no** (§6.2).
  Deleting unused data never needs advice.
- **Retention periods** (§6.3). Pick a number, state it, honour it. Any stated-and-honoured policy
  beats an unstated one.
- **Registering a takedown agent** (§6.4). It is a web form and a small fee. There is no downside and
  no judgement call.
- **The removal path's design and response target** (§6.1).
- **Staying invite-only through W12** (§6.6).
- **Not geo-blocking Europe** (§6.7).
- **Not cutting hands, feet or face for legal reasons** (§6.8).

---

## 9. What I could not verify

Listed because an admitted gap is worth more than a confident wrong citation.

1. ***Martell v. X Corp.*** — I read the holding through two independent secondary sources (Covington's
   *Inside Privacy*, and a second summary) but **did not open the slip opinion** and do not have a
   verified docket number or reporter citation. The holding as reported is consistent with
   *Daichendt*, *Rivera* and *Carpenter*, which I do have pin cites for, so the proposition does not
   rest on it alone. Resolve by pulling the opinion from PACER or CourtListener.
2. **Seventh Circuit retroactivity of P.A. 103-769.** A search surfaced a 2026 decision said to hold
   the single-recovery amendment applies retroactively. I could not confirm the case, and the date is
   recent enough that I will not repeat the name. The *amendment itself* is well sourced and is what
   §4c relies on. Resolve before relying on retroactive application.
3. **Current DMCA designated-agent fee.** The $6 figure traces to the 2016 rulemaking's own
   commentary. 37 C.F.R. § 201.38 points to the fee schedule at § 201.3, which has been amended since
   (most recently 85 FR 11295). Check the live figure at filing time; it is small either way.
4. **Illinois Right of Publicity Act current text.** ILGA blocks automated access, so §3e rests on
   secondary summaries of §§ 5, 30 and 35(b) including the P.A. 103-836 digital-replica amendments
   effective 1 January 2025. Read the live text before relying on the § 35(b) exemption.
5. **BIPA statutory text source.** The verbatim §10, §15 and §20 text in §4 was read from a PDF
   reproduction of the Act; I cross-checked the §10 definition against an independent source and they
   agree. ILGA blocked direct fetching. The quoted language is the enacted text (P.A. 95-994), not the
   proposed amendments that also appeared in that document.
6. **No court anywhere has addressed a full-body 3D mesh or pose reconstruction under any biometric
   statute, as far as I can find.** I searched specifically for it. **That absence is the finding**, and
   it cuts both ways: no adverse authority, and no favourable authority either. It is why §4b is
   phrased as "strong defence, unresolved split" rather than "settled."
7. **Whether the identification requirement survives in Illinois state court.** No Illinois appellate
   decision resolves the split; *Zellmer* is a federal court of appeals applying Illinois law. An
   Illinois Supreme Court decision going the other way would weaken §4b materially.
8. **Unchanged and not mine:** the MHR `assets.zip` in-zip LICENSE is still unread (PRD §2 G6, §9). It
   is a distribution-licence question, not a rights-of-people question, but it is the other unresolved
   licensing item and it is still open.

---

## 10. Sources

**Primary**

- [740 ILCS 14, Biometric Information Privacy Act](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57) — §10 definitions, §15 retention/consent, §20 damages
- [Tex. Bus. & Com. Code § 503.001 (CUBI)](https://codes.findlaw.com/tx/business-and-commerce-code/bus-com-sect-503-001/)
- [RCW 19.375.010 (Washington biometric identifiers)](https://app.leg.wa.gov/RCW/default.aspx?cite=19.375.010)
- [RCW 19.373.010 (My Health My Data Act definitions)](https://app.leg.wa.gov/RCW/default.aspx?cite=19.373.010)
- [Regulation (EU) 2016/679 (GDPR), EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679) — Art. 4(14), Art. 9, Recital 51
- [17 U.S.C. § 512](https://www.law.cornell.edu/uscode/text/17/512) — §512(c)(2), §512(c)(3), §512(i)
- [37 C.F.R. § 201.38](https://www.ecfr.gov/current/title-37/chapter-II/subchapter-A/part-201/section-201.38) — agent designation, three-year expiry
- [U.S. Copyright Office, Circular 52: Copyright Registration of Choreography and Pantomime](https://www.copyright.gov/circs/circ52.pdf) (rev. 10/2022)
- [U.S. Copyright Office, DMCA Designated Agent Directory](https://www.copyright.gov/dmca-directory/)
- `SAM Materials/LICENSE` (in repo, branch `licensing-compliance`) — §1.b.iii, §8

**Cases**

- [*Zellmer v. Meta Platforms, Inc.*, 104 F.4th 1117 (9th Cir. 2024)](https://law.justia.com/cases/federal/appellate-courts/ca9/22-16925/22-16925-2024-06-17.html)
- [*Hanagami v. Epic Games, Inc.*, No. 22-55890 (9th Cir. 2023)](https://law.justia.com/cases/federal/appellate-courts/ca9/22-55890/22-55890-2023-11-01.html)
- *Daichendt v. CVS Pharmacy, Inc.*, 2022 WL 17404488 (N.D. Ill. Dec. 2, 2022); *Rivera v. Google Inc.*, 238 F. Supp. 3d 1088 (N.D. Ill. 2017); *Carpenter v. McDonald's Corp.*, 580 F. Supp. 3d 512 (N.D. Ill. 2022); *Colombo v. YouTube, LLC*, 2023 WL 4240226 (N.D. Cal. June 28, 2023); *Wilcosky v. Amazon.com, Inc.*, 517 F. Supp. 3d 751 (N.D. Ill. 2021) — all as collected and pin-cited in [Morrison Foerster, *Getting BIPA Right*](https://www.mofo.com/resources/insights/240503-getting-bipa-right-biometric-identifiers-must-identify)
- *Rosenbach v. Six Flags Ent. Corp.*, 2019 IL 123186
- *Martell v. X Corp.* (N.D. Ill. 2024) — **secondary sources only**, see §9.1

**Secondary (used for currency and to locate primary text, not as authority)**

- [Covington, *Illinois Enacts BIPA Amendment Limiting Violation Accrual*](https://www.insideprivacy.com/data-privacy/illinois-enacts-bipa-amendment-limiting-violation-accrual/)
- [Covington, *Illinois Federal Court Dismisses BIPA Suit Against X*](https://www.insideprivacy.com/privacy-and-data-security/illinois-federal-court-dismisses-bipa-suit-against-x-holding-biometric-identifiers-must-identify-individuals/)
- [Davis Wright Tremaine on P.A. 103-769](https://www.dwt.com/blogs/privacy--security-law-blog/2024/08/illinois-bipa-biometrics-law-amended-for-damages)
- [Future of Privacy Forum, *Old Laws & New Tech*](https://fpf.org/blog/old-laws-new-tech-as-courts-wrestle-with-tough-questions-under-us-biometric-laws-immersive-tech-raises-new-challenges/)
- [Venable on Colorado HB24-1130](https://www.venable.com/insights/publications/2024/06/colorado-amends-state-privacy-law-to-include)
- [Texas Attorney General, Biometric Identifier Act](https://www.texasattorneygeneral.gov/consumer-protection/file-consumer-complaint/consumer-privacy-rights/biometric-identifier-act)

**In this repo**

- `docs/OPEN-DECISIONS.md` (D5, D6, D7, D8) · `docs/PRD.md` §2 G2, §4, §5, §9 · `docs/DESIGN.md` §7d, §7e, §7g, §7h, §11, §12 · `evaluation/README.md` (three-tier rights model), `evaluation/clips.yaml:129` · `services/motion-api/api.py`, `modal_app.py`, `mhr_joint_hierarchy.json` · `packages/motion-contract/schema/motion-result.schema.json` · `apps/web/lib/copy.ts`, `apps/web/app/upload/page.tsx`, `apps/web/test/copy.test.ts` (branch `w7-marketing`)
