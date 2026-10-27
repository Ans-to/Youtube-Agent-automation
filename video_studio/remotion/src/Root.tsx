import React from 'react';
import { Composition } from 'remotion';
import { StopCodingBlind } from './StopCodingBlind';
import { DURATION_FRAMES, FPS, HEIGHT, WIDTH } from './timing';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="StopCodingBlind"
    component={StopCodingBlind}
    durationInFrames={DURATION_FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);
