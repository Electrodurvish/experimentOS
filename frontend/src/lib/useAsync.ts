import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (data: T | undefined) => void;
}

/**
 * Run `fn` whenever `key` changes (or reload() is called). Pass key = null to skip.
 * The latest `fn` is always used; stale responses are ignored.
 */
export function useAsync<T>(fn: () => Promise<T>, key: string | null): AsyncState<T> {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [loading, setLoading] = useState<boolean>(key !== null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (key === null) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(undefined);
    fnRef.current().then(
      (value) => {
        if (!active) return;
        setData(value);
        setLoading(false);
      },
      (err: unknown) => {
        if (!active) return;
        setError(err);
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [key, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}

/** Wrap an async action with busy/error state. */
export function useAction<A extends unknown[], R>(action: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const ref = useRef(action);
  ref.current = action;
  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setBusy(true);
    setError(undefined);
    try {
      return await ref.current(...args);
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { run, busy, error, clearError: () => setError(undefined) };
}
