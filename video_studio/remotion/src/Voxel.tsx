import React from 'react';

export type Vec3 = [number, number, number];

/** A crisp, reusable box voxel. Scale changes do not recreate its geometry. */
export const Voxel: React.FC<{
  at: Vec3;
  size: Vec3;
  color: string;
  emissive?: string;
  intensity?: number;
  unlit?: boolean;
}> = ({ at, size, color, emissive, intensity = 1, unlit = false }) => (
  <mesh position={at} scale={size}>
    <boxGeometry args={[1, 1, 1]} />
    {unlit
      ? <meshBasicMaterial color={color} toneMapped={false} />
      : <meshStandardMaterial color={color} emissive={emissive ?? '#000000'} emissiveIntensity={intensity} roughness={.86} metalness={.04} />}
  </mesh>
);
