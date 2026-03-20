"use client";

import { useRef, useEffect, useState, useMemo } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRM, VRMHumanBoneName } from "@pixiv/three-vrm";
import { PersonPose, CameraAngle } from "@/lib/types";
import { getJointRotation, axisAngleToQuaternion } from "@/lib/rotation-utils";
import {
  SMPL_TO_VRM_BONE_MAP,
  SMPL_HAND_TO_VRM,
  getRightHandBoneName,
} from "@/lib/vrm-bone-map";

interface MannequinViewerProps {
  personPoses: PersonPose[];
  currentFrame: number;
  angle: CameraAngle;
  focusedPersonId?: number;
  mirror?: boolean;
  opacity?: number;
  groundToFloor?: boolean;
  beatPulse?: boolean; // true on beat frames for glow effect
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
      hipsBone.quaternion.set(
        rootQuat[0],
        rootQuat[1],
        rootQuat[2],
        rootQuat[3]
      );
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
      const bone = vrm.humanoid?.getNormalizedBoneNode(
        vrmBoneName as VRMHumanBoneName
      );
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
      const leftBone = vrm.humanoid?.getNormalizedBoneNode(
        leftBoneName as VRMHumanBoneName
      );
      if (leftBone) {
        const [qx, qy, qz, qw] = getJointRotation(
          smplx_params.left_hand_pose,
          i
        );
        leftBone.quaternion.set(qx, qy, qz, qw);
      }

      // Right hand
      const rightBoneName = getRightHandBoneName(leftBoneName);
      const rightBone = vrm.humanoid?.getNormalizedBoneNode(
        rightBoneName as VRMHumanBoneName
      );
      if (rightBone) {
        const [qx, qy, qz, qw] = getJointRotation(
          smplx_params.right_hand_pose,
          i
        );
        rightBone.quaternion.set(qx, qy, qz, qw);
      }
    }

    // Beat pulse: modulate emissive intensity
    const targetEmissive = beatPulse ? 0.4 : 0.15;
    emissiveRef.current +=
      (targetEmissive - emissiveRef.current) * 0.15; // ease-out

    // Update emissive intensity on all mesh materials
    vrm.scene.traverse((obj) => {
      if (
        obj instanceof THREE.Mesh &&
        obj.material instanceof THREE.MeshPhysicalMaterial
      ) {
        obj.material.emissiveIntensity = emissiveRef.current;
      }
    });

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
      // Cleanup on unmount
      setVrm((currentVrm) => {
        if (currentVrm) {
          currentVrm.scene.traverse((obj) => {
            if (obj instanceof THREE.Mesh) {
              obj.geometry?.dispose();
              if (obj.material) {
                (obj.material as THREE.Material).dispose();
              }
            }
          });
        }
        return null;
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
    return (
      personPoses.find(
        (p) => p.person_id === focusedPersonId && p.frame === currentFrame
      ) ?? null
    );
  }, [personPoses, currentFrame, focusedPersonId]);

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[2, 3, 2]} intensity={0.8} />
      <pointLight position={[-2, 3, -2]} intensity={0.3} />

      {groundToFloor && (
        <gridHelper
          args={[4, 20, "#222222", "#1a1a1a"]}
          position={[0, 0, 0]}
        />
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
      style={
        props.opacity !== undefined ? { opacity: props.opacity } : undefined
      }
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
