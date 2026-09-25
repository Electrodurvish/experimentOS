import type { Experiment, ExperimentResults, VariantResult } from '../api/types';

export interface ArmSummary {
  key: string;
  result: VariantResult;
}

export interface ControlTreatment {
  control: ArmSummary | null;
  /** The best-performing non-control arm, or the only one. */
  treatment: ArmSummary | null;
  treatments: ArmSummary[];
}

/**
 * Split results into control and treatment arms. The control is the version's
 * is_control variant if known; otherwise the arm without a `lift` field (the backend
 * only computes lift for non-control arms); otherwise a key named "control".
 */
export function splitArms(results: ExperimentResults | null | undefined, experiment?: Experiment | null): ControlTreatment {
  const entries = Object.entries(results?.variants ?? {}).map(([key, result]) => ({ key, result }));
  if (entries.length === 0) return { control: null, treatment: null, treatments: [] };

  const configured = experiment?.current_version?.variants.find((v) => v.is_control)?.key;
  const control =
    entries.find((e) => e.key === configured) ??
    entries.find((e) => e.result.lift === undefined) ??
    entries.find((e) => e.key === 'control') ??
    entries[0]!;
  const treatments = entries.filter((e) => e.key !== control.key);
  const treatment =
    treatments.length === 0
      ? null
      : treatments.reduce((best, cur) => ((cur.result.lift ?? -Infinity) > (best.result.lift ?? -Infinity) ? cur : best));
  return { control, treatment, treatments };
}
