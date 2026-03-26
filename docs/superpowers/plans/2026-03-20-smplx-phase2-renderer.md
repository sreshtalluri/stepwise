# SMPL-X Phase 2: Mannequin Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a VRM-based mannequin renderer to the frontend that displays a holographic 3D body driven by SMPL-X pose parameters, with an X-ray toggle to switch between mannequin and skeleton views, and a morph transition when SMPL-X data becomes available.

**Architecture:** Use `@pixiv/three-vrm` (MIT) to load a custom VRM mannequin model. The SMPL body_pose axis-angle rotations are converted to quaternions and applied to VRM humanoid bones each frame. A new `MannequinViewer` component sits alongside the existing `SkeletonViewer`. A `PoseViewer` wrapper switches between them based on X-ray toggle state. The viewer page polls for the `skeleton_ready → mannequin_ready` status transition and auto-upgrades.

**Tech Stack:** Next.js 14, Three.js 0.170, @react-three/fiber 8, @pixiv/three-vrm (latest), TypeScript. Worktree at `.claude/worktrees/smplx-mannequin`, branch `feat/smplx-mannequin`.

---

## File Structure

```
frontend/
├── public/
│   └── models/
│       └── mannequin.vrm           # CREATE — custom VRM mannequin model (placeholder initially)
├── components/
│   ├── MannequinViewer.tsx          # CREATE — VRM-based mannequin renderer
│   ├── PoseViewer.tsx               # CREATE — wrapper that switches skeleton ↔ mannequin
│   ├── SkeletonViewer.tsx           # UNCHANGED — kept for X-ray mode
│   ├── ViewLayout.tsx               # MODIFY — use PoseViewer instead of SkeletonViewer
│   └── ViewPresetBar.tsx            # MODIFY — add X-ray toggle button
├── lib/
│   ├── vrm-bone-map.ts             # CREATE — SMPL joint index → VRM bone name mapping
│   ├── rotation-utils.ts           # CREATE — axis-angle → quaternion conversion
│   ├── types.ts                    # ALREADY UPDATED in Phase 1 (SmplxParams, PersonPose, etc.)
│   └── constants.ts                # MODIFY — add mannequin-related constants
├── app/
│   └── viewer/
│       └── [jobId]/
│           └── page.tsx             # MODIFY — add X-ray state, poll for mannequin_ready, auto-upgrade
```

---

### Task 1: Rotation Utilities — Axis-Angle to Quaternion

**Files:**
- Create: `frontend/lib/rotation-utils.ts`

Pure math utility — no dependencies on Three.js or VRM. Converts SMPL axis-angle rotation vectors (3 floats) to quaternions (4 floats) for driving VRM bones.

- [ ] **Step 1: Create rotation-utils.ts**

```typescript
/**
 * Convert axis-angle rotation (3 values) to quaternion (4 values).
 *
 * SMPL body_pose contains 21 joints × 3 axis-angle values = 63 floats.
 * VRM bones expect quaternion rotations. This converts between them.
 *
 * axis-angle: [ax, ay, az] where magnitude = rotation angle in radians,
 * direction = rotation axis.
 */

export function axisAngleToQuaternion(
  ax: number,
  ay: number,
  az: number
): [number, number, number, number] {
  const angle = Math.sqrt(ax * ax + ay * ay + az * az);
  if (angle < 1e-8) {
    return [0, 0, 0, 1]; // identity quaternion
  }
  const halfAngle = angle / 2;
  const s = Math.sin(halfAngle) / angle;
  return [ax * s, ay * s, az * s, Math.cos(halfAngle)]; // [x, y, z, w]
}

/**
 * Extract a single joint's axis-angle rotation from the body_pose array.
 *
 * body_pose is 63 floats: joints 0-20, each with 3 axis-angle values.
 * Joint index i starts at body_pose[i * 3].
 */
export function getJointRotation(
  bodyPose: number[],
  jointIndex: number
): [number, number, number, number] {
  const offset = jointIndex * 3;
  return axisAngleToQuaternion(
    bodyPose[offset],
    bodyPose[offset + 1],
    bodyPose[offset + 2]
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit lib/rotation-utils.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/rotation-utils.ts
git commit -m "feat: add axis-angle to quaternion rotation utilities"
```

