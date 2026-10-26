/**
 * The film's ink and paper, in one place.
 *
 * This lived twice - once here and once inside nokia_scene1 - and the two drifted
 * far enough apart that changing the map's land colour in one of them changed
 * nothing on screen. A palette is a single fact about a film; it cannot have two
 * copies.
 */
export const PALETTE = {
  text: '#12233F',
  // The caption was 3.3:1 on paper, below the 4.5:1 a small label needs.
  caption: '#8A5410',
  dim: '#5C6472',
  // Land used to be #E2E6EC on #FAF8F3 - four percent apart in luma, so every map
  // was beige mush. A screen print puts the land down in ink and lets paper be sea.
  land: '#24374F',
  landEdge: '#0E1B2B',
  paper: '#F4EFE4',
};

export default PALETTE;
