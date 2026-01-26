import { GlobePoint } from './types';
import { SUPER_GENRES } from './constants';

// City centers across all continents for wide geographic distribution
const CITY_CENTERS = [
  // North America — major metros
  { lat: 40.71, lng: -74.01, weight: 8 },   // New York
  { lat: 34.05, lng: -118.24, weight: 7 },  // Los Angeles
  { lat: 41.88, lng: -87.63, weight: 5 },   // Chicago
  { lat: 29.76, lng: -95.37, weight: 4 },   // Houston
  { lat: 33.75, lng: -84.39, weight: 4 },   // Atlanta
  { lat: 43.65, lng: -79.38, weight: 4 },   // Toronto
  { lat: 25.76, lng: -80.19, weight: 4 },   // Miami
  { lat: 47.61, lng: -122.33, weight: 4 },  // Seattle
  { lat: 37.77, lng: -122.42, weight: 5 },  // San Francisco
  { lat: 39.74, lng: -104.99, weight: 3 },  // Denver
  { lat: 45.50, lng: -73.57, weight: 3 },   // Montreal
  { lat: 49.28, lng: -123.12, weight: 3 },  // Vancouver
  { lat: 19.43, lng: -99.13, weight: 4 },   // Mexico City
  { lat: 32.72, lng: -117.16, weight: 3 },  // San Diego
  { lat: 36.17, lng: -115.14, weight: 3 },  // Las Vegas
  { lat: 30.27, lng: -97.74, weight: 3 },   // Austin
  { lat: 42.36, lng: -71.06, weight: 3 },   // Boston
  { lat: 38.91, lng: -77.04, weight: 3 },   // Washington DC
  { lat: 35.23, lng: -80.84, weight: 2 },   // Charlotte
  { lat: 44.98, lng: -93.27, weight: 2 },   // Minneapolis
  { lat: 29.95, lng: -90.07, weight: 2 },   // New Orleans
  { lat: 36.16, lng: -86.78, weight: 3 },   // Nashville
  // Central America & Caribbean
  { lat: 9.93, lng: -84.08, weight: 2 },    // San José (Costa Rica)
  { lat: 18.47, lng: -69.90, weight: 2 },   // Santo Domingo
  { lat: 23.11, lng: -82.37, weight: 2 },   // Havana
  // Europe — major metros
  { lat: 51.51, lng: -0.13, weight: 7 },    // London
  { lat: 48.86, lng: 2.35, weight: 5 },     // Paris
  { lat: 52.52, lng: 13.41, weight: 4 },    // Berlin
  { lat: 41.90, lng: 12.50, weight: 3 },    // Rome
  { lat: 45.46, lng: 9.19, weight: 3 },     // Milan
  { lat: 59.33, lng: 18.07, weight: 3 },    // Stockholm
  { lat: 55.76, lng: 37.62, weight: 4 },    // Moscow
  { lat: 40.42, lng: -3.70, weight: 3 },    // Madrid
  { lat: 41.39, lng: 2.17, weight: 3 },     // Barcelona
  { lat: 50.85, lng: 4.35, weight: 2 },     // Brussels
  { lat: 52.37, lng: 4.90, weight: 3 },     // Amsterdam
  { lat: 47.50, lng: 19.04, weight: 2 },    // Budapest
  { lat: 50.08, lng: 14.44, weight: 2 },    // Prague
  { lat: 38.72, lng: -9.14, weight: 2 },    // Lisbon
  { lat: 60.17, lng: 24.94, weight: 2 },    // Helsinki
  { lat: 53.35, lng: -6.26, weight: 2 },    // Dublin
  { lat: 48.21, lng: 16.37, weight: 2 },    // Vienna
  { lat: 55.68, lng: 12.57, weight: 2 },    // Copenhagen
  { lat: 59.91, lng: 10.75, weight: 2 },    // Oslo
  { lat: 46.20, lng: 6.14, weight: 2 },     // Geneva
  { lat: 47.37, lng: 8.54, weight: 2 },     // Zurich
  { lat: 52.23, lng: 21.01, weight: 2 },    // Warsaw
  { lat: 44.43, lng: 26.10, weight: 2 },    // Bucharest
  { lat: 37.98, lng: 23.73, weight: 2 },    // Athens
  // Asia — major metros
  { lat: 35.68, lng: 139.69, weight: 6 },   // Tokyo
  { lat: 37.57, lng: 126.98, weight: 4 },   // Seoul
  { lat: 39.91, lng: 116.40, weight: 5 },   // Beijing
  { lat: 31.23, lng: 121.47, weight: 5 },   // Shanghai
  { lat: 22.32, lng: 114.17, weight: 3 },   // Hong Kong
  { lat: 28.61, lng: 77.23, weight: 5 },    // Delhi
  { lat: 19.08, lng: 72.88, weight: 4 },    // Mumbai
  { lat: 13.08, lng: 80.27, weight: 3 },    // Chennai
  { lat: 12.97, lng: 77.59, weight: 3 },    // Bangalore
  { lat: 1.35, lng: 103.82, weight: 3 },    // Singapore
  { lat: 13.76, lng: 100.50, weight: 3 },   // Bangkok
  { lat: 14.60, lng: 120.98, weight: 3 },   // Manila
  { lat: 21.03, lng: 105.85, weight: 2 },   // Hanoi
  { lat: 3.14, lng: 101.69, weight: 2 },    // Kuala Lumpur
  { lat: -6.21, lng: 106.85, weight: 3 },   // Jakarta
  { lat: 34.69, lng: 135.50, weight: 3 },   // Osaka
  { lat: 22.54, lng: 88.34, weight: 2 },    // Kolkata
  { lat: 25.20, lng: 55.27, weight: 3 },    // Dubai
  { lat: 35.69, lng: 51.39, weight: 2 },    // Tehran
  { lat: 41.01, lng: 28.98, weight: 3 },    // Istanbul
  { lat: 24.71, lng: 46.68, weight: 2 },    // Riyadh
  { lat: 31.95, lng: 35.93, weight: 2 },    // Amman
  { lat: 32.06, lng: 34.78, weight: 2 },    // Tel Aviv
  // South America
  { lat: -23.55, lng: -46.63, weight: 5 },  // São Paulo
  { lat: -22.91, lng: -43.17, weight: 3 },  // Rio de Janeiro
  { lat: -34.60, lng: -58.38, weight: 3 },  // Buenos Aires
  { lat: -33.45, lng: -70.67, weight: 2 },  // Santiago
  { lat: -12.05, lng: -77.04, weight: 2 },  // Lima
  { lat: 4.71, lng: -74.07, weight: 3 },    // Bogotá
  { lat: 10.49, lng: -66.88, weight: 2 },   // Caracas
  { lat: -15.79, lng: -47.88, weight: 2 },  // Brasília
  { lat: -3.12, lng: -60.02, weight: 1 },   // Manaus
  { lat: -1.83, lng: -78.18, weight: 1 },   // Quito region
  { lat: -25.29, lng: -57.63, weight: 1 },  // Asunción
  // Africa
  { lat: 6.52, lng: 3.38, weight: 3 },      // Lagos
  { lat: -1.29, lng: 36.82, weight: 2 },    // Nairobi
  { lat: 30.04, lng: 31.24, weight: 3 },    // Cairo
  { lat: -33.92, lng: 18.42, weight: 2 },   // Cape Town
  { lat: -26.20, lng: 28.05, weight: 2 },   // Johannesburg
  { lat: 33.59, lng: -7.62, weight: 2 },    // Casablanca
  { lat: 36.75, lng: 3.06, weight: 1 },     // Algiers
  { lat: 5.56, lng: -0.19, weight: 2 },     // Accra
  { lat: 9.02, lng: 38.75, weight: 1 },     // Addis Ababa
  { lat: 14.72, lng: -17.47, weight: 1 },   // Dakar
  { lat: -4.32, lng: 15.31, weight: 1 },    // Kinshasa
  { lat: -6.79, lng: 39.28, weight: 1 },    // Dar es Salaam
  { lat: 12.05, lng: -1.52, weight: 1 },    // Ouagadougou
  // Oceania
  { lat: -33.87, lng: 151.21, weight: 4 },  // Sydney
  { lat: -37.81, lng: 144.96, weight: 3 },  // Melbourne
  { lat: -27.47, lng: 153.03, weight: 2 },  // Brisbane
  { lat: -36.85, lng: 174.76, weight: 2 },  // Auckland
  { lat: -31.95, lng: 115.86, weight: 2 },  // Perth
  { lat: -41.29, lng: 174.78, weight: 1 },  // Wellington
];

