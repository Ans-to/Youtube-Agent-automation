import React from 'react';
import { Voxel } from './Voxel';
import { avatarMotion } from './avatarMotion';

/** A voxel robot stands at the keyboard and alternates its hands as it types. */
export const PixelAvatar: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const { beat, bob, typing, blink } = avatarMotion(frame, fps);

  const arm = (side: -1 | 1) => (
    <group position={[side * .43, 1.48, .07]} rotation={[side * typing * .10, 0, 0]}>
      <Voxel at={[0, -.12, .02]} size={[.21, .34, .23]} color="#707c8d" />
      <Voxel at={[0, -.30, .24]} size={[.17, .15, .44]} color="#a5adba" />
      <Voxel at={[0, -.33 + side * typing * .06, .49]} size={[.21, .11, .18]} color="#e3d8cb" />
      <Voxel at={[0, -.35 + side * typing * .06, .58]} size={[.13, .055, .08]} color="#ff5a66" unlit />
    </group>
  );

  return (
    <group position={[1.66, 0, .68]} rotation={[0, -Math.PI / 2, 0]}>
      {/* Feet and legs */}
      <Voxel at={[-.22, .13, .08]} size={[.28, .23, .42]} color="#414b5b" />
      <Voxel at={[.22, .13, .08]} size={[.28, .23, .42]} color="#414b5b" />
      <Voxel at={[-.22, .48, 0]} size={[.24, .55, .25]} color="#77818f" />
      <Voxel at={[.22, .48, 0]} size={[.24, .55, .25]} color="#77818f" />
      {/* Torso, scarf and small status light */}
      <group position={[0, bob, 0]}>
        <Voxel at={[0, 1.02, 0]} size={[.75, .70, .48]} color="#9da6ae" />
        <Voxel at={[0, 1.10, .251]} size={[.52, .39, .035]} color="#354354" />
        <Voxel at={[0, 1.33, .27]} size={[.76, .15, .09]} color="#ee4959" />
        <Voxel at={[.24, 1.20, .29]} size={[.17, .29, .08]} color="#d73149" />
        <Voxel at={[-.13, 1.11, .279]} size={[.09, .09, .025]} color="#70fff2" unlit />
        {arm(-1)}
        {arm(1)}
        {/* The face turns toward the desk, so the eyes stay on the terminal. */}
        <group position={[0, 1.73, 0]} rotation={[.025 * Math.sin(beat * Math.PI), 0, .045 * Math.sin(beat * Math.PI / 2)]}>
          <Voxel at={[0, 0, 0]} size={[.86, .72, .70]} color="#b7c0c6" />
          <Voxel at={[0, -.035, .36]} size={[.70, .42, .035]} color="#15232e" />
          <Voxel at={[-.20, .005, .383]} size={[.13, blink ? .035 : .13, .02]} color="#69fff5" unlit />
          <Voxel at={[.20, .005, .383]} size={[.13, blink ? .035 : .13, .02]} color="#69fff5" unlit />
          <Voxel at={[0, -.17, .383]} size={[.18, .035, .02]} color="#5aa6aa" unlit />
          <Voxel at={[0, .40, 0]} size={[.13, .17, .13]} color="#85929b" />
          <Voxel at={[0, .51, 0]} size={[.16, .12, .16]} color="#ff5263" unlit />
          <Voxel at={[-.48, -.01, 0]} size={[.13, .30, .30]} color="#667480" />
          <Voxel at={[.48, -.01, 0]} size={[.13, .30, .30]} color="#667480" />
        </group>
      </group>
    </group>
  );
};
