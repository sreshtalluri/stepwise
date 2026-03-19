"use client";

import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import {
  PoseFrame,
  CameraAngle,
  DetailLayer,
  JointName,
  HandState,
  FootState,
} from "@/lib/types";
import { BONE_CONNECTIONS, FOOT_COLORS } from "@/lib/constants";

interface SkeletonViewerProps {
  frames: PoseFrame[];
  currentFrame: number;
  angle: CameraAngle;
  showHands: boolean;
  showFeet: boolean;
  mirror?: boolean;
  mirrored?: boolean;
  orbitEnabled?: boolean;
  opacity?: number;
}

// Camera positions for different angles
const CAMERA_POSITIONS: Record<string, [number, number, number]> = {
  front: [0, 1.2, 3],
  back: [0, 1.2, -3],
  mirror: [0, 1.2, 3],
};

function Skeleton({
  frame,
  mirror,
  showHands,
  showFeet,
}: {
  frame: PoseFrame;
  mirror: boolean;
  showHands: boolean;
  showFeet: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  const jointPositions = useMemo(() => {
    const positions: Record<string, THREE.Vector3> = {};
    for (const [name, joint] of Object.entries(frame.joints)) {
      const x = mirror ? -joint.x : joint.x;
      positions[name] = new THREE.Vector3(x, joint.y, joint.z);
    }
    return positions;
  }, [frame, mirror]);

  // Build bone geometry
  const boneLines = useMemo(() => {
    const points: THREE.Vector3[] = [];
    for (const [a, b] of BONE_CONNECTIONS) {
      const posA = jointPositions[a];
      const posB = jointPositions[b];
      if (posA && posB) {
        points.push(posA.clone(), posB.clone());
      }
    }
    return points;
  }, [jointPositions]);

  return (
    <group ref={groupRef}>
      {/* Bones as line segments */}
      {BONE_CONNECTIONS.map(([a, b], i) => {
        const posA = jointPositions[a];
        const posB = jointPositions[b];
        if (!posA || !posB) return null;
        return <BoneLine key={i} start={posA} end={posB} />;
      })}

      {/* Joint spheres */}
      {Object.entries(jointPositions).map(([name, pos]) => (
        <mesh key={name} position={pos}>
          <sphereGeometry args={[0.015, 8, 8]} />
          <meshStandardMaterial
            color="#00d4ff"
            emissive="#00d4ff"
            emissiveIntensity={0.5}
          />
        </mesh>
      ))}

      {/* Hand indicators */}
      {showHands &&
        frame.hands?.map((hand, i) => {
          const pos = jointPositions[hand.joint];
          if (!pos) return null;
          return (
            <HandIndicator key={i} position={pos} state={hand.state} />
          );
        })}

      {/* Foot indicators */}
      {showFeet &&
        frame.feet?.map((foot, i) => {
          const pos = jointPositions[foot.joint];
          if (!pos) return null;
          if (foot.state === "airborne") return null;
          return (
            <FootIndicator key={i} position={pos} state={foot.state} />
          );
        })}
    </group>
  );
}

function BoneLine({
  start,
  end,
}: {
  start: THREE.Vector3;
  end: THREE.Vector3;
}) {
  const ref = useRef<THREE.BufferGeometry>(null);

  useMemo(() => {
    if (ref.current) {
      ref.current.setFromPoints([start, end]);
    }
  }, [start, end]);

  return (
    <line>
      <bufferGeometry ref={ref}>
        <bufferAttribute
          attach="attributes-position"
          args={[
            new Float32Array([
              start.x, start.y, start.z,
              end.x, end.y, end.z,
            ]),
            3,
          ]}
        />
      </bufferGeometry>
      <lineBasicMaterial color="#00d4ff" linewidth={2} transparent opacity={0.8} />
    </line>
  );
}

function HandIndicator({
  position,
  state,
}: {
  position: THREE.Vector3;
  state: HandState;
}) {
  switch (state) {
    case "fist":
      return (
        <mesh position={position}>
          <sphereGeometry args={[0.03, 8, 8]} />
          <meshStandardMaterial
            color="#00d4ff"
            emissive="#00d4ff"
            emissiveIntensity={0.8}
          />
        </mesh>
      );
    case "open":
      return (
        <mesh position={position} rotation={[Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.04, 16]} />
          <meshStandardMaterial
            color="#00d4ff"
            emissive="#00d4ff"
            emissiveIntensity={0.8}
            side={THREE.DoubleSide}
          />
        </mesh>
      );
    case "spread":
      return (
        <group position={position}>
          {[0, 1, 2, 3, 4].map((i) => {
            const angle = (i / 5) * Math.PI * 2;
            return (
              <mesh
                key={i}
                position={[
                  Math.cos(angle) * 0.03,
                  Math.sin(angle) * 0.03,
                  0,
                ]}
              >
                <sphereGeometry args={[0.01, 6, 6]} />
                <meshStandardMaterial
                  color="#00d4ff"
                  emissive="#00d4ff"
                  emissiveIntensity={0.8}
                />
              </mesh>
            );
          })}
        </group>
      );
    case "pointing":
      return (
        <mesh position={position} rotation={[0, 0, Math.PI / 2]}>
          <coneGeometry args={[0.02, 0.06, 8]} />
          <meshStandardMaterial
            color="#00d4ff"
            emissive="#00d4ff"
            emissiveIntensity={0.8}
          />
        </mesh>
      );
  }
}

function FootIndicator({
  position,
  state,
}: {
  position: THREE.Vector3;
  state: FootState;
}) {
  const color = FOOT_COLORS[state] || "#ffffff";
  return (
    <mesh position={position}>
      <sphereGeometry args={[0.025, 8, 8]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={0.6}
      />
    </mesh>
  );
}

function Scene({
  frames,
  currentFrame,
  angle,
  showHands,
  showFeet,
  mirrored,
  orbitEnabled,
}: SkeletonViewerProps) {
  const frame = frames[currentFrame] || frames[0];
  if (!frame) return null;

  const isMirror = mirrored !== undefined ? mirrored : angle === "mirror";
  const cameraPos = CAMERA_POSITIONS[angle] || CAMERA_POSITIONS.front;
  const orbitIsEnabled = orbitEnabled !== undefined ? orbitEnabled : true;

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[2, 3, 2]} intensity={0.8} />
      <pointLight position={[-2, 3, -2]} intensity={0.3} />

      {/* Ground grid */}
      <gridHelper
        args={[4, 20, "#222222", "#1a1a1a"]}
        position={[0, 0, 0]}
      />

      <Skeleton
        frame={frame}
        mirror={isMirror}
        showHands={showHands}
        showFeet={showFeet}
      />

      <OrbitControls
        target={[0, 1.0, 0]}
        enablePan={false}
        minDistance={1.5}
        maxDistance={6}
        enabled={orbitIsEnabled}
      />
    </>
  );
}

export function SkeletonViewer(props: SkeletonViewerProps) {
  const cameraPos = CAMERA_POSITIONS[props.angle] || CAMERA_POSITIONS.front;

  return (
    <div
      className="w-full h-full r3f-canvas"
      style={props.opacity !== undefined ? { opacity: props.opacity } : undefined}
    >
      <Canvas
        camera={{
          position: cameraPos,
          fov: 50,
          near: 0.1,
          far: 100,
        }}
        gl={{ antialias: true }}
      >
        <color attach="background" args={["#0a0a0a"]} />
        <Scene {...props} />
      </Canvas>
    </div>
  );
}
