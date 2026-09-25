import { useEffect, useState } from 'react';
import { experiments } from '../api';

/** Fetch health scores for a set of experiments in parallel. Missing/failed → null. */
export function useHealthScores(ids: string[]): { scores: Record<string, number | null>; loading: boolean } {
  const key = ids.join(',');
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const list = key ? key.split(',') : [];
    if (list.length === 0) {
      setScores({});
      return;
    }
    let active = true;
    setLoading(true);
    Promise.all(
      list.map((id) =>
        experiments.health(id).then(
          (h) => [id, h.health?.overall_score ?? null] as const,
          () => [id, null] as const,
        ),
      ),
    ).then((pairs) => {
      if (!active) return;
      setScores(Object.fromEntries(pairs));
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [key]);

  return { scores, loading };
}
