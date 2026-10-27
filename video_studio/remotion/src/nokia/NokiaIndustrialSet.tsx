import React, { useLayoutEffect } from 'react';
import { useThree } from '@react-three/fiber';
import { ThreeCanvas } from '@remotion/three';
import { spring } from 'remotion';
import { OrthographicCamera, Quaternion, Vector3 } from 'three';

const IndustrialBlock: React.FC<{
  frame: number;
  arrivalFrame: number;
  position: [number, number, number];
  size: [number, number, number];
  color: string;
  accent: string;
}> = ({ frame, arrivalFrame, position, size, color, accent }) => {
  const impact = frame < arrivalFrame ? 0 : spring({ frame: frame - arrivalFrame + 1, fps: 30,
    config: { damping: 12, stiffness: 115, mass: 0.8 } });
  const height = Math.max(0.01, impact);
  return (
    <group position={[position[0], position[1] - (1 - impact) * 0.65, position[2]]} scale={[1, height, 1]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={size} />
        <meshStandardMaterial color={color} roughness={0.72} metalness={0.13} />
      </mesh>
      <mesh position={[0, size[1] / 2 + 0.008, 0]}>
        <boxGeometry args={[size[0] * 0.82, 0.018, size[2] * 0.82]} />
        <meshBasicMaterial color={accent} transparent opacity={0.82} />
      </mesh>
    </group>
  );
};

const Conduit: React.FC<{ from: Vector3; to: Vector3; color: string; opacity: number }> = ({ from, to, color, opacity }) => {
  const delta = new Vector3().subVectors(to, from);
  const center = new Vector3().addVectors(from, to).multiplyScalar(0.5);
  const quaternion = new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), delta.clone().normalize());
  return (
    <mesh position={center} quaternion={quaternion}>
      <cylinderGeometry args={[0.025, 0.025, delta.length(), 8]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} />
    </mesh>
  );
};

const IsometricCamera: React.FC = () => {
  const camera = useThree((state) => state.camera);
  useLayoutEffect(() => {
    const orthographic = camera as OrthographicCamera;
    orthographic.position.set(8, 9, 9);
    orthographic.lookAt(0, 0.8, 0);
    orthographic.zoom = 178;
    orthographic.updateProjectionMatrix();
  }, [camera]);
  return null;
};

const NokiaIndustrialWorld: React.FC<{ frame: number }> = ({ frame }) => {
  const pulse = 0.52 + 0.38 * ((Math.sin(frame / 12) + 1) / 2);
  const nodes: [Vector3, Vector3, Vector3, Vector3] = [
    new Vector3(-2.55, 0.45, 0.8), new Vector3(-0.85, 0.82, 0.25),
    new Vector3(0.95, 1.12, -0.25), new Vector3(2.65, 1.45, -0.8),
  ];
  return (
    <>
      <IsometricCamera />
      <ambientLight intensity={1.6} color="#bfccdc" />
      <directionalLight position={[-4, 8, 6]} intensity={2.0} color="#f8d1a1" />
      <pointLight position={[-2.5, 3.8, 1.8]} color="#f3ad5a" intensity={5.2} distance={10} />
      <pointLight position={[2.5, 2.4, -1.6]} color="#48d9d7" intensity={2.0 + pulse} distance={8} />
      <gridHelper args={[10, 20, '#53758c', '#263a4c']} position={[0, 0.01, 0]} />

      {nodes.map((node, index) => (
        <IndustrialBlock key={index} frame={frame} arrivalFrame={246 + index * 13}
          position={[node.x, node.y, node.z]}
          size={[1.05, 0.72 + index * 0.12, 1.0]}
          color={['#596879', '#705344', '#79503c', '#655341'][index]}
          accent={index % 2 ? '#e74c3c' : '#e7ad60'} />
      ))}
      {nodes.slice(0, -1).map((node, index) => (
        <React.Fragment key={`conduit-${index}`}>
          <Conduit from={node} to={nodes[index + 1]} color="#55e0dc" opacity={pulse} />
          <Conduit from={new Vector3(node.x, node.y + 0.08, node.z + 0.11)}
            to={new Vector3(nodes[index + 1].x, nodes[index + 1].y + 0.08, nodes[index + 1].z + 0.11)}
            color="#e74c3c" opacity={0.78 - pulse * 0.28} />
        </React.Fragment>
      ))}

      {/* Cable reels emerge beside the rising industrial blocks. */}
      {[0, 1, 2].map((index) => {
        const arrival = 280 + index * 17;
        const rise = frame < arrival ? 0 : spring({ frame: frame - arrival + 1, fps: 30,
          config: { damping: 13, stiffness: 105, mass: 0.9 } });
        return <group key={`reel-${index}`} position={[-1.35 + index * 1.28, 1.45 + rise * 0.04, -1.55]} rotation={[Math.PI / 2, 0, 0]} scale={0.72 + rise * 0.28}>
          <mesh>
            <torusGeometry args={[0.31, 0.065, 10, 32]} />
            <meshStandardMaterial color={index === 1 ? '#e74c3c' : '#d5a15f'} metalness={0.62} roughness={0.32} />
          </mesh>
          <mesh>
            <cylinderGeometry args={[0.13, 0.13, 0.24, 20]} />
            <meshStandardMaterial color="#9aa7b6" metalness={0.55} roughness={0.4} />
          </mesh>
        </group>;
      })}
    </>
  );
};

/** A real Three.js orthographic isometric industrial layer, alpha-composited over the SVG grid. */
export const NokiaIndustrialSet: React.FC<{ frame: number }> = ({ frame }) => (
  <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
    <ThreeCanvas width={1080} height={1920} orthographic
      camera={{ position: [8, 9, 9], zoom: 178, near: 0.1, far: 100 }}
      gl={{ antialias: true, alpha: true }}>
      <NokiaIndustrialWorld frame={frame} />
    </ThreeCanvas>
  </div>
);
