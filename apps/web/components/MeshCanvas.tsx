'use client';

import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { Float32BufferAttribute, BufferGeometry, Color } from 'three';
import { useMemo } from 'react';
import { applyLinearBlendSkinning, jointMatricesForPose, type MeshResult, type Person, type PersonFrame } from '@/lib/client-model';

function Surface({ person, frame, mirror, xray }: { person: Person; frame?: PersonFrame; mirror: boolean; xray: boolean }) {
  const mesh = person.mesh_asset;
  const geometry = useMemo(() => {
    if (!mesh) return null;
    const matrices = jointMatricesForPose(frame, mesh.joint_hierarchy, mesh.inverse_bind_matrices, mirror);
    const skinned = applyLinearBlendSkinning(mesh.vertices, mesh.skin_weights, matrices);
    const geom = new BufferGeometry();
    geom.setAttribute('position', new Float32BufferAttribute(skinned.flat(), 3));
    geom.setIndex(mesh.faces.flat());
    geom.computeVertexNormals();
    return geom;
  }, [frame, mesh, mirror]);

  if (!mesh || !geometry) return null;
  const color = new Color(person.color);
  const joints = frame?.joints_3d ?? [];

  return (
    <group position={[0, -0.9, 0]}>
      <mesh geometry={geometry}>
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.23} roughness={0.42} metalness={0.18} transparent opacity={0.72} wireframe={xray} />
      </mesh>
      {xray && joints.map((joint) => (
        <mesh key={`${person.track_id}-${joint.name}`} position={[mirror ? -joint.position[0] : joint.position[0], joint.position[1] - 0.9, joint.position[2]]}>
          <sphereGeometry args={[0.018, 8, 8]} />
          <meshBasicMaterial color="#f0f0f0" />
        </mesh>
      ))}
    </group>
  );
}

export default function MeshCanvas({ result, people, frameIndex, mirror, xray, orbit }: { result: MeshResult; people: Person[]; frameIndex: number; mirror: boolean; xray: boolean; orbit: boolean }) {
  const frame = result.frames[frameIndex % result.frames.length];
  return (
    <Canvas camera={{ position: [0, 1.15, 3.15], fov: 42 }} dpr={[1, 1.8]}>
      <color attach="background" args={["#050505"]} />
      <ambientLight intensity={0.7} />
      <pointLight position={[2, 4, 2]} intensity={45} color="#00d4ff" />
      <gridHelper args={[4, 16, '#00d4ff', '#202020']} position={[0, -0.92, 0]} />
      {people.map((person) => <Surface key={person.track_id} person={person} frame={frame.people.find((pose) => pose.track_id === person.track_id)} mirror={mirror} xray={xray} />)}
      {orbit && <OrbitControls enablePan={false} maxDistance={5} minDistance={1.7} />}
    </Canvas>
  );
}
