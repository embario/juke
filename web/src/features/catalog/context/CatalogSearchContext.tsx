import { createContext, useCallback, useContext, useReducer, type ReactNode } from 'react';
import { useAuth } from '../../auth/hooks/useAuth';
import { fetchAllCatalogResources } from '../api/catalogApi';
import type { CatalogResults } from '../types';

type State = {
  query: string;
  data: CatalogResults;
  isLoading: boolean;
  error: string | null;
};

type Action =
  | { type: 'request'; query: string }
  | { type: 'success'; payload: CatalogResults }
  | { type: 'failure'; message: string };

const initialResults: CatalogResults = {
  genres: [],
  artists: [],
  albums: [],
  tracks: [],
};

const initialState: State = {
  query: '',
  data: initialResults,
  isLoading: false,
  error: null,
};

const reducer = (state: State, action: Action): State => {
  switch (action.type) {
    case 'request':
      return { ...state, query: action.query, isLoading: true, error: null };
    case 'success':
      return { ...state, data: action.payload, isLoading: false };
    case 'failure':
      return { ...state, isLoading: false, error: action.message };
    default:
      return state;
  }
};

type CatalogSearchContextValue = State & {
  runSearch: (query: string) => Promise<void>;
};

const CatalogSearchContext = createContext<CatalogSearchContextValue | undefined>(undefined);

type Props = {
  children: ReactNode;
};

export const CatalogSearchProvider = ({ children }: Props) => {
  const { token } = useAuth();
  const [state, dispatch] = useReducer(reducer, initialState);

  const runSearch = useCallback(
    async (query: string) => {
      if (!token) {
        dispatch({ type: 'failure', message: 'Authenticate to browse the catalog.' });
        return;
      }
      dispatch({ type: 'request', query });
      try {
        const payload = await fetchAllCatalogResources(token, query.trim());
        dispatch({ type: 'success', payload });
      } catch (error) {
        dispatch({
          type: 'failure',
          message: error instanceof Error ? error.message : 'Unable to fetch catalog.',
        });
      }
    },
    [token],
  );

  return (
    <CatalogSearchContext.Provider value={{ ...state, runSearch }}>
      {children}
    </CatalogSearchContext.Provider>
  );
};

export const useCatalogSearchContext = () => {
  const ctx = useContext(CatalogSearchContext);
  if (!ctx) {
    throw new Error('useCatalogSearchContext must be used within CatalogSearchProvider');
  }
  return ctx;
};