---

### Task 2: VRM Bone Mapping — SMPL to VRM Humanoid

**Files:**
- Create: `frontend/lib/vrm-bone-map.ts`

Maps SMPL body_pose joint indices (0-20) to VRM humanoid bone names. VRM uses a standardized bone naming convention. Not all 21 SMPL joints map 1:1 to VRM bones — some need to be skipped or combined.

- [ ] **Step 1: Create vrm-bone-map.ts**

```typescript
/**
 * Maps SMPL body_pose joint indices to VRM humanoid bone names.
 *
 * SMPL body_pose has 21 joints (indices 0-20), excluding the root (pelvis).
 * The root orientation comes from global_orient instead.
 *
 * VRM humanoid bones follow the VRM specification:
 * https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md
 *
 * Joint indices reference the SMPL body model joint ordering.
 * null means the SMPL joint has no direct VRM equivalent.
 */
export const SMPL_TO_VRM_BONE_MAP: Record<number, string | null> = {
  0: "hips",              // SMPL: pelvis (body_pose root, not global_orient)
  1: "leftUpperLeg",      // SMPL: left_hip
  2: "rightUpperLeg",     // SMPL: right_hip
  3: "spine",             // SMPL: spine1
  4: "leftLowerLeg",      // SMPL: left_knee
  5: "rightLowerLeg",     // SMPL: right_knee
  6: "chest",             // SMPL: spine2
  7: "leftFoot",          // SMPL: left_ankle
  8: "rightFoot",         // SMPL: right_ankle
  9: "upperChest",        // SMPL: spine3
  10: "leftToes",         // SMPL: left_foot
  11: "rightToes",        // SMPL: right_foot
  12: "neck",             // SMPL: neck
  13: "leftShoulder",     // SMPL: left_collar
  14: "rightShoulder",    // SMPL: right_collar
  15: "head",             // SMPL: head
  16: "leftUpperArm",     // SMPL: left_shoulder
  17: "rightUpperArm",    // SMPL: right_shoulder
  18: "leftLowerArm",     // SMPL: left_elbow
  19: "rightLowerArm",    // SMPL: right_elbow
  20: null,               // SMPL: left_wrist → VRM leftHand (handled separately via hand_pose)
};

/**
 * VRM bone name for the root (driven by global_orient, not body_pose).
 */
export const VRM_ROOT_BONE = "hips";

/**
 * Hand bone mapping for SMPL-X hand_pose.
 *
 * SMPL-X has 15 joints per hand × 3 axis-angle values = 45 floats per hand.
 * VRM has 15 finger bones per hand (3 per finger × 5 fingers).
 */
export const SMPL_HAND_TO_VRM: Record<number, string> = {
  // Left hand: indices 0-14 in left_hand_pose
  // Index finger
  0: "leftIndexProximal",
  1: "leftIndexIntermediate",
  2: "leftIndexDistal",
  // Middle finger
  3: "leftMiddleProximal",
  4: "leftMiddleIntermediate",
  5: "leftMiddleDistal",
  // Pinky
  6: "leftLittleProximal",
  7: "leftLittleIntermediate",
  8: "leftLittleDistal",
  // Ring finger
  9: "leftRingProximal",
  10: "leftRingIntermediate",
  11: "leftRingDistal",
  // Thumb
  12: "leftThumbMetacarpal",
  13: "leftThumbProximal",
  14: "leftThumbDistal",
};

/**
 * Right hand uses the same indices but with "right" prefix.
 */
export function getRightHandBoneName(leftBoneName: string): string {
  return leftBoneName.replace("left", "right");
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit lib/vrm-bone-map.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/vrm-bone-map.ts
git commit -m "feat: add SMPL to VRM humanoid bone mapping"
```

---

### Task 3: Placeholder VRM Mannequin Model

**Files:**
- Create: `frontend/public/models/mannequin.vrm`

For now, we need a VRM model to develop against. We'll use a freely available minimal VRM mannequin. Later, a custom holographic mannequin can be designed in Blender and exported as VRM.

- [ ] **Step 1: Create models directory and add a placeholder note**

