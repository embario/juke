import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuth } from '../../auth/hooks/useAuth';
import {
  fetchMyProfile,
  fetchProfileByUsername,
  searchProfiles,
  updateMyProfile,
} from '../api/profileApi';
import type { MusicProfile, MusicProfileSearchResult, MusicProfileUpdatePayload } from '../types';

type ProfileDraft = {
  display_name: string;
  tagline: string;
  bio: string;
  location: string;
  avatar_url: string;
  favorite_genres_text: string;
  favorite_artists_text: string;
  favorite_albums_text: string;
  favorite_tracks_text: string;
};

type ProfileViewContextValue = {
  profile: MusicProfile | null;
  draft: ProfileDraft | null;
  mode: 'view' | 'edit';
  canEdit: boolean;
  isPrivateContext: boolean;
  isLoading: boolean;
  isSaving: boolean;
  profileError: string | null;
  formError: string | null;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  searchResults: MusicProfileSearchResult[];
  isSearching: boolean;
  clearSearch: () => void;
  viewingUsername: string | null;
  updateField: (field: keyof ProfileDraft, value: string) => void;
  saveDraft: () => Promise<void>;
  resetDraft: () => void;
  toggleMode: () => void;
};

const ProfileViewContext = createContext<ProfileViewContextValue | undefined>(undefined);

type Props = {
  children: ReactNode;
  username?: string;
};

const listToMultiline = (values: string[]) => values.join('\n');
const multilineToList = (value: string): string[] =>
  value
    .split('\n')
    .map((entry) => entry.trim())
    .filter(Boolean);

const toDraft = (profile: MusicProfile): ProfileDraft => ({
  display_name: profile.display_name ?? '',
  tagline: profile.tagline ?? '',
  bio: profile.bio ?? '',
  location: profile.location ?? '',
  avatar_url: profile.avatar_url ?? '',
  favorite_genres_text: listToMultiline(profile.favorite_genres ?? []),
  favorite_artists_text: listToMultiline(profile.favorite_artists ?? []),
  favorite_albums_text: listToMultiline(profile.favorite_albums ?? []),
  favorite_tracks_text: listToMultiline(profile.favorite_tracks ?? []),
});

export const ProfileViewProvider = ({ children, username: routeUsername }: Props) => {
  const { token, username: authUsername, isAuthenticated } = useAuth();
  const [profile, setProfile] = useState<MusicProfile | null>(null);
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [profileError, setProfileError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MusicProfileSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  const viewingUsername = routeUsername ?? (isAuthenticated ? authUsername : null);
  const isPrivateContext = Boolean(isAuthenticated && !routeUsername);
  const canEdit = Boolean(profile?.is_owner && isPrivateContext);

  useEffect(() => {
    if (mode === 'edit' && !canEdit) {
      setMode('view');
    }
  }, [mode, canEdit]);

  const refreshProfile = useCallback(async () => {
    if (!isAuthenticated || !token || !viewingUsername) {
      setProfile(null);
      setDraft(null);
      return;
    }

    setIsLoading(true);
    setProfileError(null);

    try {
      const payload = isPrivateContext
        ? await fetchMyProfile(token)
        : await fetchProfileByUsername(token, viewingUsername);
      setProfile(payload);
      setDraft(toDraft(payload));
      setMode('view');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load music profile.';
      setProfile(null);
      setDraft(null);
      setProfileError(message);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, token, viewingUsername, isPrivateContext]);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  useEffect(() => {
    if (!isAuthenticated || !token) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }
    if (searchQuery.trim().length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    const handle = window.setTimeout(async () => {
      try {
        const results = await searchProfiles(token, searchQuery.trim());
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => window.clearTimeout(handle);
  }, [isAuthenticated, token, searchQuery]);

  const updateField = useCallback((field: keyof ProfileDraft, value: string) => {
    if (!canEdit) {
      return;
    }
    setDraft((prev) => (prev ? { ...prev, [field]: value } : prev));
  }, [canEdit]);

  const saveDraft = useCallback(async () => {
    if (!draft || !token || !canEdit) {
      return;
    }
    setIsSaving(true);
    setFormError(null);

    const payload: MusicProfileUpdatePayload = {
      display_name: draft.display_name,
      tagline: draft.tagline,
      bio: draft.bio,
      location: draft.location,
      avatar_url: draft.avatar_url,
      favorite_genres: multilineToList(draft.favorite_genres_text),
      favorite_artists: multilineToList(draft.favorite_artists_text),
      favorite_albums: multilineToList(draft.favorite_albums_text),
      favorite_tracks: multilineToList(draft.favorite_tracks_text),
    };

    try {
      const updated = await updateMyProfile(token, payload);
      setProfile(updated);
      setDraft(toDraft(updated));
      setMode('view');
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Unable to update profile.');
    } finally {
      setIsSaving(false);
    }
  }, [draft, token, canEdit]);

  const resetDraft = useCallback(() => {
    if (profile) {
      setDraft(toDraft(profile));
    }
    setMode('view');
  }, [profile]);

  const toggleMode = useCallback(() => {
    if (!canEdit) {
      return;
    }
    setMode((prev) => (prev === 'view' ? 'edit' : 'view'));
  }, [canEdit]);

  const clearSearch = useCallback(() => {
    setSearchResults([]);
    setIsSearching(false);
  }, []);

  const value = useMemo<ProfileViewContextValue>(() => ({
    profile,
    draft,
    mode,
    canEdit,
    isPrivateContext,
    isLoading,
    isSaving,
    profileError,
    formError,
    searchQuery,
    setSearchQuery,
    searchResults,
    isSearching,
    clearSearch,
    viewingUsername,
    updateField,
    saveDraft,
    resetDraft,
    toggleMode,
  }), [
    profile,
    draft,
    mode,
    canEdit,
    isPrivateContext,
    isLoading,
    isSaving,
    profileError,
    formError,
    searchQuery,
    searchResults,
    isSearching,
    viewingUsername,
    updateField,
    saveDraft,
    resetDraft,
    toggleMode,
    clearSearch,
  ]);

  return <ProfileViewContext.Provider value={value}>{children}</ProfileViewContext.Provider>;
};

export const useProfileViewContext = () => {
  const ctx = useContext(ProfileViewContext);
  if (!ctx) {
    throw new Error('useProfileViewContext must be used inside ProfileViewProvider');
  }
  return ctx;
};
