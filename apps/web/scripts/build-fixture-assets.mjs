/**
 * Builds the dev assets the viewer needs but the (not-yet-existing) GPU pipeline
 * would normally produce:
 *
 *   public/fixtures/<lesson>.json              copy of the frozen contract fixture
 *   public/fixtures/<lesson>.<person_id>.glb   one rigged, animated GLB per dancer
 *   public/fixtures/<lesson>.mp4               a stand-in source video of the right length
 *   public/fixtures/two-dancers.json + glbs    a DERIVED multi-person fixture (see note)
 *
 * NOTE ON THE MULTI-PERSON FIXTURE. `packages/motion-contract/fixtures/` only ships
 * single-person lessons, but multi-dancer is in MVP scope (PRD §5, DESIGN §7a2).
 * Rather than edit the frozen contract package, this script DERIVES a two-dancer
 * document from good-lesson.json and validates it against the real schema. If the
 * contract package later ships its own multi-person fixture, delete `buildTwoDancers`.
 *
 * NOTE ON THE MESH. The real body is MHR LOD 3-4. This stand-in is deliberately
 * built the way the real exporter must also build it (OPEN-DECISIONS E3): ONE shared
 * skeleton, and the surface split into separately-drawable region meshes — because
 * hiding a bone does not hide a skinned surface. Region ids here must survive into
 * the real export.
 *
 * NOTE ON ANIMATION SEGMENTS. Every sample slot in MotionResult carries a rotation,
 * so this export has a keyframe at every `sample_times_s[i]` and there is no gap for
 * AnimationMixer to interpolate across. A real exporter that OMITS keyframes for
 * suppressed samples must split the clip into per-segment clips instead — the mixer
 * will happily interpolate straight across a hole otherwise.
 */
import * as THREE from "three";

// GLTFExporter's binary path is browser-only in exactly one place: it reads the
// packed Blob back with a FileReader. Node has Blob but not FileReader.
if (typeof globalThis.FileReader === "undefined") {
  globalThis.FileReader = class {
    readAsArrayBuffer(blob) {
      blob.arrayBuffer().then((buf) => {
        this.result = buf;
        this.onloadend?.();
      });
    }
  };
}

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { REGIONS } from "../lib/regions.ts";

const { GLTFExporter } = await import("three/examples/jsm/exporters/GLTFExporter.js");

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(here, "..");
const outDir = path.join(webRoot, "public", "fixtures");
const contractFixtures = path.join(webRoot, "..", "..", "packages", "motion-contract", "fixtures");

mkdirSync(outDir, { recursive: true });

/* ------------------------------------------------------------------- rigging */