```bash
mkdir -p frontend/public/models
```

Create `frontend/public/models/README.md`:
```markdown
# VRM Mannequin Model

Place `mannequin.vrm` in this directory.

For development, use any VRM model from:
- https://hub.vroid.com/ (free VRM models, check individual licenses)
- https://www.vroid.com/en/studio (create your own with VRoid Studio)

For production, create a custom holographic mannequin in Blender:
- Minimal geometric body (capsule limbs, sphere joints)
- Export as VRM using the VRM Add-on for Blender
- Must include full humanoid bone hierarchy + finger bones

The mannequin.vrm file is not committed to git (too large).
Add to .gitignore if needed.
```

- [ ] **Step 2: Commit**

```bash
git add frontend/public/models/README.md
git commit -m "docs: add VRM mannequin model placeholder and instructions"
```

---

### Task 4: Install @pixiv/three-vrm

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install three-vrm**

```bash
cd frontend && npm install @pixiv/three-vrm
```

- [ ] **Step 2: Verify installation**

```bash
cd frontend && node -e "require('@pixiv/three-vrm'); console.log('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add @pixiv/three-vrm for VRM mannequin rendering"
```

---

### Task 5: MannequinViewer Component

**Files:**
- Create: `frontend/components/MannequinViewer.tsx`

The core mannequin renderer. Loads a VRM model, applies SMPL-X pose params each frame by converting axis-angle rotations to quaternions and setting VRM bone rotations.

- [ ] **Step 1: Create MannequinViewer.tsx**

