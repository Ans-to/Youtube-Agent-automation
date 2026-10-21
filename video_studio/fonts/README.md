# Bundled fonts

These files are shipped so the studio never depends on whatever fonts happen to
be installed on the render machine. They are the only typefaces the motion
system will call professional on its own.

| Family | Weights | Files | Licence |
|---|---|---|---|
| Inter | 400, 500, 600, 700, 800 | `inter-latin-*-normal.woff2` | SIL Open Font License 1.1 |
| Space Grotesk | 400, 500, 600, 700 | `space-grotesk-latin-*-normal.woff2` | SIL Open Font License 1.1 |

Latin subset only. Arabic/Urdu narration still falls back to the platform's
Noto Naskh / Nastaliq / Nirmala faces through the RTL stack in
`motion/typography.py`.

Inter: https://github.com/rsms/inter
Space Grotesk: https://github.com/floriankarsten/space-grotesk

Both are distributed under the SIL Open Font License, which permits bundling
and redistribution with software. The full licence text is available at
https://openfontlicense.org/. If you replace these files, keep the licence
compatible with offline redistribution; the compliance checker rejects stacks
that start with a system default such as Arial.