function buildRig(doc) {
  const defs = doc.joint_hierarchy.joints;
  const byName = new Map(defs.map((j) => [j.name, j]));
  const bones = defs.map((j) => {
    const b = new THREE.Bone();
    b.name = j.glb_node_name;
    b.position.fromArray(j.rest_translation);
    b.quaternion.fromArray(j.rest_rotation);
    return b;
  });
  defs.forEach((j, i) => {
    if (j.parent_index >= 0) bones[j.parent_index].add(bones[i]);
  });

  const group = new THREE.Group();
  group.name = "dancer";
  group.add(bones[doc.joint_hierarchy.root_joint_index]);
  group.updateMatrixWorld(true);

  const skeleton = new THREE.Skeleton(bones);
  const restWorld = (name) => bones[byName.get(name).index].getWorldPosition(new THREE.Vector3());

  for (const region of REGIONS) {
    const def = byName.get(region.bone);
    if (!def) throw new Error(`region ${region.id} references unknown joint ${region.bone}`);
    const a = restWorld(region.bone);
    const b = region.tip ? restWorld(region.tip) : a.clone().addScaledVector(new THREE.Vector3(0, 1, 0), 0.001);

    let geom;
    if (region.tip === null) {
      geom = new THREE.SphereGeometry(region.radius, 20, 14);
      geom.translate(a.x, a.y + region.radius * 0.55, a.z);
    } else {
      const dir = b.clone().sub(a);
      const len = Math.max(dir.length() - region.radius * 0.6, 0.02);
      geom = new THREE.CapsuleGeometry(region.radius, len, 4, 16);
      const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
      const mid = a.clone().add(b).multiplyScalar(0.5);
      geom.applyMatrix4(new THREE.Matrix4().compose(mid, q, new THREE.Vector3(1, 1, 1)));
    }

    // Single-bone weights: coarse, but the point of this asset is the region split,
    // not deformation quality. ponytail: upgrade to real MHR weights when the
    // pipeline's GLB exists; nothing in the viewer depends on the weighting.
    const count = geom.attributes.position.count;
    const idx = new Uint16Array(count * 4);
    const wgt = new Float32Array(count * 4);
    for (let i = 0; i < count; i++) {
      idx[i * 4] = def.index;
      wgt[i * 4] = 1;
    }
    geom.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(idx, 4));
    geom.setAttribute("skinWeight", new THREE.Float32BufferAttribute(wgt, 4));

    const mesh = new THREE.SkinnedMesh(geom, new THREE.MeshStandardMaterial({ color: 0xcccccc }));
    mesh.name = `region_${region.id}`;
    group.add(mesh);
    mesh.bind(skeleton);
  }

  return { group, bones, defs, byName };
}

/* ----------------------------------------------------------------- animation */

function buildClip(doc, person, rig, clipName) {
  const times = Float32Array.from(doc.sample_times_s);
  const n = times.length;
  const tracks = [];

  const rootDef = doc.joint_hierarchy.joints[doc.joint_hierarchy.root_joint_index];
  const pos = new Float32Array(n * 3);
  const rootQuat = new Float32Array(n * 4);
  const restRoot = new THREE.Quaternion().fromArray(rootDef.rest_rotation);
  const q = new THREE.Quaternion();
  const qLocal = new THREE.Quaternion();

  for (let i = 0; i < n; i++) {
    const rt = person.root_trajectory[i];
    pos.set(rt.position, i * 3);
    // Root node = world root orientation, then the rest pose, then the pelvis's own
    // local rotation. In the shipped fixtures the last two are identity; composing
    // them anyway keeps the exporter correct for a pipeline that uses them.
    q.fromArray(rt.rotation)
      .multiply(restRoot)
      .multiply(qLocal.fromArray(person.samples[i].joints[rootDef.index].rotation));
    rootQuat.set([q.x, q.y, q.z, q.w], i * 4);
  }
  tracks.push(new THREE.VectorKeyframeTrack(`${rootDef.glb_node_name}.position`, times, pos));
  tracks.push(new THREE.QuaternionKeyframeTrack(`${rootDef.glb_node_name}.quaternion`, times, rootQuat));

  for (const def of doc.joint_hierarchy.joints) {
    if (def.index === rootDef.index) continue;
    const rest = new THREE.Quaternion().fromArray(def.rest_rotation);
    const values = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) {
      q.copy(rest).multiply(qLocal.fromArray(person.samples[i].joints[def.index].rotation));
      values.set([q.x, q.y, q.z, q.w], i * 4);
    }
    tracks.push(new THREE.QuaternionKeyframeTrack(`${def.glb_node_name}.quaternion`, times, values));
  }

  return new THREE.AnimationClip(clipName, times[n - 1], tracks);
}

/* ------------------------------------------------------------------- exports */

async function writeGlb(doc, person, file) {
  const rig = buildRig(doc);
  const scene = new THREE.Scene();
  scene.add(rig.group);
  // Per-PERSON, not per-document: W8 moved `animation` out of the top level and
  // into PersonResult so a multi-dancer result can say which clip belongs to
  // which dancer. W5 was cut before that and read `doc.animation`.
  const clip = buildClip(doc, person, rig, person.animation.clip_id);
  const exporter = new GLTFExporter();
  const buffer = await exporter.parseAsync(scene, { binary: true, animations: [clip] });
  writeFileSync(file, Buffer.from(buffer));
  return clip.tracks.length;
}

