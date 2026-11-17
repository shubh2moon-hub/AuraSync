// AuraSync effect engine (reference version). The PC and phone renderers port these exact formulas.
// colorAt(effect, t, x) -> [r,g,b] 0..1 for time t (seconds) and horizontal position x (0..1).
const AuraEffects = (() => {
  const SPEED = { slow: 0.5, normal: 1, fast: 2 };

  function hsv(h, s, v) {
    h = ((h % 360) + 360) % 360 / 60;
    const i = Math.floor(h), f = h - i, p = v * (1 - s), q = v * (1 - s * f), u = v * (1 - s * (1 - f));
    return [[v, u, p], [q, v, p], [p, v, u], [p, q, v], [u, p, v], [v, p, q]][i % 6];
  }

  // Effects that match G-Helper's TUF keyboard modes, plus wallpaper-only extras.
  const EFFECTS = {
    static:  { name: "Static",      keyboard: true,  uniform: true,  at: (e, t) => e.color },
    breathe: { name: "Breathe",     keyboard: true,  uniform: true,  at: (e, t) => {
      const k = 0.5 - 0.5 * Math.cos(2 * Math.PI * t * SPEED[e.speed] / 4);
      return e.color.map(c => c * (0.04 + 0.96 * k * k)); } },
    cycle:   { name: "Color Cycle", keyboard: true,  uniform: true,  at: (e, t) => hsv(t * SPEED[e.speed] * 36, 1, 1) },
    strobe:  { name: "Strobe",      keyboard: true,  uniform: true,  at: (e, t) => {
      const ph = (t * SPEED[e.speed] * 1.6) % 1;
      const v = ph < 0.24 ? ph / 0.24 : 1 - (ph - 0.24) / 0.76;     // quick rise, slow fade
      return e.color.map(c => c * v); } },
    rainbow: { name: "Rainbow",     keyboard: false, uniform: false, at: (e, t, x) => hsv(x * 300 - t * SPEED[e.speed] * 72, 1, 1) },
    comet:   { name: "Comet",       keyboard: false, uniform: false, at: (e, t, x) => {
      const pos = ((t * SPEED[e.speed] * 0.35) % 1.4) - 0.2, d = pos - x;
      const k = d >= 0 ? Math.exp(-d * d / 0.02) : Math.exp(-d * d / 0.0015);   // long tail behind, sharp head
      return e.color.map((c, i) => 0.06 * c + k * c + (k > 0.85 ? (k - 0.85) * 2 : 0)); } },
  };

  // Display formula shared with toolkit.composite(): base + light * color, with a white-hot core.
  function composite(out, base, light, colorForX, width) {
    const n = light.length;
    for (let i = 0; i < n; i++) {
      const L = light[i] / 255;
      const c = colorForX[i % width];
      const hot = Math.min(1, Math.max(0, (L - 0.88) / 0.12)) * 0.35;
      for (let k = 0; k < 3; k++) {
        let v = base[i * 4 + k] / 255 * (1 - 0.55 * L) + L * c[k] * 0.95;
        v = v > 1 ? 1 : v;
        v += hot * (1 - v);
        out[i * 4 + k] = v * 255;
      }
      out[i * 4 + 3] = 255;
    }
  }

  return { EFFECTS, SPEED, hsv, composite };
})();
