/**
 * Onboarding API
 *
 * API functions for fetching genres, artists, and saving profile data.
 */

import { apiClient } from '@shared/api/apiClient';
import type { Genre, Artist, CityLocation, OnboardingData } from '../types';

// Fetch featured genres with top artists
export async function fetchFeaturedGenres(): Promise<Genre[]> {
  // For now, return curated list. In production, this would call /api/v1/genres/featured/
  // which would return genres with top artists from Spotify

  const FEATURED_GENRES: Genre[] = [
    {
      id: 'hiphop',
      name: 'Hip-Hop',
      spotifyId: 'hip-hop',
      topArtists: [
        { name: 'Drake', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb4293385d324db8558179afd9' },
        { name: 'Kendrick Lamar', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb52696c89a9a2d7ed21d73e92' },
        { name: 'J. Cole', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb078456da9d0b07fd2b0c3eba' },
      ],
    },
    {
      id: 'rock',
      name: 'Rock',
      spotifyId: 'rock',
      topArtists: [
        { name: 'Foo Fighters', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb9a43b87b50cd3d03544bb3e5' },
        { name: 'Green Day', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb4b2a1d9ef4e6c16e5cbe8e3e' },
        { name: 'Nirvana', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb7bbad89a61061304ec842588' },
      ],
    },
    {
      id: 'pop',
      name: 'Pop',
      spotifyId: 'pop',
      topArtists: [
        { name: 'Taylor Swift', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb5a00969a4698c3132a15fbb0' },
        { name: 'Dua Lipa', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb1bbee4a02f85ecc58d385c3e' },
        { name: 'The Weeknd', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb214f3cf1cbe7139c1e26ffbb' },
      ],
    },
    {
      id: 'rnb',
      name: 'R&B',
      spotifyId: 'r-n-b',
      topArtists: [
        { name: 'SZA', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb0895066d172e1f51f520bc65' },
        { name: 'Frank Ocean', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb7b2a499c1df8cf0ab8ee9722' },
        { name: 'Daniel Caesar', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb94a251170e5bc6c5cc67385a' },
      ],
    },
    {
      id: 'electronic',
      name: 'Electronic',
      spotifyId: 'electronic',
      topArtists: [
        { name: 'Daft Punk', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eba7bfd7835b5c1eee0c95fa6e' },
        { name: 'Calvin Harris', imageUrl: 'https://i.scdn.co/image/ab6761610000e5ebf150017ca69c8793503c2d4f' },
        { name: 'Disclosure', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb855d1cdf330080d9dafcc825' },
      ],
    },
    {
      id: 'country',
      name: 'Country',
      spotifyId: 'country',
      topArtists: [
        { name: 'Morgan Wallen', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb21ed0100a3a4e5aa3c57f6dd' },
        { name: 'Luke Combs', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb5db6179a702a931368a1b2c2' },
        { name: 'Chris Stapleton', imageUrl: 'https://i.scdn.co/image/ab6761610000e5ebce5c7a49d8694e0d99e974ee' },
      ],
    },
    {
      id: 'jazz',
      name: 'Jazz',
      spotifyId: 'jazz',
      topArtists: [
        { name: 'Kamasi Washington', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb717a36763ed9c9e9ed4c6d49' },
        { name: 'Robert Glasper', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb6d922ec4c474c0200f0c5655' },
        { name: 'Esperanza Spalding', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb8cbf3b45d3c2ca98c35f4e3f' },
      ],
    },
    {
      id: 'classical',
      name: 'Classical',
      spotifyId: 'classical',
      topArtists: [
        { name: 'Yo-Yo Ma', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb36a5ffce3db2c3c0a7a8b67f' },
        { name: 'Lang Lang', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb7f4c7c12d8c9c5f9f5db0dc8' },
        { name: 'Hilary Hahn', imageUrl: 'https://i.scdn.co/image/ab6761610000e5ebc8e7e4c2f0c85a6f2c6c2a47' },
      ],
    },
    {
      id: 'latin',
      name: 'Latin',
      spotifyId: 'latin',
      topArtists: [
        { name: 'Bad Bunny', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb9ad50e478a469c5f4d974426' },
        { name: 'J Balvin', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb5e787f6c1d56e97b0c6e68c6' },
        { name: 'Rosalía', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb30c6f97f0a269a02c87bb95e' },
      ],
    },
    {
      id: 'indie',
      name: 'Indie',
      spotifyId: 'indie',
      topArtists: [
        { name: 'Tame Impala', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb5765c90bb5ef3a86f7cb980d' },
        { name: 'Arctic Monkeys', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb7da39dea0a72f581535fb11f' },
        { name: 'Mac DeMarco', imageUrl: 'https://i.scdn.co/image/ab6761610000e5eb922e58b75ed5d8c7f4eb8f73' },
      ],
    },
  ];

  // In production:
  // const response = await apiClient.get<Genre[]>('/api/v1/genres/featured/', { token });
  // return response;

  return FEATURED_GENRES;
}

// Search artists via Spotify
export async function searchArtists(query: string, token: string): Promise<Artist[]> {
  if (!query.trim()) return [];

  try {
    // Use external=true to search Spotify directly, q is the search parameter
    const response = await apiClient.get<{
      results: Array<{
        pk: number;
        name: string;
        spotify_id: string;
        spotify_data?: { images?: string[] };
      }>;
    }>(
      '/api/v1/artists/',
      {
        token,
        query: { external: 'true', q: query },
      }
    );

    // Results are in a 'results' array
    const artists = response.results || [];

    return artists.slice(0, 10).map((artist) => ({
      id: String(artist.pk),
      name: artist.name,
      spotifyId: artist.spotify_id,
      imageUrl: artist.spotify_data?.images?.[0] || '',
      genres: [],
    }));
  } catch (err) {
    console.error('Artist search failed:', err);
    // Return empty array on error, let UI handle gracefully
    return [];
  }
}

// Search cities (placeholder - would use GeoNames or similar in production)
export async function searchCities(query: string): Promise<CityLocation[]> {
  if (!query.trim()) return [];

  // Static list of major cities for MVP
  const CITIES: CityLocation[] = [
    { name: 'New York', country: 'USA', lat: 40.71, lng: -74.01 },
    { name: 'Los Angeles', country: 'USA', lat: 34.05, lng: -118.24 },
    { name: 'Chicago', country: 'USA', lat: 41.88, lng: -87.63 },
    { name: 'Houston', country: 'USA', lat: 29.76, lng: -95.37 },
    { name: 'Phoenix', country: 'USA', lat: 33.45, lng: -112.07 },
    { name: 'London', country: 'UK', lat: 51.51, lng: -0.13 },
    { name: 'Paris', country: 'France', lat: 48.86, lng: 2.35 },
    { name: 'Tokyo', country: 'Japan', lat: 35.68, lng: 139.69 },
    { name: 'Sydney', country: 'Australia', lat: -33.87, lng: 151.21 },
    { name: 'Toronto', country: 'Canada', lat: 43.65, lng: -79.38 },
    { name: 'Berlin', country: 'Germany', lat: 52.52, lng: 13.41 },
    { name: 'Amsterdam', country: 'Netherlands', lat: 52.37, lng: 4.90 },
    { name: 'Seoul', country: 'South Korea', lat: 37.57, lng: 126.98 },
    { name: 'Singapore', country: 'Singapore', lat: 1.35, lng: 103.82 },
    { name: 'Dubai', country: 'UAE', lat: 25.20, lng: 55.27 },
    { name: 'Mumbai', country: 'India', lat: 19.08, lng: 72.88 },
    { name: 'São Paulo', country: 'Brazil', lat: -23.55, lng: -46.63 },
    { name: 'Mexico City', country: 'Mexico', lat: 19.43, lng: -99.13 },
    { name: 'Lagos', country: 'Nigeria', lat: 6.52, lng: 3.38 },
    { name: 'Cairo', country: 'Egypt', lat: 30.04, lng: 31.24 },
    { name: 'Austin', country: 'USA', lat: 30.27, lng: -97.74 },
    { name: 'Nashville', country: 'USA', lat: 36.16, lng: -86.78 },
    { name: 'Atlanta', country: 'USA', lat: 33.75, lng: -84.39 },
    { name: 'Miami', country: 'USA', lat: 25.76, lng: -80.19 },
    { name: 'Seattle', country: 'USA', lat: 47.61, lng: -122.33 },
    { name: 'San Francisco', country: 'USA', lat: 37.77, lng: -122.42 },
    { name: 'Denver', country: 'USA', lat: 39.74, lng: -104.99 },
    { name: 'Boston', country: 'USA', lat: 42.36, lng: -71.06 },
    { name: 'Philadelphia', country: 'USA', lat: 39.95, lng: -75.17 },
    { name: 'Detroit', country: 'USA', lat: 42.33, lng: -83.05 },
  ];

  const lowerQuery = query.toLowerCase();
  return CITIES.filter(
    (city) =>
      city.name.toLowerCase().includes(lowerQuery) ||
      city.country.toLowerCase().includes(lowerQuery)
  ).slice(0, 10);
}

// Save profile with onboarding data
export async function saveOnboardingProfile(data: OnboardingData, token: string): Promise<void> {
  const payload = {
    favorite_genres: data.favoriteGenres,
    favorite_artists: data.rideOrDieArtist ? [data.rideOrDieArtist.spotifyId] : [],
    location: data.location?.name || '',
    city_lat: data.location?.lat || null,
    city_lng: data.location?.lng || null,
    custom_data: {
      hated_genres: data.hatedGenres,
      rainy_day_mood: data.rainyDayMood,
      workout_vibe: data.workoutVibe,
      favorite_decade: data.favoriteDecade,
      listening_style: data.listeningStyle,
      age_range: data.ageRange,
      onboarding_completed_at: new Date().toISOString(),
    },
  };

  await apiClient.patch('/api/v1/music-profiles/me/', payload, { token });
}

// Get Spotify OAuth URL - use full backend URL
export function getSpotifyOAuthUrl(): string {
  const backendUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.BACKEND_URL || 'http://localhost:8001';
  return `${backendUrl}/api/v1/social-auth/login/spotify/`;
}
