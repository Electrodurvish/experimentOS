import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { VariantResult } from '../api';
import { formatRate } from '../lib/format';

interface Datum {
  key: string;
  rate: number;
  err: [number, number];
  isControl: boolean;
  lower: number;
  upper: number;
}

/** Conversion rate per variant with 95% Wilson CI whiskers. Single measure → no legend; x labels name the arms. */
export function ConversionChart({ variants, controlKey }: { variants: Record<string, VariantResult>; controlKey?: string }) {
  const data: Datum[] = Object.entries(variants).map(([key, v]) => ({
    key,
    rate: v.conversion_rate,
    err: [Math.max(0, v.conversion_rate - v.ci_lower), Math.max(0, v.ci_upper - v.conversion_rate)],
    isControl: key === controlKey,
    lower: v.ci_lower,
    upper: v.ci_upper,
  }));
  if (data.length === 0) return null;
  return (
    <figure className="chart" aria-label="Conversion rate by variant with 95% confidence intervals">
      <figcaption className="chart-caption">Conversion rate by variant (95% CI)</figcaption>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="key" tickLine={false} axisLine={{ stroke: 'var(--border)' }} tick={{ fill: 'var(--text-2)', fontSize: 12 }} />
          <YAxis
            tickFormatter={(v: number) => formatRate(v, 0)}
            tickLine={false}
            axisLine={false}
            width={44}
            tick={{ fill: 'var(--text-2)', fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: 'var(--hover)' }}
            content={({ active, payload }) => {
              const d = active && payload?.[0] ? (payload[0].payload as Datum) : null;
              if (!d) return null;
              return (
                <div className="chart-tooltip">
                  <strong>{d.key}</strong>
                  {d.isControl && <span className="muted"> (control)</span>}
                  <div>{formatRate(d.rate, 2)}</div>
                  <div className="muted small">
                    CI {formatRate(d.lower, 2)} – {formatRate(d.upper, 2)}
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="rate" radius={[4, 4, 0, 0]} maxBarSize={56}>
            {data.map((d) => (
              <Cell key={d.key} fill={d.isControl ? 'var(--series-control)' : 'var(--series-1)'} />
            ))}
            <ErrorBar dataKey="err" width={8} strokeWidth={1.5} stroke="var(--text-1)" direction="y" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
