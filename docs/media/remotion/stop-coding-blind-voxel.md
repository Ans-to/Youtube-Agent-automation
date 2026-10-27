# Stop coding blind — Skill.md voxel remake

**Draft preview, not human-approved.** This remake follows the [specified Skill.md](../../../Skill.md), copied unchanged from main at commit [`26fbc5a`](https://github.com/Ans-to/Youtube-Agent-automation/blob/26fbc5a84d4ea7d093425da165a03715f00fe997/Skill.md). The isometric workspace and typing robot are rendered as 3D voxels with React Three Fiber; the camera moves, text springs in on the beat, and RGB/pixel glitches and CRT scanlines are procedural overlays. No photographs or AI-generated backplates are used.

- [Preview video](stop-coding-blind-voxel.mp4)
- [Component and setup](../../../video_studio/remotion/README.md)
- [Technical QA report](stop-coding-blind-voxel.qc.json)

The included track is the original procedurally synthesized 120 BPM instrumental; no track or voiceover was supplied. “Stop”, “coding” and “blind.” first appear on frames 15, 30 and 45 (0.5, 1.0 and 1.5 seconds). Decoded music matched the source PCM at zero-sample lag in a two-second correlation check. The encoded video has 300 frames, with timestamp error below one microsecond from the 30 fps grid. A downscaled luma comparison found no exactly identical adjacent frames; it is not a substitute for a human assessment of meaningful motion.

The delivered H.264/AAC MP4 is 1080×1920, 30 fps and 10.000 seconds. Audio measured −14.5 LUFS integrated and −5.3 dBTP. The automated strict black, freeze, silence and sampled held-picture checks passed. These heuristics do not assess the design, timing by ear or artistic quality.

The original 2D preview remains [here](stop-coding-blind.md). The included video was made by copying the Remotion-rendered H.264 stream and encoding the original WAV to stereo AAC with a 10-second playback duration; the optional FFmpeg command is in the setup guide. Remotion's direct MP4 output may include a few milliseconds of AAC/container padding even though its 300-frame picture is exactly ten seconds.

Video SHA-256: `de65a1249424b0af5624562c2c686fc2272c21f3870c60dc2b65700cdb1eccee`.
