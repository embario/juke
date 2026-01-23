import { useState, useCallback } from 'react';
import { MusicProfile } from '../../profiles/types';
import { fetchUserProfile } from '../api/worldApi';

type UseUserDetailReturn = {
  userDetail: MusicProfile | null;
  loading: boolean;
  error: string | null;
  loadUser: (username: string) => void;
  clearUser: () => void;
};

export function useUserDetail(token: string | null): UseUserDetailReturn {
  const [userDetail, setUserDetail] = useState<MusicProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadUser = useCallback(
    (username: string) => {
      setLoading(true);
      setError(null);

      fetchUserProfile(username, token)
        .then((data) => {
          setUserDetail(data);
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message || 'Failed to load user profile');
          setLoading(false);
        });
    },
    [token],
  );

  const clearUser = useCallback(() => {
    setUserDetail(null);
    setError(null);
  }, []);

  return { userDetail, loading, error, loadUser, clearUser };
}
