import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const cwd = process.cwd();
const workspace = path.basename(cwd) === "sipi_harness" ? path.resolve("..") : cwd;
const boardPath =
  process.argv[2] ||
  path.join(workspace, "outputs", "kicad_microstrip_50ohm", "microstrip_50ohm_fr4_1p6.kicad_pcb");

function uuid() {
  return crypto.randomUUID();
}

function launchFootprint(reference, x, y) {
  return `\t(footprint "Microstrip_Launch_Pad_5x4mm"
\t\t(layer "F.Cu")
\t\t(uuid "${uuid()}")
\t\t(at ${x} ${y})
\t\t(property "Reference" "${reference}"
\t\t\t(at 0 -3 0)
\t\t\t(layer "F.SilkS")
\t\t\t(hide yes)
\t\t\t(uuid "${uuid()}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(property "Value" "MICROSTRIP_LAUNCH_PAD"
\t\t\t(at 0 3 0)
\t\t\t(layer "F.Fab")
\t\t\t(hide yes)
\t\t\t(uuid "${uuid()}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(attr smd exclude_from_bom)
\t\t(pad "1" smd rect
\t\t\t(at 0 0)
\t\t\t(size 5 4)
\t\t\t(layers "F.Cu" "F.Mask" "F.Paste")
\t\t\t(net 1 "SIG_50OHM")
\t\t\t(uuid "${uuid()}")
\t\t)
\t)
`;
}

function groundVia(x, y) {
  return `\t(via
\t\t(at ${x} ${y})
\t\t(size 0.8)
\t\t(drill 0.35)
\t\t(layers "F.Cu" "B.Cu")
\t\t(net 2)
\t\t(uuid "${uuid()}")
\t)
`;
}

function groundPlaneFootprint() {
  return `\t(footprint "Reference_Plane_BCu"
\t\t(layer "B.Cu")
\t\t(uuid "${uuid()}")
\t\t(at 40 20)
\t\t(property "Reference" "GND_PLANE"
\t\t\t(at 0 0 0)
\t\t\t(layer "B.Fab")
\t\t\t(hide yes)
\t\t\t(uuid "${uuid()}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(property "Value" "BOTTOM_REFERENCE_PLANE"
\t\t\t(at 0 0 0)
\t\t\t(layer "B.Fab")
\t\t\t(hide yes)
\t\t\t(uuid "${uuid()}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(attr smd exclude_from_bom)
\t\t(pad "1" smd rect
\t\t\t(at 0 0)
\t\t\t(size 78 38)
\t\t\t(layers "B.Cu")
\t\t\t(net 2 "GND")
\t\t\t(uuid "${uuid()}")
\t\t)
\t)
`;
}

function replaceSegmentNets(text) {
  return text.replace(/\(segment[\s\S]*?\n\t\)/g, (segment) => {
    if (!segment.includes('(layer "F.Cu")')) return segment;
    return segment.replace(/\(net \d+\)/, "(net 1)");
  });
}

function ensureFilledGroundPlane(text) {
  const zoneStart = text.indexOf("(zone");
  if (zoneStart === -1) return text;

  let depth = 0;
  let zoneEnd = -1;
  for (let i = zoneStart; i < text.length; i += 1) {
    if (text[i] === "(") depth += 1;
    if (text[i] === ")") depth -= 1;
    if (depth === 0) {
      zoneEnd = i + 1;
      break;
    }
  }
  if (zoneEnd === -1) return text;

  let zone = text.slice(zoneStart, zoneEnd);
  if (!zone.includes('(layer "B.Cu")')) return text;

  zone = zone.replace(/\(fill\s*\n\t\t\t\(thermal_gap 0\.5\)/, "(fill yes\n\t\t\t(thermal_gap 0.5)");
  zone = zone.replace(/\n\t\t\(filled_polygon[\s\S]*?\n\t\t\)/g, "");
  return `${text.slice(0, zoneStart)}${zone}${text.slice(zoneEnd)}`;
}

function removeExistingLaunchPads(text) {
  let output = text;
  for (const ref of ["J1", "J2"]) {
    while (true) {
      const marker = `(property "Reference" "${ref}"`;
      const markerIndex = output.indexOf(marker);
      if (markerIndex === -1) break;

      const start = output.lastIndexOf("(footprint ", markerIndex);
      if (start === -1) break;

      let depth = 0;
      let end = -1;
      for (let i = start; i < output.length; i += 1) {
        if (output[i] === "(") depth += 1;
        if (output[i] === ")") depth -= 1;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
      if (end === -1) {
        break;
      }
      output = `${output.slice(0, start)}${output.slice(end).replace(/^\r?\n/, "")}`;
    }
  }
  return output;
}

let text = fs.readFileSync(boardPath, "utf8");
text = removeExistingLaunchPads(text);

if (!text.includes('(net 1 "SIG_50OHM")')) {
  text = text.replace(/\(net 0 ""\)/, '(net 0 "")\n\t(net 1 "SIG_50OHM")\n\t(net 2 "GND")');
}

text = replaceSegmentNets(text);
text = text.replace(/\(zone\s*\n\t\t\(net \d+\)\s*\n\t\t\(net_name "[^"]*"\)\s*\n\t\t\(layer "B\.Cu"\)/, '(zone\n\t\t(net 2)\n\t\t(net_name "GND")\n\t\t(layer "B.Cu")');
text = ensureFilledGroundPlane(text);

const footprints = `${launchFootprint("J1", 5, 20)}${launchFootprint("J2", 75, 20)}`;
const groundVias = [groundVia(5, 14), groundVia(5, 26), groundVia(75, 14), groundVia(75, 26)].join("");
text = text.replace(/\t\(zone\n/, `${footprints}${groundVias}${groundPlaneFootprint()}\t(zone\n`);

fs.writeFileSync(boardPath, text, "utf8");
console.log(JSON.stringify({ ok: true, boardPath }, null, 2));
