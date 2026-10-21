import { useEffect, useState } from "react";

type State<T> = { data?: T; error?: string; loading: boolean };

/** Runs `fn` whenever `deps` change; ignores responses that arrive after a newer request. */
export function useAsync<T>(fn: () => Promise<T> | null, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ loading: true });
  useEffect(() => {
    const promise = fn();
    if (!promise) {
      setState({ loading: false });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    promise
      .then((data) => live && setState({ data, loading: false }))
      .catch((e: Error) => live && setState({ error: e.message, loading: false }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