```typescript
"use client";

import { useRef, useEffect, useState, useMemo } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRM, VRMHumanBoneName } from "@pixiv/three-vrm";
import { PersonPose, CameraAngle } from "@/lib/types";
import { getJointRotation, axisAngleToQuaternion } from "@/lib/rotation-utils";
import { SMPL_TO_VRM_BONE_MAP, SMPL_HAND_TO_VRM, getRightHandBoneName } from "@/lib/vrm-bone-map";

interface MannequinViewerProps {
  personPoses: PersonPose[];
  currentFrame: number;
  angle: CameraAngle;
  focusedPersonId?: number;
  mirror?: boolean;
  opacity?: number;
  groundToFloor?: boolean;
  beatPulse?: boolean;  // true on beat frames for glow effect
}

const CAMERA_POSITIONS: Record<string, [number, number, number]> = {
  front: [0, 1.2, 3],
  back: [0, 1.2, -3],
  mirror: [0, 1.2, 3],
};

function VRMMannequin({
  vrm,
  personPose,
  mirror,
  beatPulse,
}: {
  vrm: VRM;
  personPose: PersonPose | null;
  mirror: boolean;
  beatPulse: boolean;
}) {
  const emissiveRef = useRef(0.15);

  // Apply pose each frame
  useFrame(() => {
    if (!vrm || !personPose) return;

    const { smplx_params } = personPose;

    // Apply global orientation (root rotation)
    const [gx, gy, gz] = smplx_params.global_orient;
    const rootQuat = axisAngleToQuaternion(gx, gy, gz);
    const hipsBone = vrm.humanoid?.getNormalizedBoneNode("hips");
    if (hipsBone) {
      hipsBone.quaternion.set(rootQuat[0], rootQuat[1], rootQuat[2], rootQuat[3]);
      if (mirror) {
        hipsBone.quaternion.x *= -1;
        hipsBone.quaternion.z *= -1;
      }
    }

    // Apply global translation
    const [tx, ty, tz] = smplx_params.transl;
    if (hipsBone) {
      hipsBone.position.set(mirror ? -tx : tx, ty, tz);
    }

    // Apply body pose rotations (21 joints)
    for (let i = 0; i < 21; i++) {
      const vrmBoneName = SMPL_TO_VRM_BONE_MAP[i];
      if (!vrmBoneName) continue;
      const bone = vrm.humanoid?.getNormalizedBoneNode(vrmBoneName as VRMHumanBoneName);
      if (!bone) continue;

      const [qx, qy, qz, qw] = getJointRotation(smplx_params.body_pose, i);
      bone.quaternion.set(qx, qy, qz, qw);

      if (mirror) {
        bone.quaternion.x *= -1;
        bone.quaternion.z *= -1;
      }
    }

    // Apply hand poses
    for (let i = 0; i < 15; i++) {
      const leftBoneName = SMPL_HAND_TO_VRM[i];
      if (!leftBoneName) continue;

      // Left hand
      const leftBone = vrm.humanoid?.getNormalizedBoneNode(leftBoneName as VRMHumanBoneName);
      if (leftBone) {
        const [qx, qy, qz, qw] = getJointRotation(smplx_params.left_hand_pose, i);
        leftBone.quaternion.set(qx, qy, qz, qw);
      }

      // Right hand
      const rightBoneName = getRightHandBoneName(leftBoneName);
      const rightBone = vrm.humanoid?.getNormalizedBoneNode(rightBoneName as VRMHumanBoneName);
      if (rightBone) {
        const [qx, qy, qz, qw] = getJointRotation(smplx_params.right_hand_pose, i);
        rightBone.quaternion.set(qx, qy, qz, qw);
      }
    }

    // Beat pulse: modulate emissive intensity
    const targetEmissive = beatPulse ? 0.4 : 0.15;
    emissiveRef.current += (targetEmissive - emissiveRef.current) * 0.15; // ease-out

    // Update VRM
    vrm.update(0);
  });

  return vrm.scene ? <primitive object={vrm.scene} /> : null;
}

function MannequinScene({
  personPoses,
  currentFrame,
  angle,
  focusedPersonId = 0,
  mirror = false,
  groundToFloor = true,
  beatPulse = false,
}: MannequinViewerProps) {
  const [vrm, setVrm] = useState<VRM | null>(null);
  const { camera } = useThree();

  // Load VRM model
  useEffect(() => {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    loader.load(
      "/models/mannequin.vrm",
      (gltf) => {
        const loadedVrm = gltf.userData.vrm as VRM;
        if (loadedVrm) {
          // Apply holographic material to all meshes
          loadedVrm.scene.traverse((obj) => {
            if (obj instanceof THREE.Mesh && obj.material) {
              obj.material = new THREE.MeshPhysicalMaterial({
                color: new THREE.Color("#0a1a2a"),
                emissive: new THREE.Color("#00d4ff"),
                emissiveIntensity: 0.15,
                transmission: 0.3,
                roughness: 0.4,
                transparent: true,
                opacity: 0.85,
              });
            }
          });
          setVrm(loadedVrm);
        }
      },
      undefined,
      (error) => {
        console.error("Failed to load VRM mannequin:", error);
      }
    );

    return () => {
      if (vrm) vrm.scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry?.dispose();
          if (obj.material) {
            (obj.material as THREE.Material).dispose();
          }
        }
      });
    };
  }, []);

  // Set camera
  useEffect(() => {
    const pos = CAMERA_POSITIONS[angle] || CAMERA_POSITIONS.front;
    camera.position.set(pos[0], pos[1], pos[2]);
    camera.lookAt(0, 1.0, 0);
    camera.updateProjectionMatrix();
  }, [camera, angle]);

  // Get current frame's pose for focused person
  const currentPose = useMemo(() => {
    return personPoses.find(
      (p) => p.person_id === focusedPersonId && p.frame === currentFrame
    ) ?? null;
  }, [personPoses, currentFrame, focusedPersonId]);

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[2, 3, 2]} intensity={0.8} />
      <pointLight position={[-2, 3, -2]} intensity={0.3} />

      {groundToFloor && (
        <gridHelper args={[4, 20, "#222222", "#1a1a1a"]} position={[0, 0, 0]} />
      )}

      {vrm && (
        <VRMMannequin
          vrm={vrm}
          personPose={currentPose}
          mirror={mirror}
          beatPulse={beatPulse}
        />
      )}
    </>
  );
}

export function MannequinViewer(props: MannequinViewerProps) {
  const cameraPos = CAMERA_POSITIONS[props.angle] || CAMERA_POSITIONS.front;

  return (
    <div
      className="w-full h-full r3f-canvas"
      style={props.opacity !== undefined ? { opacity: props.opacity } : undefined}
    >
      <Canvas
        camera={{ position: cameraPos, fov: 50, near: 0.1, far: 100 }}
        gl={{ antialias: true }}
      >
        <color attach="background" args={["#0a0a0a"]} />
        <MannequinScene {...props} />
      </Canvas>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit components/MannequinViewer.tsx`