function writeVideo(doc, file) {
  if (existsSync(file)) return "cached";
  const d = doc.source_video.duration_s;
  const aspect = doc.source_video.width_px / doc.source_video.height_px;
  const h = 720;
  const w = Math.round((h * aspect) / 2) * 2;
  try {
    execFileSync("ffmpeg", [
    "-y", "-hide_banner", "-loglevel", "error",
    "-f", "lavfi", "-i", `testsrc2=size=${w}x${h}:rate=30:duration=${d}`,
    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "34", "-movflags", "+faststart",
      file,
    ]);
  } catch {
    // The stand-in video is a convenience, not the deliverable. Without ffmpeg the
    // 3D stage still loads and the clock falls back to the video element being absent.
    return "SKIPPED (ffmpeg not available)";
  }
  return "built";
}

/* ------------------------------------- derived two-dancer document (see note) */

/** `half` = metres each dancer is offset from the origin, so they stand 2*half apart. */
function buildTwoDancers(good, half = 0.62) {
  const doc = structuredClone(good);
  doc.job_id = "job_dev_two_dancers_0000000000000000000000";
  // More than one dancer => the per-clip sampled accent is not used (DESIGN §3):
  // each dancer takes a --dancer-N swatch instead.
  doc.accent_color = { hex: "#E8952F", source: "fallback" };

  const n = doc.sample_times_s.length;
  const shift = 23; // so the second dancer is not a frame-for-frame twin
  const a = doc.persons[0];
  const b = structuredClone(a);
  b.person_id = "person_2";
  b.track_id = 2;
  // Its own GLB, because this script writes one per person_id. Same clip_id is
  // fine and is what the real exporter produces — the contract only requires
  // each person carry its own resolvable reference, not a unique clip name.
  b.animation = { ...a.animation, glb_asset_id: `${a.animation.glb_asset_id}_b` };
  b.samples = Array.from({ length: n }, (_, i) => structuredClone(a.samples[(i + shift) % n]));
  b.root_trajectory = Array.from({ length: n }, (_, i) => structuredClone(a.root_trajectory[(i + shift) % n]));
  b.crop_rects = {
    hands: Array.from({ length: n }, (_, i) => structuredClone(a.crop_rects.hands[(i + shift) % n])),
    feet: Array.from({ length: n }, (_, i) => structuredClone(a.crop_rects.feet[(i + shift) % n])),
  };
  for (let i = 0; i < n; i++) {
    a.root_trajectory[i].position[0] -= half;
    b.root_trajectory[i].position[0] += half;
  }

  // A crossing: track confidence collapses where the two overlap. DESIGN §7a2 —
  // mark the span uncertain on BOTH, never silently swap identity.
  for (const p of [a, b]) {
    for (let i = 128; i <= 146; i++) {
      for (const j of p.samples[i].joints) {
        j.visibility = "uncertain";
        j.provenance = { observed: j.provenance.observed, interpolated: true, suppressed: "low_confidence" };
      }
      p.root_trajectory[i].provenance = { observed: true, interpolated: true, suppressed: "low_confidence" };
    }
  }
  doc.persons = [a, b];
  return doc;
}

/* ------------------------------------- derived travelling document (see note) */

