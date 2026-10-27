/** The requested wording and its 120 BPM entrance cues are the storyboard. */
export const WORDS = [
  { text: 'Stop', beat: 1, accent: false },
  { text: 'coding', beat: 2, accent: false },
  { text: 'blind.', beat: 3, accent: true },
] as const;

// Word impacts followed by one-second rhythmic accent bursts.
export const GLITCH_BEATS = [1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18] as const;
