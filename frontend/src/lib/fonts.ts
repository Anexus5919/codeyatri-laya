// Fonts are bundled (no network needed). Only the latin and latin-ext subsets are registered.
import sansLatin from "@fontsource-variable/ibm-plex-sans/files/ibm-plex-sans-latin-wght-normal.woff2?url";
import sansLatinExt from "@fontsource-variable/ibm-plex-sans/files/ibm-plex-sans-latin-ext-wght-normal.woff2?url";
import mono400 from "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2?url";
import mono500 from "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2?url";

const LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";
const LATIN_EXT = "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF";

const faces: [string, string, string, string][] = [
  ["IBM Plex Sans Variable", sansLatin, LATIN, "100 700"],
  ["IBM Plex Sans Variable", sansLatinExt, LATIN_EXT, "100 700"],
  ["IBM Plex Mono", mono400, LATIN, "400"],
  ["IBM Plex Mono", mono500, LATIN, "500"],
];

export function registerFonts(): Promise<unknown> {
  if (typeof FontFace === "undefined" || !document.fonts) return Promise.resolve();
  const loads = faces.map(([family, url, range, weight]) => {
    const face = new FontFace(family, `url(${url}) format("woff2")`, { weight, unicodeRange: range, display: "swap" });
    document.fonts.add(face);
    return face;
  });
  // Load the latin sans face now; the 3D tile and axis numbers are drawn into canvases and need it ready
  return Promise.all([loads[0].load(), loads[2].load()]).catch(() => undefined);
}