/**
 * A dancer who actually crosses the floor.
 *
 * WHY THIS IS SYNTHETIC AND MUST STAY LABELLED SO. `root_trajectory` in every real
 * document today is effectively constant — the pipeline pins the dancer to the origin
 * and world placement is unresolved (OPEN-DECISIONS E6, under research on the
 * `world-placement` branch). So there is nothing for a follow camera to follow, and
 * no way to tell a working follow rig from a broken one on the shipped fixtures.
 *
 * This document adds travel and CHANGES NOTHING ELSE: the same joint rotations, the
 * same visibility, the same timeline. It is the second regime the viewer has to work
 * in. It is derived here rather than added to `packages/motion-contract/fixtures/`
 * precisely because it is not pipeline output — inventing a travelling clip in the
 * frozen contract package would suggest the pipeline produces one. Delete this the
 * day E6 lands and a real travelling clip exists.
 *
 * The path: 2.6 m laterally and 1.5 m in depth — lateral so the dancer would slide
 * out of frame without follow, depth so they would visibly shrink without it. Both
 * failure modes the feature exists to fix, in one clip. Motion is confined to the
 * middle of the clip so the fixture also exercises the still -> travelling -> still
 * transition, which is where the deadzone and the lag are visible.
 */
function buildTravellingDancer(good) {
  const doc = structuredClone(good);
  doc.job_id = "job_dev_travelling_00000000000000000000000";
  const t = doc.sample_times_s;
  const p = doc.persons[0];
  const span = t[t.length - 1];
  for (let i = 0; i < t.length; i++) {
    // 0 -> 1 -> 0 over the middle 60% of the clip, smoothstepped so the dancer starts
    // and stops rather than teleporting into motion.
    const u = Math.min(Math.max((t[i] / span - 0.2) / 0.6, 0), 1);
    const s = u * u * (3 - 2 * u);
    const swing = Math.sin(s * Math.PI * 2) * 0.5 + s * 0.5; // net displacement, not a loop
    p.root_trajectory[i].position[0] += swing * 2.6;
    p.root_trajectory[i].position[2] += Math.sin(s * Math.PI) * 1.5;
  }
  return doc;
}

/* ---------------------------------------------------------------------- main */

const lessons = [
  { name: "good-lesson", doc: JSON.parse(readFileSync(path.join(contractFixtures, "good-lesson.json"), "utf-8")) },
  { name: "failure-lesson", doc: JSON.parse(readFileSync(path.join(contractFixtures, "failure-lesson.json"), "utf-8")) },
];
lessons.push({ name: "two-dancers", doc: buildTwoDancers(lessons[0].doc) });
// 4.4 m apart — past FOLLOW.cutDistance, so switching dancer cuts instead of gliding.
// Both sides of that rule need to be reachable in the viewer or neither is verified.
lessons.push({
  name: "two-dancers-apart",
  doc: (() => {
    const d = buildTwoDancers(lessons[0].doc, 2.2);
    d.job_id = "job_dev_two_dancers_apart_00000000000000000";
    // No beat proposal. `proposed_counts` is optional and absence is a normal
    // outcome — a silent clip, no audio track, or a tracker that found fewer
    // than two beats — so the viewer's "counts are not set for this clip"
    // branch needs a fixture to be reachable in, or it is never looked at.
    delete d.proposed_counts;
    return d;
  })(),
});
lessons.push({ name: "travelling", doc: buildTravellingDancer(lessons[0].doc) });
// The same travelling path, but with the floor taken away — the regime DESIGN.md §10
// forbids drawing a floor in, and the one every real clip is currently in.
lessons.push({
  name: "travelling-no-floor",
  doc: (() => {
    const d = buildTravellingDancer(lessons[0].doc);
    d.job_id = "job_dev_travelling_nofloor_000000000000000";
    d.grounding = { status: "none", floor_plane: null };
    return d;
  })(),
});

for (const { name, doc } of lessons) {
  writeFileSync(path.join(outDir, `${name}.json`), JSON.stringify(doc));
  const video = writeVideo(doc, path.join(outDir, `${name}.mp4`));
  const glbs = [];
  for (const person of doc.persons) {
    const file = path.join(outDir, `${name}.${person.person_id}.glb`);
    const tracks = await writeGlb(doc, person, file);
    glbs.push(`${path.basename(file)} (${tracks} tracks)`);
  }
  console.log(`${name}: video ${video}, ${doc.sample_times_s.length} samples, ${glbs.join(", ")}`);
}
