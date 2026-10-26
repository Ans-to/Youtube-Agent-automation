/**
 * The world, drawn.
 *
 * The kit had a `globe-grid`: a wireframe sphere. That is not a map, and a
 * documentary about a company that sold to 130 countries cannot be told without
 * one. So here are the continents as hand-authored low-poly outlines in
 * longitude/latitude, a projection to turn them into pixels, and the four things
 * a map in a film actually has to do: draw itself on, light up a region, drop
 * pins on cities, and sweep an arc between two of them.
 *
 * Everything is a pure function of progress `p`. Nothing is random: the only
 * variation comes from a hash of a string, so a frame renders twice the same.
 *
 *     drawMap(ctx, { x, y, w, h, p, projection: 'equirect', cities: [...] })
 */

/* -------------------------------------------------------------------------
 * Land
 *
 * Coordinates are [longitude, latitude], west and south negative. These are
 * deliberately coarse - twelve to forty points per landmass - because the film
 * is 720p and a continent is never closer than a third of the frame. Detail
 * below this costs points and reads as noise.
 * ---------------------------------------------------------------------- */

export const CONTINENTS = [
  {
    id: 'north-america',
    name: 'North America',
    rings: [[
      [-168, 65], [-160, 71], [-140, 70], [-125, 70], [-110, 69], [-95, 70], [-85, 70],
      [-78, 73], [-70, 70], [-62, 60], [-56, 52], [-66, 48], [-70, 44], [-74, 40],
      [-76, 35], [-81, 31], [-80, 26], [-83, 29], [-88, 30], [-94, 29], [-97, 26],
      [-99, 20], [-105, 19], [-106, 24], [-110, 29], [-114, 31], [-118, 34], [-124, 40],
      [-124, 48], [-130, 54], [-140, 60], [-152, 59], [-162, 63],
    ]],
  },
  {
    id: 'greenland',
    name: 'Greenland',
    rings: [[
      [-45, 60], [-52, 65], [-55, 70], [-45, 78], [-30, 83], [-20, 80], [-22, 72],
      [-30, 66], [-40, 61],
    ]],
  },
  {
    id: 'south-america',
    name: 'South America',
    rings: [[
      [-81, 8], [-76, 10], [-70, 12], [-62, 11], [-52, 5], [-50, 0], [-44, -2],
      [-35, -6], [-38, -13], [-39, -18], [-48, -25], [-53, -33], [-58, -38], [-62, -40],
      [-65, -45], [-68, -52], [-70, -55], [-75, -52], [-74, -45], [-73, -37], [-71, -30],
      [-70, -23], [-71, -18], [-76, -14], [-79, -8], [-81, -5], [-80, 0], [-78, 6],
    ]],
  },
  {
    id: 'africa',
    name: 'Africa',
    rings: [[
      [-17, 15], [-16, 21], [-10, 28], [-6, 35], [0, 36], [10, 37], [18, 31], [25, 32],
      [32, 31], [35, 24], [38, 18], [43, 12], [51, 12], [43, 2], [41, -5], [40, -12],
      [35, -20], [32, -26], [27, -33], [20, -34], [15, -27], [12, -18], [9, -2], [5, 4],
      [-2, 5], [-8, 5], [-13, 9],
    ]],
  },
  {
    id: 'europe',
    name: 'Europe',
    rings: [[
      [-9, 43], [-2, 43], [0, 49], [4, 51], [8, 54], [9, 57], [11, 58], [13, 55],
      [19, 54], [24, 57], [28, 60], [30, 65], [26, 70], [20, 69], [15, 68], [12, 64],
      [10, 59], [6, 58], [4, 52], [0, 51], [-2, 44],
    ]],
    // Europe's coast is the most convoluted of the set, so it gets the detail
    // this film actually needs: the Baltic, Britain and Scandinavia as separate
    // outlines rather than one smeared blob.
    parts: [
      [[5, 58], [10, 59], [12, 65], [15, 68], [20, 70], [26, 71], [30, 70], [32, 66],
        [28, 60], [24, 57], [19, 54], [13, 55], [11, 58]],
      [[-6, 50], [-2, 51], [0, 53], [-1, 55], [-3, 58], [-6, 58], [-5, 54]],
      [[-10, 37], [-7, 37], [-6, 43], [-9, 43]],
    ],
  },
  {
    id: 'asia',
    name: 'Asia',
    rings: [[
      [30, 70], [45, 68], [60, 70], [75, 73], [90, 76], [105, 77], [120, 74], [135, 72],
      [145, 70], [160, 68], [170, 63], [178, 66], [172, 60], [162, 58], [155, 52],
      [143, 47], [140, 42], [130, 42], [127, 35], [122, 30], [119, 25], [112, 21],
      [108, 15], [105, 10], [103, 2], [100, 6], [97, 16], [92, 21], [88, 21], [80, 15],
      [77, 8], [72, 20], [68, 24], [61, 25], [57, 26], [50, 29], [44, 30], [38, 37],
      [34, 36], [30, 41], [30, 45], [36, 45], [40, 52], [42, 58], [38, 64],
    ]],
    parts: [
      [[68, 23], [72, 20], [77, 8], [80, 13], [87, 21], [80, 25], [72, 25]],
      [[129, 32], [134, 33], [139, 35], [142, 40], [145, 44], [143, 42], [138, 36], [132, 34]],
      [[95, 5], [100, 2], [104, -2], [106, -6], [100, -3], [96, 2]],
    ],
  },
  {
    id: 'australia',
    name: 'Australia',
    rings: [[
      [114, -22], [122, -18], [130, -12], [137, -12], [142, -11], [145, -15], [150, -22],
      [153, -27], [151, -33], [148, -38], [141, -38], [135, -35], [130, -32], [121, -34],
      [115, -34], [114, -28],
    ]],
    parts: [[[173, -35], [178, -38], [174, -42], [170, -46], [166, -46], [170, -42]]],
  },
  {
    id: 'antarctica',
    name: 'Antarctica',
    rings: [[
      [-180, -70], [-120, -72], [-60, -68], [0, -70], [60, -68], [120, -72], [180, -70],
      [180, -88], [-180, -88],
    ]],
  },
];

