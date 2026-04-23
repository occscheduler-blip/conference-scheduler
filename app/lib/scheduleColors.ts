// 15 distinct base colors for department-level color coding
export const DEPARTMENT_BASE_COLORS = [
  { r: 31, g: 119, b: 180 },
  { r: 255, g: 127, b: 14 },
  { r: 44, g: 160, b: 44 },
  { r: 214, g: 39, b: 40 },
  { r: 148, g: 103, b: 189 },
  { r: 140, g: 86, b: 75 },
  { r: 227, g: 119, b: 194 },
  { r: 127, g: 201, b: 127 },
  { r: 188, g: 143, b: 143 },
  { r: 23, g: 190, b: 207 },
  { r: 158, g: 154, b: 36 },
  { r: 0, g: 172, b: 193 },
  { r: 255, g: 99, b: 71 },
  { r: 75, g: 0, b: 130 },
  { r: 220, g: 20, b: 60 },
];

// 7 shades per base color (light to dark, factor 0.3–0.9)
export const COLOR_SHADES = DEPARTMENT_BASE_COLORS.map(({ r, g, b }) => {
  const shades = [];
  for (let i = 0; i < 7; i++) {
    const factor = 0.3 + i * 0.1;
    const sr = Math.round(r + (255 - r) * (1 - factor));
    const sg = Math.round(g + (255 - g) * (1 - factor));
    const sb = Math.round(b + (255 - b) * (1 - factor));
    shades.push({ r: sr, g: sg, b: sb });
  }
  return shades;
});

export function rgbToHex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((x) => Math.round(x).toString(16).padStart(2, "0")).join("")}`;
}

export function getTextColor(color: { r: number; g: number; b: number }): string {
  const luminance = (color.r * 299 + color.g * 587 + color.b * 114) / 1000;
  return luminance > 128 ? "#000" : "#fff";
}

/**
 * Assigns consistent colors to presentations based on department and class.
 * Each department gets a distinct base color; each class within a department gets a shade.
 * Returns a map from presentation ID to { bg, text }.
 */
export function buildPresentationColorMap(
  items: Array<{ id: string; departmentName: string; class_id: string }>
): Map<string, { bg: string; text: string }> {
  const map = new Map<string, { bg: string; text: string }>();

  const deptToClasses = new Map<string, Set<string>>();
  for (const item of items) {
    if (!deptToClasses.has(item.departmentName)) {
      deptToClasses.set(item.departmentName, new Set());
    }
    deptToClasses.get(item.departmentName)!.add(item.class_id);
  }

  const deptsSorted = Array.from(deptToClasses.keys()).sort();
  const classesByDept = new Map<string, string[]>();
  for (const dept of deptsSorted) {
    classesByDept.set(dept, Array.from(deptToClasses.get(dept)!).sort());
  }

  for (const item of items) {
    if (!item.id) continue;
    const deptIndex = deptsSorted.indexOf(item.departmentName);
    const baseColorIndex = deptIndex % DEPARTMENT_BASE_COLORS.length;
    const classes = classesByDept.get(item.departmentName) ?? [];
    const classIndex = classes.indexOf(item.class_id);
    const shadeIndex = classIndex < 7 ? classIndex : classIndex % 7;
    const color = COLOR_SHADES[baseColorIndex][shadeIndex];
    map.set(item.id, { bg: rgbToHex(color.r, color.g, color.b), text: getTextColor(color) });
  }

  return map;
}
