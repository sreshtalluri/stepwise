"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import { REGIONS, HAND_JOINTS, FOOT_JOINTS, lookupJoint } from "../lib/regions";
import {
  sampleIndexAt,
  regionVisibility,
  absentNotes,
  dancerColor,
  followStep,
  deadzoneFor,
  damp,
  rootPlacementObserved,
  rootPositionAt,
  soleLift,
  sourceProjection,
  stageBasis,
  orbitPosition,
  FOLLOW,
  VIEW_PRESETS,
  type MotionResult,
  type ViewId,
  type Visibility,
  type Vec3,
} from "../lib/motion";

/* ----------------------------------------------------------------- materials */

/**
 * DESIGN.md §10: toon, two-tone, no specular / rim / fresnel. The dark step sits at
 * 70% lightness of the accent, which is the shadow side the design specifies. The
 * two-tone break is load-bearing — a flat single fill reads as a bathroom pictogram.
 */
function toonRamp(): THREE.DataTexture {
  // Two tones: the shadow side is the accent at 70% lightness, per DESIGN.md §10.
  //
  // Four texels rather than two, and only to move the break. three samples the ramp
  // at `dot(N,L) * 0.5 + 0.5`, so a two-texel ramp puts the terminator at dot = 0 —
  // exactly on the silhouette, where it is invisible and the figure goes back to
  // reading as one flat fill. Breaking at the 3/4 texel boundary puts it at dot = 0.5,
  // about 60 degrees off the light, which is where a form-describing terminator sits.
  const tex = new THREE.DataTexture(new Uint8Array([179, 179, 179, 255]), 4, 1, THREE.RedFormat);
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  // Mipmaps would blur the two steps back into the smooth ramp we are avoiding.
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/**
 * The `uncertain` surface. DESIGN.md §4 plus the review finding in §13.4: a dashed
 * or detached silhouette reads as BROKEN, not unsure — the uncertainty has to live
 * in the surface and the limb has to stay attached to the body. So: desaturated to
 * grey, plus a hatch across the surface whose phase is regenerated at a low rate so
 * it shimmers slightly. No opacity encoding (forbidden, DESIGN.md §12.4) and no
 * confident pose in a lighter tint (§12.11).
 *
 * This is the interim treatment. E2 in OPEN-DECISIONS.md is still OPEN and cannot be
 * closed against a capsule stand-in — it has to be judged on a real MHR mesh.
 */
function uncertainMaterial(ramp: THREE.DataTexture): THREE.MeshToonMaterial {
  const mat = new THREE.MeshToonMaterial({ color: "#8A847C", gradientMap: ramp });
  mat.userData.seed = { value: 0 };
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uSeed = mat.userData.seed;
    shader.fragmentShader = shader.fragmentShader
      .replace("void main() {", "uniform float uSeed;\nvoid main() {")
      .replace(
        "#include <dithering_fragment>",
        `#include <dithering_fragment>
        float hatch = sin((vViewPosition.x - vViewPosition.y) * 150.0 + uSeed * 6.2831853);
        float wob = sin((vViewPosition.x + vViewPosition.y) * 37.0 + uSeed * 12.0) * 0.25;
        gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.40, 0.385, 0.365), step(0.0, hatch + wob) * 0.5);`,
      );
  };
  return mat;
}

/**
 * Bounds the view presets frame against, refreshed from the posed skeleton.
 *
 * Also the single source of truth for the video pane's crop: `LessonViewer` owns this
 * ref, passes it down, and projects `body` through the clip's camera. One number
 * frames both panes, so they cannot drift apart (see `projectBoxToFrame`).
 */
export interface Focus {
  body: THREE.Box3;
  hands: THREE.Box3;
  feet: THREE.Box3;
}

/* -------------------------------------------------------------------- dancer */

interface DancerProps {
  doc: MotionResult;
  personIndex: number;
  selectedIndex: number;
  timeRef: RefObject<number>;
  mirrored: boolean;
  onAbsent?: (notes: string[]) => void;
  focusRef?: RefObject<Focus | null>;
  glbUrl: string;
}

