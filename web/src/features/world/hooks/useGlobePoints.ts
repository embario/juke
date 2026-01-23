import { useState, useCallback, useRef } from 'react';
import { GlobePoint } from '../types';
import { fetchGlobePoints, GlobeQueryParams } from '../api/worldApi';

type UseGlobePointsReturn = {
  points: GlobePoint[];
  loading: boolean;
  error: string | null;
  loadPoints: (params: GlobeQueryParams) => void;
};

export function useGlobePoints(token: string | null): UseGlobePointsReturn {
  const [points, setPoints] = useState<GlobePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadPoints = useCallback(
    (params: GlobeQueryParams) => {
      // Cancel previous in-flight request
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      fetchGlobePoints(params, token)
        .then((data) => {
          if (!controller.signal.aborted) {
            setPoints(data);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(err.message || 'Failed to load globe points');
            setLoading(false);
          }
        });
    },
    [token],
  );

  return { points, loading, error, loadPoints };
}