Note: This may show warnings about the VRM model file not existing — that's expected until we add a real .vrm file.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/MannequinViewer.tsx
git commit -m "feat: add VRM-based MannequinViewer component with holographic material"
```

---

### Task 6: PoseViewer Wrapper — X-Ray Toggle

**Files:**
- Create: `frontend/components/PoseViewer.tsx`

Wrapper component that switches between `SkeletonViewer` (X-ray mode) and `MannequinViewer` (mannequin mode) based on a toggle prop. When mannequin data isn't available yet, always shows skeleton.

- [ ] **Step 1: Create PoseViewer.tsx**

```typescript
"use client";

import { PoseFrame, PersonPose, CameraAngle } from "@/lib/types";
import { SkeletonViewer } from "./SkeletonViewer";
import { MannequinViewer } from "./MannequinViewer";

interface PoseViewerProps {
  // Skeleton data (always available)
  frames: PoseFrame[];
  currentFrame: number;
  angle: CameraAngle;
  showHands: boolean;
  showFeet: boolean;
  mirror?: boolean;
  mirrored?: boolean;
  orbitEnabled?: boolean;
  opacity?: number;
  groundToFloor?: boolean;

  // Mannequin data (available after SMPL-X processing)
  personPoses?: PersonPose[];
  focusedPersonId?: number;
  beatPulse?: boolean;

  // View mode
  xrayMode: boolean;  // true = skeleton, false = mannequin
}

