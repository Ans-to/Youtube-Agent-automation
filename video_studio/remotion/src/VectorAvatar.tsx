import React, { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { DoubleSide, Group, MeshBasicMaterial, ShapeGeometry } from 'three';
import { SVGLoader } from 'three/addons/loaders/SVGLoader.js';
import { avatarMotion } from './avatarMotion';

const DETECTIVE_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="500" viewBox="0 0 320 500">
  <!-- Rear shoulder silhouette and trench coat -->
  <path id="coat-shadow" fill="#080d16" d="M106 218 Q81 221 70 250 L45 338 Q43 350 55 356 L77 367 Q88 372 94 359 L111 312 L105 478 Q160 494 215 478 L209 312 L226 359 Q232 372 243 367 L265 356 Q277 350 275 338 L250 250 Q239 221 214 218 L196 204 L124 204Z"/>
  <path id="coat" fill="#202a38" d="M112 222 Q88 225 79 254 L56 338 L76 348 L105 286 L101 464 Q160 481 219 464 L215 286 L244 348 L264 338 L241 254 Q232 225 208 222 L191 209 L129 209Z"/>
  <path id="coat-shadow-panel" fill="#141c28" d="M108 263 L126 229 L151 251 L139 458 L106 451Z M212 263 L194 229 L169 251 L181 458 L214 451Z"/>
  <path id="shirt" fill="#d9d5ca" d="M128 207 L160 230 L192 207 L205 289 L181 320 L139 320 L115 289Z"/>
  <path id="vest" fill="#303b49" d="M133 231 L160 253 L187 231 L178 443 L142 443Z"/>
  <path id="left-lapel" fill="#465364" d="M126 208 L158 229 L139 274 L113 241Z"/>
  <path id="right-lapel" fill="#394657" d="M194 208 L162 229 L181 274 L207 241Z"/>
  <path id="lapel-highlight" fill="#83909a" d="M126 216 L151 232 L138 244 L119 236Z M194 216 L169 232 L182 244 L201 236Z"/>
  <path id="tie" fill="#d84952" d="M153 245 L160 251 L167 245 L171 270 L160 286 L149 270Z M160 286 L171 270 L179 410 L160 423 L141 410 L149 270Z"/>
  <path id="tie-shadow" fill="#a92f3b" d="M160 286 L171 270 L179 410 L160 423Z"/>
  <path id="coat-belt" fill="#111924" d="M105 402 Q160 414 215 402 L215 423 Q160 438 105 423Z"/>
  <path id="buckle" fill="#c2a779" d="M151 407 L169 407 L169 425 L151 425Z M155 411 L165 411 L165 421 L155 421Z"/>
  <path id="left-pocket" fill="#394657" d="M111 329 L137 333 L134 367 L108 364Z"/>
  <path id="right-pocket" fill="#394657" d="M183 333 L209 329 L212 364 L186 367Z"/>
  <path id="left-pocket-flap" fill="#576371" d="M108 329 L139 333 L135 343 L109 340Z"/>
  <path id="right-pocket-flap" fill="#576371" d="M181 333 L212 329 L211 340 L185 343Z"/>

  <!-- Extended sleeves and hands, subtly animated on the beat -->
  <path id="arm-left" fill="#273444" d="M102 230 Q83 235 77 258 L54 329 Q50 340 62 346 L76 351 Q86 355 91 342 L119 278 L133 253Z"/>
  <path id="arm-right" fill="#273444" d="M218 230 Q237 235 243 258 L266 329 Q270 340 258 346 L244 351 Q234 355 229 342 L201 278 L187 253Z"/>
  <path id="cuff-left" fill="#d9d5ca" d="M54 324 L78 332 L72 350 L51 343Z"/>
  <path id="cuff-right" fill="#d9d5ca" d="M266 324 L242 332 L248 350 L269 343Z"/>
  <path id="hand-left" fill="#c79672" d="M53 339 Q43 339 39 348 L31 360 Q28 367 35 370 L44 368 L52 376 Q59 379 64 371 L74 353Z"/>
  <path id="hand-right" fill="#c79672" d="M267 339 Q277 339 281 348 L289 360 Q292 367 285 370 L276 368 L268 376 Q261 379 256 371 L246 353Z"/>
  <path id="knuckle-left" fill="#e4b18a" d="M34 358 L45 351 L49 356 L39 365Z"/>
  <path id="knuckle-right" fill="#e4b18a" d="M286 358 L275 351 L271 356 L281 365Z"/>

  <!-- Neck, ears, face and hair -->
  <path id="neck" fill="#bd8968" d="M137 185 L183 185 L190 225 L160 245 L130 225Z"/>
  <path id="ear-left" fill="#bd8968" d="M104 126 Q87 122 91 146 Q94 164 111 162Z"/>
  <path id="ear-right" fill="#bd8968" d="M216 126 Q233 122 229 146 Q226 164 209 162Z"/>
  <path id="face-shadow" fill="#9f705a" d="M104 99 Q112 66 160 67 Q208 66 216 99 L211 163 Q204 198 160 211 Q116 198 109 163Z"/>
  <path id="face" fill="#d5a17d" d="M108 100 Q116 76 160 76 Q204 76 212 100 L207 157 Q201 188 160 200 Q119 188 113 157Z"/>
  <path id="face-light" fill="#e4b18a" d="M160 78 Q197 78 208 101 L204 151 Q198 179 160 192Z"/>
  <path id="hair-left" fill="#17202c" d="M108 111 Q102 144 117 166 L111 183 Q97 166 96 139 Q93 105 112 82Z"/>
  <path id="hair-right" fill="#17202c" d="M212 111 Q218 144 203 166 L209 183 Q223 166 224 139 Q227 105 208 82Z"/>
  <path id="brow-left" fill="#25202a" d="M122 126 Q136 117 150 125 L148 131 Q135 126 123 133Z"/>
  <path id="brow-right" fill="#25202a" d="M170 125 Q184 117 198 126 L197 133 Q184 126 172 131Z"/>
  <path id="eye-left" fill="#161b24" d="M126 138 Q137 132 148 138 L146 143 Q136 140 127 144Z"/>
  <path id="eye-right" fill="#161b24" d="M172 138 Q183 132 194 138 L193 144 Q183 140 174 143Z"/>
  <path id="nose" fill="#a8765f" d="M157 139 L151 166 Q159 171 169 165 L163 139Z"/>
  <path id="moustache" fill="#25202a" d="M136 174 Q147 167 158 174 Q160 179 162 174 Q174 167 185 174 Q180 188 161 187 Q142 188 136 174Z"/>
  <path id="mouth" fill="#7e4d43" d="M148 192 Q160 197 172 192 L169 197 Q160 200 151 197Z"/>
  <path id="face-scarf" fill="#a83844" d="M128 204 L160 218 L192 204 L188 218 L160 233 L132 218Z"/>

  <!-- Fedora: broad brim, crown and crisp highlight -->
  <path id="hat-shadow" fill="#090e17" d="M71 89 Q157 65 249 89 Q264 94 258 102 Q163 117 62 103 Q55 97 71 89Z"/>
  <path id="hat-brim" fill="#1b2431" d="M69 83 Q160 61 251 83 Q267 89 256 97 Q160 113 64 98 Q53 92 69 83Z"/>
  <path id="hat-crown" fill="#273344" d="M99 83 Q101 38 121 23 Q158 7 197 22 Q220 39 222 82 Q163 73 99 83Z"/>
  <path id="hat-band" fill="#d84952" d="M99 72 Q160 63 221 72 L222 83 Q161 74 99 84Z"/>
  <path id="hat-rim" fill="#667487" d="M112 41 Q131 19 164 20 Q187 20 204 36 Q177 27 150 31 Q128 33 112 41Z"/>
  <path id="hat-highlight" fill="#83909a" d="M65 89 Q155 69 245 86 L246 89 Q156 77 68 93Z"/>
</svg>`;

type Layer = {
  id: string;
  geometry: ShapeGeometry;
  material: MeshBasicMaterial;
  z: number;
};

const ARM_PIVOTS: Record<string, [number, number]> = {
  'arm-left': [105, 238],
  'arm-right': [215, 238],
  'hand-left': [55, 353],
  'hand-right': [265, 353],
  'cuff-left': [60, 337],
  'cuff-right': [260, 337],
};
const SVG_SCALE = 0.0037;

/** A crisp vector detective on a camera-facing SVG plane beside the unchanged voxel desk. */
export const VectorAvatar: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const billboard = useRef<Group>(null);
  const { bob, typing } = avatarMotion(frame, fps);
  const layers = useMemo(() => {
    const parsed = new SVGLoader().parse(DETECTIVE_SVG);
    const result: Layer[] = [];
    let index = 0;
    for (const path of parsed.paths) {
      const style = path.userData?.style;
      if (!style?.fill || style.fill === 'none') continue;
      const id = path.userData?.node?.getAttribute('id') ?? `layer-${index}`;
      const pivot = ARM_PIVOTS[id];
      for (const shape of SVGLoader.createShapes(path)) {
        const geometry = new ShapeGeometry(shape);
        if (pivot) geometry.translate(-pivot[0], -pivot[1], 0);
        const material = new MeshBasicMaterial({
          color: style.fill,
          side: DoubleSide,
          depthTest: false,
          depthWrite: false,
        });
        result.push({ id, geometry, material, z: index * 0.00035 });
      }
      index += 1;
    }
    return result;
  }, []);

  useEffect(() => () => {
    for (const layer of layers) {
      layer.geometry.dispose();
      layer.material.dispose();
    }
  }, [layers]);

  useFrame(({ camera }) => {
    if (billboard.current) billboard.current.quaternion.copy(camera.quaternion);
  });

  return (
    <group ref={billboard} position={[1.67, 1.0 + bob, 1.12]}>
      <group position={[-160 * SVG_SCALE, 250 * SVG_SCALE, 0]} scale={[SVG_SCALE, -SVG_SCALE, SVG_SCALE]}>
        {layers.map((layer, index) => {
          const pivot = ARM_PIVOTS[layer.id];
          const armSide = layer.id.endsWith('left') ? -1 : 1;
          const swing = pivot ? armSide * typing * 0.018 : 0;
          return pivot ? (
            <group key={`${layer.id}-${index}`} position={[pivot[0], pivot[1], layer.z]} rotation={[0, 0, swing]}>
              <mesh geometry={layer.geometry} material={layer.material} renderOrder={100 + index} />
            </group>
          ) : (
            <mesh key={`${layer.id}-${index}`} geometry={layer.geometry} material={layer.material}
              position={[0, 0, layer.z]} renderOrder={100 + index} />
          );
        })}
      </group>
    </group>
  );
};
