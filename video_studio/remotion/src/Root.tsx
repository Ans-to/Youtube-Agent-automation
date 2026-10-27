import React from 'react';
import { Composition } from 'remotion';
import { NokiaEvolution, NOKIA_EVOLUTION_DEFAULT_PROPS } from './nokia/NokiaEvolution';
import { NOKIA_DURATION_FRAMES, NOKIA_FPS, NOKIA_HEIGHT, NOKIA_WIDTH } from './nokia/storyboard';
import { StopCodingBlind } from './StopCodingBlind';
import { DURATION_FRAMES, FPS, HEIGHT, WIDTH } from './timing';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="StopCodingBlind"
      component={StopCodingBlind}
      durationInFrames={DURATION_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
    <Composition
      id="NokiaEvolution"
      component={NokiaEvolution}
      durationInFrames={NOKIA_DURATION_FRAMES}
      fps={NOKIA_FPS}
      width={NOKIA_WIDTH}
      height={NOKIA_HEIGHT}
      defaultProps={NOKIA_EVOLUTION_DEFAULT_PROPS}
    />
  </>
);
