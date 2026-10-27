import React, { useLayoutEffect } from 'react';
import { useThree } from '@react-three/fiber';
import { OrthographicCamera } from 'three';
import { cameraPose } from './camera';
import { VectorAvatar } from './VectorAvatar';
import { Voxel } from './Voxel';
import { terminalLineState } from './terminalMotion';
import { BPM } from './timing';

const CameraRig: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const camera = useThree((state) => state.camera);
  const pose = cameraPose(frame, fps);
  useLayoutEffect(() => {
    const ortho = camera as OrthographicCamera;
    ortho.position.set(...pose.position);
    ortho.lookAt(...pose.target);
    ortho.zoom = pose.zoom;
    ortho.updateProjectionMatrix();
  }, [camera, frame, fps, pose.position, pose.target, pose.zoom]);
  return null;
};

/** A desk, monitor, keyboard and room made from actual Three.js box geometry. */
export const VoxelWorkspace: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const beat = frame * BPM / (fps * 60);
  const phase = beat - Math.floor(beat);
  const pulse = Math.pow(1 - phase, 3);
  const activeRow = Math.floor(beat) % 6;
  const rows = [1.04, .72, 1.15, .89, .65, 1.00];

  const floorTiles = [];
  for (let x = 0; x < 10; x++) {
    for (let z = 0; z < 7; z++) {
      const checker = (x + z) % 2 === 0;
      floorTiles.push(<Voxel key={`${x}-${z}`} at={[-2.33 + x * .52, .045, -1.62 + z * .52]}
        size={[.48, .06, .48]} color={checker ? '#30333f' : '#272a36'} />);
    }
  }

  const keys = [];
  for (let x = 0; x < 4; x++) {
    for (let z = 0; z < 7; z++) {
      keys.push(<Voxel key={`${x}-${z}`} at={[.70 + x * .115, 1.34, .05 + z * .16]}
        size={[.082, .035, .112]} color={z === 2 && x === 2 ? '#fb5963' : '#8c96a0'} />);
    }
  }

  return (
    <>
      <CameraRig frame={frame} fps={fps} />
      <ambientLight intensity={1.25} color="#d8e2f7" />
      <directionalLight position={[-4, 8, 6]} intensity={2.1} color="#f5d4c9" />
      <pointLight position={[-.4, 2.1, .15]} color="#ff3a52" intensity={3.2 + pulse * 1.1} distance={5} />
      <pointLight position={[.5, 1.8, .45]} color="#38e6ed" intensity={2.2} distance={4.5} />
      <pointLight position={[-1.65, 2.7, -.45]} color="#ff9b65" intensity={2.4} distance={4} />

      {/* Floating tiled floor, a warm rim and a pixelated back wall. */}
      <Voxel at={[0, -.12, 0]} size={[5.35, .25, 4.0]} color="#25212c" />
      <Voxel at={[0, -.18, 1.99]} size={[5.34, .11, .06]} color="#b93e4e" />
      <Voxel at={[-2.65, -.18, 0]} size={[.07, .11, 3.96]} color="#5fe8e3" />
      {floorTiles}
      <Voxel at={[0, 1.47, -1.95]} size={[5.35, 2.96, .18]} color="#252d38" />
      <Voxel at={[0, 2.98, -1.95]} size={[5.38, .10, .22]} color="#667078" />
      <Voxel at={[-2.60, 1.48, -1.84]} size={[.12, 2.90, .09]} color="#566270" />
      <Voxel at={[2.60, 1.48, -1.84]} size={[.12, 2.90, .09]} color="#566270" />
      {/* Voxel window and small wall pixels make the room feel inhabited. */}
      <Voxel at={[-1.74, 2.09, -1.83]} size={[1.15, 1.05, .07]} color="#111b29" />
      <Voxel at={[-1.74, 2.09, -1.78]} size={[.96, .86, .04]} color="#204053" />
      <Voxel at={[-1.74, 2.09, -1.75]} size={[.055, .86, .035]} color="#81b2bb" />
      <Voxel at={[-1.74, 2.09, -1.74]} size={[.96, .055, .035]} color="#81b2bb" />
      <Voxel at={[1.35, 2.42, -1.81]} size={[.50, .14, .04]} color="#fd4f5d" unlit />
      <Voxel at={[1.75, 2.42, -1.81]} size={[.16, .14, .04]} color="#67e7e3" unlit />
      <Voxel at={[1.35, 2.18, -1.81]} size={[.80, .07, .04]} color="#687a86" />
      <Voxel at={[1.19, 2.02, -1.81]} size={[.48, .07, .04]} color="#687a86" />

      {/* Desk top and legs. */}
      <Voxel at={[-.22, 1.18, -.27]} size={[3.32, .18, 2.55]} color="#856b67" />
      <Voxel at={[-.22, 1.26, -.27]} size={[3.32, .045, 2.55]} color="#b39282" />
      <Voxel at={[-1.65, .58, -1.23]} size={[.20, 1.12, .20]} color="#62616d" />
      <Voxel at={[1.18, .58, -1.23]} size={[.20, 1.12, .20]} color="#62616d" />
      <Voxel at={[-1.65, .58, .71]} size={[.20, 1.12, .20]} color="#62616d" />
      <Voxel at={[1.18, .58, .71]} size={[.20, 1.12, .20]} color="#62616d" />
      <Voxel at={[-.25, .70, -.94]} size={[2.7, .08, .10]} color="#55515c" />

      {/* Screen housing, stand and a set of typed code-shaped strokes. */}
      <Voxel at={[-.50, 1.38, -.76]} size={[.62, .08, .35]} color="#59616c" />
      <Voxel at={[-.50, 1.55, -.82]} size={[.14, .35, .13]} color="#7b838a" />
      <Voxel at={[-.50, 2.10, -.83]} size={[1.92, 1.30, .20]} color="#4b5661" />
      <Voxel at={[-.50, 2.10, -.715]} size={[1.76, 1.14, .035]} color="#0a1720" unlit />
      <Voxel at={[-.50, 2.58, -.69]} size={[1.76, .10, .025]} color="#32414d" unlit />
      {[-1.24, -1.12, -1.00].map((x, i) => (
        <Voxel key={x} at={[x, 2.58, -.67]} size={[.07, .07, .025]} color={i === 0 ? '#ff5161' : '#6d7e88'} unlit />
      ))}
      {/* Red frame plus a cyan edge are the screen's neon emissive pixels. */}
      <Voxel at={[-.50, 1.49, -.69]} size={[1.94, .045, .035]} color="#ff5261" unlit />
      <Voxel at={[-1.46, 2.10, -.69]} size={[.045, 1.26, .035]} color="#ff5261" unlit />
      <Voxel at={[.46, 2.10, -.69]} size={[.045, 1.26, .035]} color="#64eeec" unlit />
      {rows.map((width, index) => {
        const { progress, active } = terminalLineState(frame, index, fps);
        const indent = index === 1 || index === 2 || index === 3 ? .15 : 0;
        const actualWidth = Math.max(.001, width * progress);
        const left = -1.25 + indent;
        const y = 2.43 - index * .145;
        return (
          <group key={index}>
            <Voxel at={[left - .06, y, -.672]} size={[.055, .035, .025]} color="#bf6875" unlit />
            <Voxel at={[left + actualWidth / 2, y, -.671]} size={[actualWidth, .035, .025]}
              color={active || index === activeRow ? '#ff6571' : index % 3 === 1 ? '#6ce8e7' : '#d8e6e5'} unlit />
          </group>
        );
      })}
      <Voxel at={[-1.19 + (Math.sin(beat * Math.PI) * .5 + .5) * .75, 1.63, -.66]}
        size={[.055, .08, .025]} color="#ff5262" unlit />

      {/* Keyboard and individually modeled keys stay in the isometric workspace. */}
      <Voxel at={[.87, 1.30, .53]} size={[.58, .06, 1.23]} color="#373e48" />
      {keys}

      {/* Warm task lamp and blocky plant. */}
      <Voxel at={[-1.47, 1.30, .38]} size={[.34, .08, .32]} color="#484c57" />
      <Voxel at={[-1.47, 1.69, .38]} size={[.09, .77, .09]} color="#7e8085" />
      <Voxel at={[-1.35, 2.06, .38]} size={[.31, .16, .24]} color="#e37c60" />
      <Voxel at={[-1.35, 1.96, .38]} size={[.23, .06, .17]} color="#ffd18c" unlit />
      <Voxel at={[-1.37, 1.38, -1.16]} size={[.30, .26, .30]} color="#ad6c59" />
      <Voxel at={[-1.37, 1.62, -1.16]} size={[.12, .32, .12]} color="#5f9a7c" />
      <Voxel at={[-1.50, 1.72, -1.16]} size={[.18, .14, .17]} color="#80bc93" />
      <Voxel at={[-1.24, 1.76, -1.16]} size={[.18, .14, .17]} color="#6bae86" />

      <VectorAvatar frame={frame} fps={fps} />
    </>
  );
};