function Dancer({ doc, personIndex, selectedIndex, timeRef, mirrored, onAbsent, focusRef, glbUrl }: DancerProps) {
  const gltf = useGLTF(glbUrl);
  const ramp = useMemo(toonRamp, []);

  // SkeletonUtils clone, not scene.clone: a cached GLTF scene cannot be mounted into
  // two React trees (compare mode does exactly that) and skinned meshes need their
  // bones re-bound to the cloned skeleton.
  const { scene, mixer, clip, regionMeshes, stubs, bonesByName } = useMemo(() => {
    const scene = cloneSkeleton(gltf.scene) as THREE.Group;
    const mixer = new THREE.AnimationMixer(scene);
    // Per-PERSON animation ref (W8 contract change): `animation` moved from the
    // top level into PersonResult, so each dancer names its own clip.
    const clipId = doc.persons[personIndex]?.animation?.clip_id;
    const clip = gltf.animations.find((c) => c.name === clipId) ?? gltf.animations[0];

    const regionMeshes = new Map<string, THREE.SkinnedMesh>();
    const bonesByName = new Map<string, THREE.Bone>();
    scene.traverse((o) => {
      if ((o as THREE.Bone).isBone) bonesByName.set(o.name, o as THREE.Bone);
      if ((o as THREE.SkinnedMesh).isSkinnedMesh && o.name.startsWith("region_")) {
        regionMeshes.set(o.name.slice("region_".length), o as THREE.SkinnedMesh);
      }
    });

    // DESIGN.md §4 `absent`: not drawn, but a stub with real weight at the last known
    // joint — a thin dotted line is invisible at phone scale. Parented to the bone so
    // it follows the animation for free.
    const jointByName = new Map(doc.joint_hierarchy.joints.map((j) => [j.name, j]));
    const stubs = new Map<string, THREE.Mesh>();
    for (const region of REGIONS) {
      const def = lookupJoint(jointByName, region.bone);
      const bone = def && bonesByName.get(def.glb_node_name);
      if (!bone) continue;
      const stub = new THREE.Mesh(
        new THREE.CylinderGeometry(0.016, 0.016, 0.085, 8),
        new THREE.MeshBasicMaterial({ color: "#9A9188" }),
      );
      stub.position.y = -0.045;
      stub.visible = false;
      bone.add(stub);
      stubs.set(region.id, stub);
    }
    return { scene, mixer, clip, regionMeshes, stubs, bonesByName };
  }, [gltf, doc]);

  // play() has to pair with its own stopAllAction, and both have to live in the same
  // effect: React re-runs effects on remount (StrictMode does it on every mount in
  // dev), and a cleanup that stops an action started in a useMemo leaves the mixer
  // permanently dead — mixer.setTime() then silently does nothing.
  //
  // Nothing sets action.paused either: a paused action has an effective timeScale of
  // zero, which also makes setTime() a no-op. The mixer is never ticked by delta —
  // every frame calls mixer.setTime(mediaTime), so the video is the only clock.
  useEffect(() => {
    mixer.clipAction(clip).play();
    return () => void mixer.stopAllAction();
  }, [mixer, clip]);

  // Material per region, rebuilt only when the colour or selection changes.
  const materials = useMemo(() => {
    const accent = dancerColor(doc, personIndex, selectedIndex);
    return {
      observed: new THREE.MeshToonMaterial({ color: accent, gradientMap: ramp }),
      uncertain: uncertainMaterial(ramp),
    };
  }, [doc, personIndex, selectedIndex, ramp]);

  const lastIndex = useRef(-1);

  // Mirroring flips the winding order, so the correct facing side flips with it.
  useEffect(() => {
    const side = mirrored ? THREE.BackSide : THREE.FrontSide;
    for (const mat of Object.values(materials)) {
      mat.side = side;
      mat.shadowSide = side;
      mat.needsUpdate = true;
    }
    // Meshes are only re-materialised when the sample index changes, which never
    // happens while the video is paused — so switching dancers on a still frame would
    // leave the old accent on screen. Invalidate the cached index instead.
    lastIndex.current = -1;
  }, [materials, mirrored]);

  const lastNotes = useRef<string>("");
  const box = useRef(new THREE.Box3());
  const scratch = useRef(new THREE.Vector3());

  /**
   * World placement (OPEN-DECISIONS E6, route B). The GLB is a pose clip in the
   * character's own frame — its `root` node carries a CONSTANT translation
   * (measured on real solo-01 output: no translation channel at all, a static
   * `[0, 0.924, 0]`), so animating it alone dances the dancer in place. The travel
   * lives in `root_trajectory`, and this group is what puts it back.
   *
   * Two refs, and the second one is the reason this is not simply
   * `group.position = root_trajectory[t]`: the offset is measured as
   * `world − wherever the clip alone put the root`. On today's export that
   * subtrahend is the constant above; on a fixture or a future export that DOES
   * compose the translation into the GLB it is the world position itself and the
   * offset collapses to zero. Same code, no regime flag, no double-counting.
   */
  const placeRef = useRef<THREE.Group>(null);
  const rootBone = useMemo(() => {
    const def = doc.joint_hierarchy.joints[doc.joint_hierarchy.root_joint_index];
    return (def && bonesByName.get(def.glb_node_name)) ?? null;
  }, [doc, bonesByName]);
  // Whole-clip fact, so it is read once, not 60 times a second.
  const placed = useMemo(() => rootPlacementObserved(doc, personIndex), [doc, personIndex]);

  /**
   * Sole contact (see `soleLift`). The floor and the placement both measure foot
   * JOINTS; the drawn sole hangs ~3 cm under them, so without this the feet sink
   * into the floor on almost every frame. Only for a placed dancer on a grounded
   * floor — a never-placed dancer has no position relative to any floor to correct.
   */
  const floor = useMemo(() => {
    const plane = doc.grounding.status === "none" ? null : doc.grounding.floor_plane;
    if (!plane || !placed) return null;
    const feet = ["foot_l", "foot_r"].flatMap((id) => regionMeshes.get(id) ?? []);
    if (!feet.length) return null;
    return { normal: new THREE.Vector3(...plane.normal).normalize(), point: new THREE.Vector3(...plane.point), feet };
  }, [doc, placed, regionMeshes]);
  const lift = useRef<number[] | null>(null);

  /**
   * Lowest drawn sole along the floor normal, relative to the root bone, in the
   * placement group's frame (so the mirror, applied on the child, is included).
   * Needs the scene's world matrices current for the pose just set.
   */
  const soleBelowRoot = (): number => {
    const place = placeRef.current!;
    const { normal, feet } = floor!;
    place.updateMatrixWorld(true);
    const rootAt = place.worldToLocal(rootBone!.getWorldPosition(scratch.current)).dot(normal);
    let low = Infinity;
    const v = vertex.current;
    for (const mesh of feet) {
      const count = mesh.geometry.attributes.position.count;
      for (let i = 0; i < count; i++) {
        low = Math.min(low, place.worldToLocal(mesh.localToWorld(mesh.getVertexPosition(i, v))).dot(normal));
      }
    }
    return low - rootAt;
  };
  const vertex = useRef(new THREE.Vector3());

  // Once per clip, after the action is playing (the effect above): pose every sample,
  // measure the sole against the floor at the placed root, derive the lift.
  useEffect(() => {
    lift.current = null;
    if (!floor || !rootBone || !placeRef.current) return;
    const gaps = doc.sample_times_s.map((t, k) => {
      mixer.setTime(t);
      const root = new THREE.Vector3(...(doc.persons[personIndex].root_trajectory[k].position as Vec3));
      return root.sub(floor.point).dot(floor.normal) + soleBelowRoot();
    });
    lift.current = soleLift(gaps);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- soleBelowRoot only reads refs and `floor`
  }, [doc, personIndex, floor, rootBone, mixer, clip]);

  useFrame((_, delta) => {
    const t = timeRef.current ?? 0;
    mixer.setTime(t);

    // Placement BEFORE anything reads a world position: the focus box below, and
    // through it the follow camera and the video pane's crop, are all supposed to
    // be about where the dancer is IN THE ROOM.
    //
    // Same clock as the pose, by construction — one `t`, read once, feeding
    // mixer.setTime and rootPositionAt in the same frame. Nothing here samples an
    // index, a React state or a second timer.
    //
    // `placed` false means this track was never solved; it stays exactly where the
    // clip puts it rather than being offset by a placeholder that is not a place.
    // See rootPlacementObserved.
    const place = placeRef.current;
    if (place && placed && rootBone) {
      const world = rootPositionAt(doc, personIndex, t);
      // Where the clip alone puts the root, expressed in this group's own frame, so
      // it is independent of the offset we are about to write (and already includes
      // the mirror flip, which is applied on the child). getWorldPosition refreshes
      // the bone's world matrix from the pose mixer.setTime just wrote.
      place.worldToLocal(rootBone.getWorldPosition(scratch.current));
      place.position.set(world[0] - scratch.current.x, world[1] - scratch.current.y, world[2] - scratch.current.z);

      if (floor && lift.current) {
        // The per-sample lift, lerped on the same clock as the pose and the root,
        // then checked against the live sole: the mixer lerps rotations between
        // samples, so a foot can dip between two samples that each clear the floor.
        const times = doc.sample_times_s;
        const i = sampleIndexAt(times, t);
        const span = i + 1 < times.length ? times[i + 1] - times[i] : 0;
        const u = span > 0 ? Math.min(Math.max((t - times[i]) / span, 0), 1) : 0;
        const planned = lift.current[i] + ((lift.current[i + 1] ?? lift.current[i]) - lift.current[i]) * u;
        const height = scratch.current.set(...world).sub(floor.point).dot(floor.normal) + soleBelowRoot();
        place.position.addScaledVector(floor.normal, Math.max(planned, -height));
      }
    }

    // Visibility is a step lookup on sample_times_s — never interpolated across a
    // suppressed span, and never derived from index/fps arithmetic.
    const i = sampleIndexAt(doc.sample_times_s, t);
    if (i !== lastIndex.current) {
      lastIndex.current = i;
      const vis = regionVisibility(doc, personIndex, i);
      for (const region of REGIONS) {
        const mesh = regionMeshes.get(region.id);
        const state: Visibility = vis.get(region.id) ?? "absent";
        if (mesh) {
          mesh.visible = state !== "absent";
          mesh.material = state === "uncertain" ? materials.uncertain : materials.observed;
          // DESIGN.md §4: only `observed` contributes to the contact shadow.
          mesh.castShadow = state === "observed";
        }
        const stub = stubs.get(region.id);
        if (stub) stub.visible = state === "absent";
      }
      if (onAbsent) {
        const notes = absentNotes(vis);
        const key = notes.join("|");
        if (key !== lastNotes.current) {
          lastNotes.current = key;
          onAbsent(notes);
        }
      }
    }

    // ~6 Hz reseed: the sketchy surface shimmers, it does not strobe.
    const seed = materials.uncertain.userData.seed;
    seed.value += delta * 6;
    if (seed.value > 1e6) seed.value = 0;

    if (focusRef) {
      // Bounds from the POSED BONES, not Box3.setFromObject. A SkinnedMesh reports
      // its bind-pose geometry box, which here is centred on the pelvis at the origin
      // — so framing off it aims the camera at the floor and pushes the dancer into
      // the top of the panel.
      box.current.makeEmpty();
      for (const bone of bonesByName.values()) {
        box.current.expandByPoint(bone.getWorldPosition(scratch.current));
      }
      box.current.expandByScalar(0.14); // the surface stands off the bones
      focusRef.current = {
        body: box.current.clone(),
        hands: boneBox(bonesByName, doc, HAND_JOINTS, 0.1),
        feet: boneBox(bonesByName, doc, FOOT_JOINTS, 0.1),
      };
    }
  });

  // The mirror stays on the inner object, not on the placement group: it is meant to
  // flip the BODY so a learner can copy a limb, and it flips about the group's own
  // origin, i.e. about the dancer. Hoisting it onto the placement group would reflect
  // the travel about world x = 0 instead — which is the camera's optical axis, not a
  // wall — and would also double-flip the video pane's crop, which is projected from
  // these same bounds and then CSS-mirrored (`useVideoCrop`). Whether a mirrored
  // lesson should mirror the PATH as well as the body is a real question and an open
  // one; it is not answered here, and today's behaviour is preserved exactly.
  return (
    <group ref={placeRef}>
      <primitive object={scene} scale-x={mirrored ? -1 : 1} />
    </group>
  );
}