/** Cities the Nokia story actually visits, with coordinates and a hint of role. */
export const CITIES = {
  helsinki: { name: 'Helsinki', lon: 24.94, lat: 60.17 },
  espoo: { name: 'Espoo', lon: 24.66, lat: 60.21 },
  tampere: { name: 'Tampere', lon: 23.76, lat: 61.50 },
  stockholm: { name: 'Stockholm', lon: 18.07, lat: 59.33 },
  london: { name: 'London', lon: -0.13, lat: 51.51 },
  berlin: { name: 'Berlin', lon: 13.40, lat: 52.52 },
  paris: { name: 'Paris', lon: 2.35, lat: 48.86 },
  moscow: { name: 'Moscow', lon: 37.62, lat: 55.75 },
  newyork: { name: 'New York', lon: -74.01, lat: 40.71 },
  cupertino: { name: 'Cupertino', lon: -122.03, lat: 37.32 },
  seattle: { name: 'Seattle', lon: -122.33, lat: 47.61 },
  saopaulo: { name: 'Sao Paulo', lon: -46.63, lat: -23.55 },
  lagos: { name: 'Lagos', lon: 3.39, lat: 6.52 },
  cairo: { name: 'Cairo', lon: 31.24, lat: 30.04 },
  karachi: { name: 'Karachi', lon: 67.01, lat: 24.86 },
  delhi: { name: 'Delhi', lon: 77.21, lat: 28.61 },
  mumbai: { name: 'Mumbai', lon: 72.88, lat: 19.08 },
  beijing: { name: 'Beijing', lon: 116.41, lat: 39.90 },
  shanghai: { name: 'Shanghai', lon: 121.47, lat: 31.23 },
  tokyo: { name: 'Tokyo', lon: 139.69, lat: 35.69 },
  seoul: { name: 'Seoul', lon: 126.98, lat: 37.57 },
  singapore: { name: 'Singapore', lon: 103.82, lat: 1.35 },
  jakarta: { name: 'Jakarta', lon: 106.85, lat: -6.21 },
  sydney: { name: 'Sydney', lon: 151.21, lat: -33.87 },
  dubai: { name: 'Dubai', lon: 55.27, lat: 25.20 },
};

/* -------------------------------------------------------------------------
 * Projection
 * ---------------------------------------------------------------------- */

const RAD = Math.PI / 180;

/**
 * Longitude/latitude to a unit square, 0..1 in both axes, north at the top.
 *
 * `equirect` is the honest one and the only one I would put behind a "this is
 * where it happened" pin. `mercator` stretches the poles into the frame's
 * corners, which is what a business map wants for Europe and North America.
 * `winkel` is the compromise that keeps Africa and South America the right
 * size; without it, a map of "130 countries" quietly makes the global south
 * look a third the size it is.
 */