export function PoseViewer({
  frames,
  currentFrame,
  angle,
  showHands,
  showFeet,
  mirror,
  mirrored,
  orbitEnabled,
  opacity,
  groundToFloor,
  personPoses,
  focusedPersonId = 0,
  beatPulse = false,
  xrayMode,
}: PoseViewerProps) {
  // If no mannequin data available, always show skeleton
  const hasMannequinData = personPoses && personPoses.length > 0;
  const showSkeleton = xrayMode || !hasMannequinData;

  if (showSkeleton) {
    return (
      <SkeletonViewer
        frames={frames}
        currentFrame={currentFrame}
        angle={angle}
        showHands={showHands}
        showFeet={showFeet}
        mirror={mirror}
        mirrored={mirrored}
        orbitEnabled={orbitEnabled}
        opacity={opacity}
        groundToFloor={groundToFloor}
      />
    );
  }

  return (
    <MannequinViewer
      personPoses={personPoses!}
      currentFrame={currentFrame}
      angle={angle}
      focusedPersonId={focusedPersonId}
      mirror={mirrored}
      opacity={opacity}
      groundToFloor={groundToFloor}
      beatPulse={beatPulse}
    />
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit components/PoseViewer.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/PoseViewer.tsx
git commit -m "feat: add PoseViewer wrapper with X-ray toggle (skeleton ↔ mannequin)"
```

---

### Task 7: Add X-Ray Toggle to ViewPresetBar

**Files:**
- Modify: `frontend/components/ViewPresetBar.tsx`

Add an X-ray toggle button to the view preset bar, separated from the existing camera/detail buttons by a vertical divider. Styled as a toggle switch matching the existing button pattern.

- [ ] **Step 1: Read current ViewPresetBar.tsx**

Read the file to understand the existing button layout and styling pattern.

- [ ] **Step 2: Add X-ray toggle**

Add an `xrayMode` prop and `onXrayToggle` callback. Add a new button section after the detail layer buttons, separated by a 1px vertical divider:

```typescript
// Add to props interface:
xrayMode?: boolean;
onXrayToggle?: () => void;
hasMannequinData?: boolean;

// Add after the detail layer buttons, before the closing tag:
{hasMannequinData && (
  <>
    <div className="w-px bg-border mx-1 self-stretch" />
    <button
      onClick={onXrayToggle}
      className={`px-3 py-1.5 rounded text-sm transition-all duration-150 ${
        xrayMode
          ? "bg-accent text-bg shadow-[0_0_8px_rgba(0,212,255,0.3)]"
          : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
      title="Toggle X-ray skeleton view (X)"
      role="switch"
      aria-checked={xrayMode}
      aria-label="Toggle X-ray skeleton view"
    >
      X-Ray
    </button>
  </>
)}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit components/ViewPresetBar.tsx`

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ViewPresetBar.tsx
git commit -m "feat: add X-ray toggle button to ViewPresetBar"
```

---

### Task 8: Wire PoseViewer into ViewLayout

**Files:**
- Modify: `frontend/components/ViewLayout.tsx`

Replace `SkeletonViewer` references with `PoseViewer` so every view preset gains mannequin support and X-ray toggle. Pass through the new props.

- [ ] **Step 1: Read current ViewLayout.tsx**

Understand all 8 presets and where SkeletonViewer is used.

- [ ] **Step 2: Update ViewLayout**

1. Import `PoseViewer` instead of (or alongside) `SkeletonViewer`
2. Add `personPoses`, `focusedPersonId`, `xrayMode`, `beatPulse` to the `ViewLayoutProps` interface
3. Replace every `<SkeletonViewer .../>` with `<PoseViewer .../>`, passing through the new props
4. Keep `SkeletonViewer` import — `PoseViewer` uses it internally

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit components/ViewLayout.tsx`

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ViewLayout.tsx
git commit -m "feat: wire PoseViewer into all ViewLayout presets"
```

---

### Task 9: Viewer Page — Progressive Enhancement + X-Ray State

**Files:**
- Modify: `frontend/app/viewer/[jobId]/page.tsx`

Add state management for:
- X-ray mode toggle (keyboard shortcut: `X`)
- Polling for `skeleton_ready` → `mannequin_ready` status transition
- Auto-fetching SMPL-X data when mannequin becomes ready
- Passing new props down to ViewLayout

- [ ] **Step 1: Read current viewer page**

Read the file to understand existing state management and data fetching.

- [ ] **Step 2: Add X-ray state and mannequin data fetching**

Add to the component:

```typescript
// New state
const [xrayMode, setXrayMode] = useState(false);
const [personPoses, setPersonPoses] = useState<PersonPose[]>([]);
const [mannequinReady, setMannequinReady] = useState(false);

// Keyboard shortcut for X-ray toggle
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.key === "x" || e.key === "X") {
      setXrayMode((prev) => !prev);
    }
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}, []);
```

Update the status polling to detect `skeleton_ready` and `mannequin_ready`:

```typescript
// In the polling logic, check for new status values:
if (data.status === "skeleton_ready" || data.status === "mannequin_ready" || data.status === "complete") {
  // Fetch skeleton result if not already loaded
  if (data.skeleton_result_url && !frames.length) {
    // fetch skeleton data (existing logic)
  }

  // Fetch mannequin result when available
  if (data.mannequin_result_url && !mannequinReady) {
    const mannequinRes = await fetch(data.mannequin_result_url);
    const mannequinData = await mannequinRes.json();
    if (mannequinData.person_poses) {
      setPersonPoses(mannequinData.person_poses);
      setMannequinReady(true);
    }
  }
}
```

Pass new props to ViewLayout:

```typescript
<ViewLayout
  // ... existing props
  personPoses={personPoses}
  xrayMode={xrayMode}
  focusedPersonId={0}
/>
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/app/viewer/\\[jobId\\]/page.tsx
git commit -m "feat: add progressive enhancement polling and X-ray toggle to viewer"
```

---

### Task 10: Final Integration Verification

- [ ] **Step 1: Run full TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

Expected: No errors.

- [ ] **Step 2: Run Next.js dev build check**

Run: `cd frontend && npx next build 2>&1 | tail -20`

Expected: Build succeeds (mannequin.vrm won't load at runtime without a real file, but the build should succeed).

- [ ] **Step 3: Commit any fixes**

Only if issues found.

- [ ] **Step 4: Verify all pipeline tests still pass**

Run: `python -m pytest pipeline/tests/ -v --tb=short`

Expected: All 69+ tests PASS.