/** World-space bounds of a named set of joints, padded for the surface around them. */
function boneBox(bones: Map<string, THREE.Bone>, doc: MotionResult, names: string[], pad: number): THREE.Box3 {
  const box = new THREE.Box3();
  const byName = new Map(doc.joint_hierarchy.joints.map((j) => [j.name, j]));
  for (const name of names) {
    const def = lookupJoint(byName, name);
    const bone = def && bones.get(def.glb_node_name);
    if (bone) box.expandByPoint(bone.getWorldPosition(new THREE.Vector3()));
  }
  return box.isEmpty() ? box : box.expandByScalar(pad);
}

/* ------------------------------------------------------------- floor + light */

function Floor({ doc }: { doc: MotionResult }) {
  // DESIGN.md §10 / contract: when grounding failed, draw NO floor. Never fake a plane.
  const plane = doc.grounding.status === "none" ? null : doc.grounding.floor_plane;

  /**
   * The disc sits ON the fitted plane — at its point, tilted to its normal — rather
   * than horizontally at `point[1]`.
   *
   * This used to be `position={[0, point[1], 0]}` with a fixed −90° rotation, which
   * is only correct for a level camera, and it was invisible while the dancer stood
   * at the origin: at one spot every plane through that spot looks the same.
   * `root_trajectory` now carries real travel, and solo-01's camera is pitched 13°
   * up, so the error is no longer a rounding detail. Measured on the shipped
   * document: over the dancer's own 8.25 m of depth the fitted plane drops 1.92 m,
   * and against a flat disc at `point[1]` the root height ranges −0.94 m to +0.94 m
   * — the dancer walks a metre under the floor at the far end. Against the real
   * plane it stays 0.63–1.05 m above it for the whole clip, which is a pelvis
   * height that crouches. Drawing the plane the grounding solver actually fitted is
   * also the only version that is honest: the document states a normal.
   */
  const quaternion = useMemo(
    () =>
      plane
        ? new THREE.Quaternion().setFromUnitVectors(UP, new THREE.Vector3(...plane.normal).normalize())
        : null,
    [plane],
  );
  if (!plane || !quaternion) return null;

  return (
    <group position={plane.point as [number, number, number]} quaternion={quaternion}>
      {/* A real surface first. Mockup finding §13.2: a 1px line is not a floor — the
          material has to sit clearly above --stage so the horizon is unmistakable.
          The fog below is what turns the far edge into that horizon rather than a
          hard disc rim.

          Depth-tested like any surface. It used to slice the toes off because the
          sole sat 3–4 cm under the fitted plane on most frames; the Dancer's sole
          contact (`soleLift`) now keeps a placed dancer's feet on top of it, so a
          foot that shows up cut here is a real regression, not a thing to hide. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[18, 64]} />
        <meshStandardMaterial color="#8E8071" roughness={0.95} metalness={0} />
      </mesh>
    </group>
  );
}

/**
 * DESIGN.md §9, the signature motion: the contact shadow swings as you orbit.
 * It is a real shadow from a world-fixed key light, so it stays put in the room
 * while the camera moves around it — which is exactly what makes it read as a body
 * standing on a floor rather than floating. It is information, so it keeps moving
 * under prefers-reduced-motion; only the UI transitions stop.
 *
 * The second light follows the camera and casts nothing. Its only job is to keep the
 * two-tone break on the near side of the body no matter where you orbit to.
 */
const UP = new THREE.Vector3(0, 1, 0);
const FILL_OFFSET = THREE.MathUtils.degToRad(40);
/** Today's key-light position, kept as the key DIRECTION once the rig has to move. */
const KEY_DIR = new THREE.Vector3(2.6, 4.2, 1.9).normalize();

/**
 * Where the key light stands, and how big its shadow volume has to be.
 *
 * A directional light's shadow is an orthographic box hung at the light and aimed at
 * its target, so the constants that used to be literals here (`±4` wide, `far 12`,
 * light at `[2.6, 4.2, 1.9]` aimed at the origin) silently assumed the dancer stands
 * at the origin. They did, until `root_trajectory` started carrying travel. On real
 * solo-01 the dancer walks to z = −11 m, which is 14.4 m from that light — past
 * `far`, and far outside the box — so the contact shadow, the thing DESIGN.md §9
 * makes the body read as standing on the floor rather than floating, simply stops
 * being drawn partway through the clip.
 *
 * So the box is sized from the document instead. The light's DIRECTION is unchanged
 * (`KEY_DIR` is the old position normalized), which is all a directional light
 * contributes to shading — the two-tone break and the direction the shadow falls are
 * byte-for-byte what they were. Only the frustum moves, and it stays as tight as the
 * clip allows: solo-01 costs 5.7 mm per shadow texel against the old 3.9 mm.
 *
 * The origin is always included because that is where a never-placed dancer stands
 * (see rootPlacementObserved) — their `root_trajectory` is a placeholder that is not
 * a place, and sizing a shadow box to it would stretch the map over empty room.
 */
function keyLightRig(doc: MotionResult) {
  const box = new THREE.Box3().setFromPoints([new THREE.Vector3(0, 0, 0)]);
  doc.persons.forEach((person, i) => {
    if (!rootPlacementObserved(doc, i)) return;
    for (const s of person.root_trajectory) box.expandByPoint(new THREE.Vector3(...(s.position as Vec3)));
  });
  const centre = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  // +1.5 m for the body around the root it is hung from; floor of 4 keeps the old
  // "several dancers side by side" width on a clip that does not travel.
  const half = Math.max(4, Math.max(size.x, size.y, size.z) / 2 + 1.5);
  const distance = half + 6;
  return {
    position: centre.clone().addScaledVector(KEY_DIR, distance),
    target: centre,
    half,
    far: distance + half + 4,
  };
}

function Lights({ doc, grounded }: { doc: MotionResult; grounded: boolean }) {
  const fill = useRef<THREE.DirectionalLight>(null);
  const key = useRef<THREE.DirectionalLight>(null);
  const rig = useMemo(() => keyLightRig(doc), [doc]);
  // The target is not mounted in the scene graph, so its world matrix is ours to
  // keep — three reads `light.target.matrixWorld` and never updates it for us.
  useEffect(() => {
    if (!key.current) return;
    key.current.target.position.copy(rig.target);
    key.current.target.updateMatrixWorld();
  }, [rig]);
  useFrame(({ camera }) => {
    if (!fill.current) return;
    // Offset 40 degrees off the view axis. Head-on it would light the body flat and
    // the two-tone break — which is what stops the figure reading as a pictogram —
    // would disappear exactly when you looked straight at it.
    fill.current.position.copy(camera.position).applyAxisAngle(UP, FILL_OFFSET).multiplyScalar(0.6);
    fill.current.position.y = Math.max(fill.current.position.y, 1.6) + 1.0;
  });
  return (
    <>
      {/* Intensities are deliberately low and sum to ~1.1. A toon ramp only shows its
          break while the lit side is below clipping — turn these up and the two-tone
          collapses into one flat fill, which is the pictogram failure mode. */}
      <ambientLight intensity={0.18} />
      <directionalLight
        ref={key}
        position={rig.position}
        intensity={grounded ? 0.3 : 0.5}
        castShadow={grounded}
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0015}
        shadow-normalBias={0.02}
        // Wide enough for several dancers side by side, and for a dancer who
        // crosses the room — see keyLightRig.
        shadow-camera-left={-rig.half}
        shadow-camera-right={rig.half}
        shadow-camera-top={rig.half}
        shadow-camera-bottom={-rig.half}
        shadow-camera-near={0.5}
        shadow-camera-far={rig.far}
      />
      <directionalLight ref={fill} intensity={0.68} />
    </>
  );
}

/* ------------------------------------------------------------- view presets */

/**
 * Distance at which `bounds` exactly fills the panel for this camera.
 *
 * Frame the body to the panel rather than to a fixed distance: the two stages are
 * very different shapes on phone and desktop, and a preset that crops the feet on one
 * of them is not a preset.
 */
function frameRadius(bounds: THREE.Box3, cam: THREE.PerspectiveCamera, margin: number): number {
  const size = bounds.getSize(new THREE.Vector3());
  const halfV = THREE.MathUtils.degToRad(cam.fov) / 2;
  const halfH = Math.atan(Math.tan(halfV) * cam.aspect);
  return Math.max(size.y / 2 / Math.tan(halfV), Math.max(size.x, size.z) / 2 / Math.tan(halfH)) * 1.18 * margin;
}

/**
 * The overlay view's camera: the clip's own camera, pose from `camera_to_world` and
 * projection from the intrinsics, fitted to the canvas the way `object-fit: contain`
 * fits the video under it. No orbit, no follow — the one angle that is not estimated.
 */
function SourceCamera({ doc }: { doc: MotionResult }) {
  const { camera, size } = useThree();
  useEffect(() => {
    new THREE.Matrix4().fromArray(doc.camera.camera_to_world).decompose(camera.position, camera.quaternion, new THREE.Vector3());
    camera.updateMatrixWorld();
  }, [camera, doc]);
  // Every frame, not on resize: R3F rewrites the projection from fov/aspect whenever
  // the canvas resizes, and would silently undo this.
  useFrame(() => {
    camera.projectionMatrix.set(...(sourceProjection(doc, size.width, size.height) as Parameters<THREE.Matrix4["set"]>));
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
  });
  return null;
}

/**
 * The view preset AND the follow rig — the two are deliberately one component,
 * because they are two axes of the same camera and have to compose rather than
 * override each other:
 *
 *   the preset  decides the DIRECTION you look from (azimuth/elevation), and is a
 *               one-shot: it aims the camera, then hands over to OrbitControls so
 *               the learner can orbit freely.
 *   follow      decides WHAT is looked at and from HOW FAR, every frame, and does it
 *               by translating the whole orbit rig — target and camera move by the
 *               same delta — so the learner's orbit angle survives untouched. You can
 *               orbit a following camera, and following never resets your angle.
 *
 * With follow off this is byte-for-byte the old one-shot behaviour.
 */
function ViewRig({
  doc,
  view,
  follow,
  selectedIndex,
  focusRef,
  controlsRef,
}: {
  doc: MotionResult;
  view: ViewId;
  follow: boolean;
  selectedIndex: number;
  focusRef: RefObject<Focus | null>;
  controlsRef: RefObject<any>;
}) {
  const { camera, size } = useThree();
  const applied = useRef<ViewId | null>(null);
  /** Where the camera is currently aiming — the damped, deadzoned follow point. */
  const aim = useRef<Vec3>([0, 0, 0]);
  /** The framing distance the rig is driving toward, before the learner's own zoom. */
  const autoDist = useRef(0);
  /** Distance we last wrote, so a change means the learner dollied. */
  const lastDist = useRef(0);
  /**
   * The learner's zoom, kept as a RATIO of the automatic framing rather than an
   * absolute distance. Without this, follow's per-frame distance correction would
   * silently overwrite the scroll wheel; with it, someone who zooms in twice as close
   * stays twice as close as the dancer moves toward and away from the camera.
   */
  const zoomBias = useRef(1);
  const switching = useRef(false);

  // Presets frame the body to the panel, so a panel that changes shape — turning on
  // compare, promoting a stage, rotating the phone — has to re-frame or it crops.
  useEffect(() => {
    applied.current = null;
  }, [size.width, size.height]);

  // A dancer switch is resolved on the next frame, once the newly selected dancer has
  // written its own bounds into focusRef.
  useEffect(() => {
    switching.current = true;
  }, [selectedIndex]);

  const subject = useRef(new THREE.Vector3());
  const delta = useRef(new THREE.Vector3());
  const offset = useRef(new THREE.Vector3());
  const extent = useRef(new THREE.Vector3());
  // Every estimated view orbits the FLOOR's up, not the phone's (see `stageBasis`);
  // "camera" keeps the source camera's own axes. The follow and orbit code below is
  // direction-agnostic, so this basis and `camera.up` are all that change.
  const basis = useMemo(() => stageBasis(doc, view !== "camera"), [doc, view]);

  useFrame((_, dt) => {
    const focus = focusRef.current;
    const controls = controlsRef.current;
    if (!focus || !controls) return;

    const preset = VIEW_PRESETS.find((p) => p.id === view)!;
    // Close-ups frame the hands or feet themselves, not a fraction of the whole body:
    // a dancer in a wide pose and a dancer with arms down need very different
    // distances for the same "hands" preset.
    const bounds = focus[preset.focus].isEmpty() ? focus.body : focus[preset.focus];
    const cam = camera as THREE.PerspectiveCamera;
    bounds.getCenter(subject.current);
    const radius = frameRadius(bounds, cam, preset.distance);

    // DESIGN.md §7a2: switching dancer is one tap and the lesson re-anchors. How it
    // re-anchors depends on how far it has to go. Within `cutDistance` the follow
    // damping simply walks the camera across, which keeps the spatial relationship
    // between the two bodies legible — you SEE that you moved to the person on the
    // left. Beyond it a glide is a slow pan across empty floor that tells you nothing
    // and loses the dancer for a second, so it cuts instead. Same rule the rest of
    // the viewer uses: show the relationship when it is readable, do not fake one
    // when it is not.
    if (switching.current) {
      switching.current = false;
      const far = subject.current.distanceTo(new THREE.Vector3(...aim.current)) > FOLLOW.cutDistance;
      if (!follow || far) applied.current = null;
    }

    // ---- one-shot: mount, view change, resize, double-tap reset, or a hard cut ----
    if (applied.current !== view) {
      applied.current = view;
      aim.current = [subject.current.x, subject.current.y, subject.current.z];
      autoDist.current = radius;
      lastDist.current = radius * zoomBias.current;
      camera.position.set(...orbitPosition(basis, aim.current, preset.azimuth, preset.elevation, lastDist.current));
      // OrbitControls caches the rotation from `camera.up` to +Y at construction and
      // orbits (and clamps polar angle, i.e. "never under the floor") in that frame.
      camera.up.set(...basis.up);
      // drei's OrbitControls is three-stdlib's, which keeps this rotation in a closure
      // (no `_quat`), so it cannot be re-levelled here; only three's own exposes it.
      // ponytail: guarded so it stops throwing every view change; re-level stdlib by
      // remounting OrbitControls with camera.up already set if the tilt shows.
      if (controls._quat) {
        controls._quat.setFromUnitVectors(camera.up, UP);
        controls._quatInverse.copy(controls._quat).invert();
      }
      controls.target.copy(subject.current);
      controls.update();
      return;
    }

    // Follow off: hand the camera to OrbitControls and never touch it again — this is
    // exactly the pre-existing behaviour, so the toggle is a true no-op when off.
    if (!follow) return;

    // A distance we did not write means the learner dollied. Record it as a ratio.
    const now = camera.position.distanceTo(controls.target);
    if (Math.abs(now - lastDist.current) > 1e-4 && autoDist.current > 0) {
      zoomBias.current = THREE.MathUtils.clamp(now / autoDist.current, 0.2, 5);
    }

    aim.current = followStep(
      aim.current,
      [subject.current.x, subject.current.y, subject.current.z],
      deadzoneFor(bounds.getSize(extent.current).y),
      dt,
    );
    autoDist.current = damp(autoDist.current, radius, FOLLOW.tauDistance, Math.min(dt, 0.1));

    // Translate the whole rig: moving target and camera by the same vector leaves
    // `camera.position - target` — which is all OrbitControls stores an orbit as —
    // completely unchanged. This is why follow and orbit compose instead of fighting.
    delta.current.set(aim.current[0], aim.current[1], aim.current[2]).sub(controls.target);
    controls.target.add(delta.current);
    camera.position.add(delta.current);

    // Then set the framing distance along the direction the learner is looking from.
    offset.current.copy(camera.position).sub(controls.target);
    const want = autoDist.current * zoomBias.current;
    if (offset.current.lengthSq() > 1e-12) {
      offset.current.setLength(want);
      camera.position.copy(controls.target).add(offset.current);
    }
    controls.update();
    lastDist.current = camera.position.distanceTo(controls.target);
  });
  return null;
}

/* --------------------------------------------------------------- the canvas */

export interface Stage3DProps {
  doc: MotionResult;
  selectedIndex: number;
  view: ViewId;
  mirrored: boolean;
  timeRef: RefObject<number>;
  /**
   * Keep the selected dancer framed at a constant, studiable size. A separate axis
   * from `view` — see ViewRig.
   */
  follow?: boolean;
  /**
   * Optional: the caller's own handle on the selected dancer's live world bounds,
   * written every frame. `LessonViewer` passes one so the video pane can crop to the
   * SAME bounds this stage frames — see `projectBoxToFrame`. A ref, not a callback,
   * because this updates 60 times a second and must not re-render React.
   */
  focusRef?: RefObject<Focus | null>;
  onAbsent?: (notes: string[]) => void;
  /** DESIGN.md §10: double-tap returns to the camera view. */
  onResetView?: () => void;
  /**
   * One GLB URL per entry in `doc.persons`, already resolved by the caller — asset
   * ids in the contract are deliberately not URLs. Keyed by PERSON, which the
   * contract now supports directly: the gap W5 reported here (one top-level
   * `animation.glb_asset_id` for an unbounded `persons`) was closed by W8, which
   * moved `animation` into PersonResult.
   */
  glbUrls: string[];
  /**
   * Render from the source camera onto a transparent canvas, for laying over the
   * `<video>` (the "overlay" view). Drops floor, backdrop, orbit and follow.
   */
  overlay?: boolean;
}

export default function Stage3D({
  doc,
  selectedIndex,
  view,
  mirrored,
  timeRef,
  follow = false,
  focusRef: externalFocusRef,
  onAbsent,
  onResetView,
  glbUrls,
  overlay = false,
}: Stage3DProps) {
  const ownFocusRef = useRef<Focus | null>(null);
  const focusRef = externalFocusRef ?? ownFocusRef;
  const controlsRef = useRef<any>(null);
  const [resetKey, setResetKey] = useState(0);

  return (
    <Canvas
      shadows
      /* `flat` = NoToneMapping. R3F defaults to ACES filmic, which rolls the toon
         ramp's hard terminator into a smooth gradient — the two-tone break, which is
         the whole reason the figure does not read as a pictogram, does not survive it. */
      flat
      dpr={[1, 2]}
      camera={{ fov: 34, position: [0, 1.4, 3.2] }}
      onDoubleClick={() => {
        onResetView?.();
        setResetKey((k) => k + 1);
      }}
      gl={{ antialias: true, alpha: overlay }}
    >
      {/* Overlay: transparent canvas over the video — no backdrop, fog or floor to
          cover the real room. */}
      {!overlay && <color attach="background" args={["#1C1917"]} />}
      {/* The far edge of the floor dissolving into the backdrop IS the horizon. */}
      {!overlay && <fog attach="fog" args={["#1C1917", 9, 24]} />}
      <Lights doc={doc} grounded={!overlay && doc.grounding.status === "grounded"} />
      {!overlay && <Floor doc={doc} />}
      {overlay && <SourceCamera doc={doc} />}
      {doc.persons.map((person, i) => (
        <Dancer
          key={person.person_id}
          doc={doc}
          personIndex={i}
          selectedIndex={selectedIndex}
          timeRef={timeRef}
          mirrored={mirrored}
          glbUrl={glbUrls[i]}
          onAbsent={i === selectedIndex ? onAbsent : undefined}
          focusRef={i === selectedIndex ? focusRef : undefined}
        />
      ))}
      {/* No `selectedIndex` in the key any more: a remount is a hard cut, and with
          follow on a nearby dancer should be glided to instead. ViewRig decides. */}
      {!overlay && <ViewRig
        key={`${view}-${resetKey}`}
        doc={doc}
        view={view}
        follow={follow}
        selectedIndex={selectedIndex}
        focusRef={focusRef}
        controlsRef={controlsRef}
      />}
      {/* Orbit, damped, clamped so the camera never flips over the pole or goes
          under the floor. Pan is off: dragging the stage always orbits, and scrubbing
          only ever happens on the bars (OPEN-DECISIONS C3 — still open, this is the
          lean recorded there). */}
      {!overlay && <OrbitControls
        ref={controlsRef}
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        minPolarAngle={0.12}
        maxPolarAngle={1.52}
        minDistance={0.4}
        maxDistance={9}
      />}
    </Canvas>
  );
}