/**
 * Latitude bands.
 *
 * A full -90..90 equirectangular sheet spends a fifth of the frame on the poles
 * and puts Antarctica across the bottom like a plinth. Films crop it. Default is
 * the inhabited band: 82 north to 58 south, which still holds Cape Horn and
 * leaves the frame for typography.
 */
export const BOUNDS = {
  equirect: { latMin: -58, latMax: 82 },
  mercator: { latMin: -56, latMax: 74 },
  winkel: { latMin: -56, latMax: 76 },
};

export function project(lon, lat, kind = 'equirect', bounds) {
  const band = bounds || BOUNDS[kind] || BOUNDS.equirect;
  const x = (lon + 180) / 360;
  const span = band.latMax - band.latMin;
  let y;
  if (kind === 'mercator') {
    const clamped = Math.max(-85, Math.min(85, lat));
    const m = Math.log(Math.tan(Math.PI / 4 + (clamped * RAD) / 2));
    const top = Math.log(Math.tan(Math.PI / 4 + (band.latMax * RAD) / 2));
    const bottom = Math.log(Math.tan(Math.PI / 4 + (band.latMin * RAD) / 2));
    y = (top - m) / (top - bottom);
  } else if (kind === 'winkel') {
    // The latitude term of Winkel Tripel, near enough to keep Africa and South
    // America the size they actually are - a map that shrinks the global south
    // is a claim about the world, not a projection.
    const phi = lat * RAD;
    const alpha = Math.acos(Math.cos(phi));
    const sinc = Math.abs(alpha) < 1e-6 ? 1 : Math.sin(alpha) / alpha;
    const raw = (phi / Math.PI + Math.sin(phi) * 0.3183) * sinc;
    const topRaw = (band.latMax * RAD / Math.PI + Math.sin(band.latMax * RAD) * 0.3183) * (Math.sin(band.latMax * RAD) / (band.latMax * RAD));
    const botRaw = (band.latMin * RAD / Math.PI + Math.sin(band.latMin * RAD) * 0.3183) * (Math.sin(band.latMin * RAD) / (band.latMin * RAD));
    y = (topRaw - raw) / (topRaw - botRaw);
  } else {
    y = (band.latMax - lat) / span;
  }
  return { x, y };
}

/** Frame placement: unit square -> a pixel box, in a canvas context transform. */
export function frame(ctx, box, kind = 'equirect', bounds) {
  const { x, y, w, h } = box;
  return (lon, lat) => {
    const u = project(lon, lat, kind, bounds);
    return { x: x + u.x * w, y: y + u.y * h };
  };
}

