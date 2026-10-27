# Stop coding blind — motion-graphics preview

**Draft preview, not human-approved.** A 10-second portrait Remotion composition with a drawn isometric workspace, a glowing terminal and the exact supplied words. The soundtrack is an original synthesized 120 BPM instrumental, not a user-supplied track. There is no spoken narration or subtitle track.

- [Preview video](stop-coding-blind.mp4)
- [Remotion component and setup](../../../video_studio/remotion/README.md)
- [Technical QA](stop-coding-blind.qc.json)

The first visible frames for “Stop”, “coding”, and “blind.” are 15, 30, and 45 respectively, synchronized to the half-second beat grid. At 30 fps, the encoded file has all 300 frame timestamps at the expected cadence (maximum deviation under one microsecond). The decoded music matched the synthesized PCM at zero sample lag in a two-second correlation check; this is not a substitute for listening.

The delivered MP4 is 1080×1920, H.264, 30 fps, 10.000 s, with stereo 48 kHz AAC. Its encoded soundtrack measured −14.5 LUFS integrated and −5.3 dBTP true peak. Strict technical QA reported no black intervals ≥0.2 s, freezes ≥3 s, silence ≥1.5 s or held-picture spans over 1 s (longest sampled span 0.9 s). These heuristics do not approve the design, motion or audio by themselves.

For an exact 10.000-second container, the Remotion-rendered H.264 stream was copied while the original generated WAV was encoded once to stereo AAC and trimmed to 10 s. The normal `npm run render` command renders directly from the same component and soundtrack; codec/container padding can result in a few extra milliseconds in its audio stream.

Video SHA-256: `90ce1350e23ba12499972b2723396ea8734cacaec0f520017e403b8673d8993a`.