const USERNAMES = [
  'melodymaven', 'basshead99', 'vinylchild', 'synthwave_sam', 'acousticanna',
  'drumloop_dave', 'jazzfingers', 'rocknroller', 'popqueen', 'folkfire',
  'classicvibes', 'raprhythm', 'countryroads', 'indiebliss', 'edmsoul',
  'pianokeys', 'guitarslinger', 'mixmaster', 'beatboxer', 'songbird',
];

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

/**
 * 20% of points are placed randomly across the globe (not tied to any city)
 * to ensure wide geographic coverage when zooming in anywhere.
 */
const GLOBAL_SCATTER_RATIO = 0.20;

export type SeedUserPoint = {
  username: string;
  lat?: number;
  lng?: number;
};

export function generateMockPoints(count: number = 2000, seedUser?: SeedUserPoint): GlobePoint[] {
  const rng = seededRandom(42);
  const points: GlobePoint[] = [];
  const totalWeight = CITY_CENTERS.reduce((sum, c) => sum + c.weight, 0);
  const globalScatterCount = Math.floor(count * GLOBAL_SCATTER_RATIO);
  const cityCount = count - globalScatterCount;

  // City-clustered points (80%)
  for (let i = 0; i < cityCount; i++) {
    // Pick a city weighted by population
    let r = rng() * totalWeight;
    let city = CITY_CENTERS[0];
    for (const c of CITY_CENTERS) {
      r -= c.weight;
      if (r <= 0) {
        city = c;
        break;
      }
    }

    // Wider scatter around city center (5-15 degrees spread)
    // This creates regional coverage, not just a tight dot on the city
    const spread = 5.0 + rng() * 10.0;
    const lat = city.lat + (rng() - 0.5) * spread;
    const lng = city.lng + (rng() - 0.5) * spread;

    // Uniform clout distribution across the full 0–1 range
    const clout = rng();

    const genre = SUPER_GENRES[Math.floor(rng() * SUPER_GENRES.length)];
    const username = `${USERNAMES[Math.floor(rng() * USERNAMES.length)]}${i}`;

    points.push({
      id: i + 1,
      username,
      lat: Math.round(Math.max(-85, Math.min(85, lat)) * 100) / 100,
      lng: Math.round(((lng + 180) % 360 - 180) * 100) / 100,
      clout: Math.round(clout * 100) / 100,
      top_genre: genre,
      display_name: username.replace(/[_\d]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).trim(),
    });
  }

  // Random global scatter points (20%) — distributed across all latitudes/longitudes
  for (let i = 0; i < globalScatterCount; i++) {
    const idx = cityCount + i;
    // Use cosine-weighted latitude for uniform sphere distribution
    const lat = Math.asin(2 * rng() - 1) * (180 / Math.PI);
    const lng = (rng() * 360) - 180;

    // Uniform clout distribution
    const clout = rng();

    const genre = SUPER_GENRES[Math.floor(rng() * SUPER_GENRES.length)];
    const username = `${USERNAMES[Math.floor(rng() * USERNAMES.length)]}${idx}`;

    points.push({
      id: idx + 1,
      username,
      lat: Math.round(lat * 100) / 100,
      lng: Math.round(lng * 100) / 100,
      clout: Math.round(clout * 100) / 100,
      top_genre: genre,
      display_name: username.replace(/[_\d]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).trim(),
    });
  }

  if (seedUser) {
    const fallbackCity = CITY_CENTERS[0];
    const seedLat = seedUser.lat ?? fallbackCity.lat;
    const seedLng = seedUser.lng ?? fallbackCity.lng;
    points.unshift({
      id: 0,
      username: seedUser.username,
      lat: Math.round(Math.max(-85, Math.min(85, seedLat)) * 100) / 100,
      lng: Math.round(((seedLng + 180) % 360 - 180) * 100) / 100,
      clout: 0.85,
      top_genre: SUPER_GENRES[0],
      display_name: seedUser.username.replace(/[_\d]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).trim(),
    });
  }

  return points;
}
