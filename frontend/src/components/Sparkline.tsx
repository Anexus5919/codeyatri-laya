import { useMemo, type PointerEvent as RPointerEvent } from "react";

interface Props {
  values: (number | null)[];
  width: number;
  height: number;
  selected: number | null;
  hover: number | null;
  onHover: (i: number | null) => void;
  onSelect: (i: number) => void;
  tone?: "ember" | "cyan" | "ivory" | "acid";
  label: string;
}

export function Sparkline({ values, width, height, selected, hover, onHover, onSelect, tone = "cyan", label }: Props) {
  const n = values.length;
  const pad = 4;
  const { path, area, max } = useMemo(() => {
    let mx = 0;
    for (const v of values) if (v !== null && v > mx) mx = v;
    mx = mx || 1;
    const xs = (i: number) => pad + (n <= 1 ? 0.5 : i / (n - 1)) * (width - pad * 2);
    const ys = (v: number) => height - pad - (v / mx) * (height - pad * 2);
    let d = "";
    let a = "";
    let open = false;
    let startX = 0;
    let lastX = 0;
    values.forEach((v, i) => {
      if (v === null) {
        if (open) a += `L${lastX} ${height - pad} L${startX} ${height - pad} Z `;
        open = false;
        return;
      }
      const x = xs(i);
      const y = ys(v);
      if (!open) {
        d += `M${x} ${y} `;
        a += `M${x} ${height - pad} L${x} ${y} `;
        startX = x;
        open = true;
      } else {
        d += `L${x} ${y} `;
        a += `L${x} ${y} `;
      }
      lastX = x;
    });
    if (open) a += `L${lastX} ${height - pad} L${startX} ${height - pad} Z`;
    return { path: d, area: a, max: mx };
  }, [values, width, height, n]);

  const xOf = (i: number) => pad + (n <= 1 ? 0.5 : i / (n - 1)) * (width - pad * 2);
  const idx = (e: RPointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = (e.clientX - r.left - pad) / Math.max(1, r.width - pad * 2);
    return Math.max(0, Math.min(n - 1, Math.round(t * (n - 1))));
  };
  const yOf = (v: number) => height - pad - (v / max) * (height - pad * 2);
  const hv = hover !== null ? values[hover] : null;
  return (
    <svg
      className={`spark tone-${tone}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      onPointerMove={(e) => n && onHover(idx(e))}
      onPointerDown={(e) => n && onSelect(idx(e))}
      onPointerLeave={() => onHover(null)}
    >
      <path d={area} className="spark-area" />
      <path d={path} className="spark-line" />
      {selected !== null && n ? <line x1={xOf(selected)} x2={xOf(selected)} y1={0} y2={height} className="spark-sel" /> : null}
      {hover !== null && n ? (
        <g className="spark-hover">
          <line x1={xOf(hover)} x2={xOf(hover)} y1={0} y2={height} />
          {hv !== null && hv !== undefined ? <circle cx={xOf(hover)} cy={yOf(hv)} r={3.5} /> : null}
        </g>
      ) : null}
    </svg>
  );
}
