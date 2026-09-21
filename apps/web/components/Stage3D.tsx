"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import { REGIONS, HAND_JOINTS, FOOT_JOINTS } from "../lib/regions";
import {
  sampleIndexAt,
  regionVisibility,
  absentNotes,
  dancerColor,
  VIEW_PRESETS,
  type MotionResult,
  type ViewId,
  type Visibility,
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

/** Bounds the view presets frame against, refreshed from the posed skeleton. */
interface Focus {
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
      const def = jointByName.get(region.bone);
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

  useFrame((_, delta) => {
    const t = timeRef.current ?? 0;
    mixer.setTime(t);

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

  return <primitive object={scene} scale-x={mirrored ? -1 : 1} />;
}

/** World-space bounds of a named set of joints, padded for the surface around them. */
function boneBox(bones: Map<string, THREE.Bone>, doc: MotionResult, names: string[], pad: number): THREE.Box3 {
  const box = new THREE.Box3();
  for (const name of names) {
    const def = doc.joint_hierarchy.joints.find((j) => j.name === name);
    const bone = def && bones.get(def.glb_node_name);
    if (bone) box.expandByPoint(bone.getWorldPosition(new THREE.Vector3()));
  }
  return box.isEmpty() ? box : box.expandByScalar(pad);
}

/* ------------------------------------------------------------- floor + light */

function Floor({ doc }: { doc: MotionResult }) {
  // DESIGN.md §10 / contract: when grounding failed, draw NO floor. Never fake a plane.
  if (doc.grounding.status === "none" || !doc.grounding.floor_plane) return null;
  const y = doc.grounding.floor_plane.point[1];
  return (
    <group position={[0, y, 0]}>
      {/* A real surface first. Mockup finding §13.2: a 1px line is not a floor — the
          material has to sit clearly above --stage so the horizon is unmistakable.
          The fog below is what turns the far edge into that horizon rather than a
          hard disc rim. */}
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

function Lights({ grounded }: { grounded: boolean }) {
  const fill = useRef<THREE.DirectionalLight>(null);
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
        position={[2.6, 4.2, 1.9]}
        intensity={grounded ? 0.3 : 0.5}
        castShadow={grounded}
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0015}
        shadow-normalBias={0.02}
        // Wide enough for several dancers side by side, not just one.
        shadow-camera-left={-4}
        shadow-camera-right={4}
        shadow-camera-top={4}
        shadow-camera-bottom={-1}
        shadow-camera-near={0.5}
        shadow-camera-far={12}
      />
      <directionalLight ref={fill} intensity={0.68} />
    </>
  );
}

/* ------------------------------------------------------------- view presets */

function ViewRig({
  view,
  focusRef,
  controlsRef,
}: {
  view: ViewId;
  focusRef: RefObject<Focus | null>;
  controlsRef: RefObject<any>;
}) {
  const { camera, size } = useThree();
  const applied = useRef<ViewId | null>(null);

  // Presets frame the body to the panel, so a panel that changes shape — turning on
  // compare, promoting a stage, rotating the phone — has to re-frame or it crops.
  useEffect(() => {
    applied.current = null;
  }, [size.width, size.height]);

  useFrame(() => {
    const focus = focusRef.current;
    const controls = controlsRef.current;
    if (!focus || !controls || applied.current === view) return;
    applied.current = view;

    const preset = VIEW_PRESETS.find((p) => p.id === view)!;
    // Close-ups frame the hands or feet themselves, not a fraction of the whole body:
    // a dancer in a wide pose and a dancer with arms down need very different
    // distances for the same "hands" preset.
    const bounds = focus[preset.focus].isEmpty() ? focus.body : focus[preset.focus];
    const size = bounds.getSize(new THREE.Vector3());
    const target = bounds.getCenter(new THREE.Vector3());

    // Frame the body to the panel rather than to a fixed distance: the two stages are
    // very different shapes on phone and desktop, and a preset that crops the feet on
    // one of them is not a preset.
    const cam = camera as THREE.PerspectiveCamera;
    const halfV = THREE.MathUtils.degToRad(cam.fov) / 2;
    const halfH = Math.atan(Math.tan(halfV) * cam.aspect);
    const radius =
      Math.max(size.y / 2 / Math.tan(halfV), Math.max(size.x, size.z) / 2 / Math.tan(halfH)) * 1.18 * preset.distance;

    camera.position.set(
      target.x + Math.sin(preset.azimuth) * Math.cos(preset.elevation) * radius,
      target.y + Math.sin(preset.elevation) * radius,
      target.z + Math.cos(preset.azimuth) * Math.cos(preset.elevation) * radius,
    );
    controls.target.copy(target);
    controls.update();
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
}

export default function Stage3D({ doc, selectedIndex, view, mirrored, timeRef, onAbsent, onResetView, glbUrls }: Stage3DProps) {
  const focusRef = useRef<Focus | null>(null);
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
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#1C1917"]} />
      {/* The far edge of the floor dissolving into the backdrop IS the horizon. */}
      <fog attach="fog" args={["#1C1917", 9, 24]} />
      <Lights grounded={doc.grounding.status === "grounded"} />
      <Floor doc={doc} />
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
      <ViewRig key={`${view}-${selectedIndex}-${resetKey}`} view={view} focusRef={focusRef} controlsRef={controlsRef} />
      {/* Orbit, damped, clamped so the camera never flips over the pole or goes
          under the floor. Pan is off: dragging the stage always orbits, and scrubbing
          only ever happens on the bars (OPEN-DECISIONS C3 — still open, this is the
          lean recorded there). */}
      <OrbitControls
        ref={controlsRef}
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        minPolarAngle={0.12}
        maxPolarAngle={1.52}
        minDistance={0.4}
        maxDistance={9}
      />
    </Canvas>
  );
}