function ringPath(ctx, ring, at) {
  ring.forEach(([lon, lat], i) => {
    const p = at(lon, lat);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
}

/* -------------------------------------------------------------------------
 * Pins and arcs
 * ---------------------------------------------------------------------- */

/**
 * A pin is a drop: it falls from above and lands with a ring. Drawn as three
 * concentric rings that expand and fade, because a static dot on a map is a
 * legend and an expanding one is an event.
 */
function drawPin(ctx, p, { at, city, t, colour, accent, size = 1 }) {
  const q = at(city.lon, city.lat);
  const drop = Math.min(1, Math.max(0, (t - 0.08) / 0.30));
  const ease = 1 - Math.pow(1 - drop, 3);
  const y = q.y - 26 * size * (1 - ease);
  const alpha = Math.min(1, drop * 1.6);

  ctx.save();
  ctx.globalAlpha = alpha;

  // The expansion ring: strongest the instant the pin lands.
  if (drop >= 0.999) {
    const ringT = Math.min(1, Math.max(0, (t - 0.38) / 0.40));
    if (ringT < 1) {
      ctx.strokeStyle = accent;
      ctx.globalAlpha = alpha * (1 - ringT) * 0.8;
      ctx.lineWidth = 1.6 * size;
      ctx.beginPath();
      ctx.arc(q.x, q.y, (5 + ringT * 22) * size, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.arc(q.x, y, 4.6 * size, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = colour;
  ctx.globalAlpha = alpha * 0.55;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(q.x, y + 3.4 * size);
  ctx.lineTo(q.x, q.y);
  ctx.stroke();

  ctx.restore();
}

/**
 * An arc between two cities.
 *
 * Not a great circle - a film map almost never is. It is a quadratic that lifts
 * off the midpoint by a fraction of the span, which reads as a flight path and
 * stays legible at 720p. The sweep is the length of the path, so a long haul
 * visibly takes longer than a short hop.
 */
export function arcControl(a, b) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // Lift perpendicular to the chord, always upward on screen.
  const lift = Math.min(0.42, len / 520) * len;
  const nx = -dy / len;
  const ny = dx / len;
  const sign = ny > 0 ? -1 : 1;
  return { cx: mx + nx * lift * sign, cy: my + ny * lift * sign };
}

function drawArc(ctx, a, b, t, { colour, width = 1.8, head = true }) {
  const { cx, cy } = arcControl(a, b);
  const steps = 48;
  const upto = Math.max(0, Math.min(1, t)) * steps;

  ctx.save();
  ctx.strokeStyle = colour;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.beginPath();
  let last = a;
  for (let i = 0; i <= steps; i += 1) {
    if (i > upto) break;
    const u = i / steps;
    const x = (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * cx + u * u * b.x;
    const y = (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * cy + u * u * b.y;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    last = { x, y };
  }
  ctx.stroke();

  if (head && upto > 0 && upto < steps - 0.5) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.arc(last.x, last.y, width * 1.5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

/* -------------------------------------------------------------------------
 * The map
 * ---------------------------------------------------------------------- */

/**
 * @param p            0..1 through the whole map's life
 * @param projection   'equirect' | 'mercator' | 'winkel'
 * @param ink          land fill; `dark` flips the whole sheet to ink-on-paper
 * @param graticule    draw the graticule (default: faint, on)
 * @param drawOn       index of the continent to reveal first; the rest follow
 * @param pins         [{ at: 'helsinki' | {lon,lat}, t: 0..1 }]
 * @param arcs         [{ from, to, t }]
 * @param glow         { region: 'europe' } fills a region with light
 */
export function drawMap(ctx, options = {}) {
  const {
    x = 0, y = 0, w = 960, h = 540,
    p = 1,
    projection = 'equirect',
    palette = {},
    ink,
    dark = false,
    graticule = true,
    land = '#E4E7EC',
    landEdge = '#C9CFD8',
    graticuleColour = 'rgba(18,35,63,0.06)',
    pins = [],
    arcs = [],
    glow = null,
    labels = [],
    bounds = null,
    scale = 1,
  } = options;

  const colour = palette.text || '#12233F';
  const accent = palette.caption || '#B4762A';
  const at = frame(ctx, { x, y, w, h }, projection, bounds);
  const band = bounds || BOUNDS[projection] || BOUNDS.equirect;

  ctx.save();

  // The ocean is the paper. A documentary map is not blue; a blue map is a
  // weather report.
  if (graticule) {
    ctx.strokeStyle = graticuleColour;
    ctx.lineWidth = 1;
    for (let lon = -150; lon <= 150; lon += 30) {
      const a = at(lon, 84);
      const b = at(lon, -84);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const a = at(-180, lat);
      const b = at(180, lat);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  // Regional light: a soft radial behind the land, so "the world lights up"
  // has something to be lit by.
  if (glow) {
    const g = at(glow.lon, glow.lat);
    const radius = (glow.radius || 0.18) * w;
    const grad = ctx.createRadialGradient(g.x, g.y, 0, g.x, g.y, radius);
    const strength = (glow.t === undefined ? 1 : glow.t) * (glow.strength || 0.5);
    grad.addColorStop(0, `rgba(180,118,42,${strength})`);
    grad.addColorStop(0.55, `rgba(180,118,42,${strength * 0.22})`);
    grad.addColorStop(1, 'rgba(180,118,42,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(x - w * 0.2, y - h * 0.2, w * 1.4, h * 1.4);
  }

  // Land, revealed continent by continent on a stagger.
  CONTINENTS.forEach((continent, i) => {
    // A draw-on that travels west to east: the film's habit of "and then the
    // whole world" is a left-to-right reveal, not a dissolve.
    // Was 0.06 + i*0.055 over 0.34, which put the last continent's arrival at
    // 0.79 - most of a shot spent looking at an empty ocean.
    const start = 0.02 + i * 0.035;
    const local = (p - start) / 0.24;
    const reveal = Math.max(0, Math.min(1, local));
    if (reveal <= 0) return;

    const allLats = continent.rings[0].map((r) => r[1]);
    // Entirely outside the visible band - Antarctica on a 58-south crop, the
    // arctic islands on a tight mercator - costs nothing and shows nothing.
    if (Math.max(...allLats) < band.latMin || Math.min(...allLats) > band.latMax) return;

    const rings = [continent.rings[0], ...(continent.parts || [])];
    rings.forEach((ring) => {
      ctx.save();
      ctx.beginPath();
      ringPath(ctx, ring, at);

      // Clip to the land itself, then paint a vertical band across it, so each
      // continent draws on from west to east instead of popping into existence.
      // (Clipping to the band and filling would have painted a rectangle - the
      // land path is gone once you clip with something else.)
      ctx.clip();

      const lons = ring.map((r) => r[0]);
      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const left = at(minLon, 0).x;
      const edge = at(minLon + (maxLon - minLon) * reveal, 0).x;

      ctx.fillStyle = ink || (dark ? 'rgba(232,236,242,0.95)' : land);
      ctx.fillRect(left - 4 * scale, y - h, Math.max(0, edge - left) + 4 * scale, h * 3);

      // The edge of the reveal reads as a drawing hand: a soft line at the front.
      if (reveal < 0.995) {
        ctx.save();
        ctx.strokeStyle = accent;
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 1.4 * scale;
        ctx.beginPath();
        ctx.moveTo(edge, y - h * 0.1);
        ctx.lineTo(edge, y + h * 1.1);
        ctx.stroke();
        ctx.restore();
      }
      ctx.restore();

      // Outline after the fill, unclipped, so a continent mid-reveal still has
      // its coast where it has been drawn.
      ctx.save();
      ctx.beginPath();
      ringPath(ctx, ring, at);
      ctx.strokeStyle = dark ? 'rgba(255,255,255,0.28)' : landEdge;
      ctx.lineWidth = 1 * scale;
      ctx.globalAlpha = reveal;
      ctx.stroke();
      ctx.restore();
      ctx.beginPath();
    });
  });

  // Arcs under the pins, pins over the arcs, labels last.
  arcs.forEach((a) => {
    const from = typeof a.from === 'string' ? CITIES[a.from] : a.from;
    const to = typeof a.to === 'string' ? CITIES[a.to] : a.to;
    if (!from || !to) return;
    drawArc(ctx, at(from.lon, from.lat), at(to.lon, to.lat), a.t === undefined ? p : a.t, {
      colour: a.colour || accent,
      width: (a.width || 1.8) * scale,
      head: a.head !== false,
    });
  });

  pins.forEach((pin) => {
    const city = typeof pin.at === 'string' ? CITIES[pin.at] : pin.at;
    if (!city) return;
    // A pin is sized against the map, not the canvas: on a 1280-wide frame the
    // old 3.6px head was a speck nobody could see.
    drawPin(ctx, p, {
      at, city,
      t: pin.t === undefined ? p : pin.t,
      colour, accent: pin.colour || colour,
      size: scale * Math.max(0.8, w / 900),
    });
  });

  labels.forEach((label) => {
    const city = typeof label.at === 'string' ? CITIES[label.at] : label.at;
    if (!city) return;
    const q = at(city.lon, city.lat);
    const t = label.t === undefined ? p : label.t;
    if (t <= 0) return;
    ctx.save();
    ctx.globalAlpha = Math.min(1, t);
    ctx.font = `600 ${11 * scale}px Inter`;
    ctx.fillStyle = colour;
    ctx.textAlign = label.align || 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(city.name || label.text, q.x + (label.dx === undefined ? 8 : label.dx), q.y + (label.dy === undefined ? -10 : label.dy));
    ctx.restore();
  });

  ctx.restore();
}

/**
 * A region's worth of cities, for "and then it reached everywhere".
 * Deterministic: the order is fixed, the timings are a stagger.
 */
export const REGIONS = {
  europe: ['helsinki', 'stockholm', 'london', 'berlin', 'paris', 'moscow'],
  americas: ['newyork', 'cupertino', 'seattle', 'saopaulo'],
  asia: ['delhi', 'mumbai', 'beijing', 'shanghai', 'tokyo', 'seoul', 'singapore', 'jakarta'],
  africa: ['lagos', 'cairo'],
  oceania: ['sydney'],
  world: ['helsinki', 'london', 'newyork', 'saopaulo', 'lagos', 'cairo', 'moscow', 'delhi',
    'beijing', 'singapore', 'tokyo', 'sydney', 'cupertino'],
};

export const MAP_PROJECTIONS = ['equirect', 'mercator', 'winkel'];
