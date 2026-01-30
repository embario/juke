import { useRef, useEffect, useCallback, useState, type MutableRefObject } from 'react';
import type { GlobeMethods } from 'react-globe.gl';
import * as THREE from 'three';
import { GlobePoint } from '../types';
import { getGenreColor } from '../constants';

// High-res earth textures from three-globe examples
const EARTH_TEXTURE = '//unpkg.com/three-globe/example/img/earth-night.jpg';
const EARTH_BUMP = '//unpkg.com/three-globe/example/img/earth-topology.png';

// Country boundaries (GeoJSON) for crisp vector overlays at any zoom
const COUNTRIES_URL = '//unpkg.com/world-atlas@2/countries-110m.json';

type CountryFeature = {
  type: string;
  properties: { name: string };
  geometry: object;
};

type Props = {
  points: GlobePoint[];
  width: number;
  height: number;
  globeRef?: MutableRefObject<GlobeMethods | null>;
  onPointClick?: (point: GlobePoint) => void;
  onCameraChange?: (pov: { lat: number; lng: number; altitude: number }) => void;
  onGlobeReady?: () => void;
};

export default function JukeGlobe({
  points,
  width,
  height,
  globeRef: externalRef,
  onPointClick,
  onCameraChange,
  onGlobeReady,
}: Props) {
  const internalRef = useRef<GlobeMethods | null>(null);
  const globeRef = externalRef ?? internalRef;
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [countries, setCountries] = useState<CountryFeature[]>([]);
  const [webglSupported, setWebglSupported] = useState(true);
  const [GlobeComponent, setGlobeComponent] = useState<React.ComponentType<any> | null>(null);

  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      if (event.message?.includes('WebGL') || event.message?.includes('react-globe')) {
        setWebglSupported(false);
      }
    };
    const handleRejection = (event: PromiseRejectionEvent) => {
      const message = String(event.reason ?? '');
      if (message.includes('WebGL') || message.includes('react-globe') || message.includes('VERTEX')) {
        setWebglSupported(false);
      }
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleRejection);
    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const checkWebglAndLoad = async () => {
      try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        const supported = !!gl;
        setWebglSupported(supported);
        if (!supported) return;

        try {
          const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
          renderer.getContext();
          renderer.dispose();
        } catch {
          setWebglSupported(false);
          return;
        }

        const mod = await import('react-globe.gl');
        if (!cancelled) {
          setGlobeComponent(() => mod.default);
        }
      } catch {
        setWebglSupported(false);
      }
    };

    checkWebglAndLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!webglSupported || !GlobeComponent) {
    return (
      <div
        style={{
          width,
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          background: 'rgba(0,0,0,0.85)',
          textAlign: 'center',
          padding: 24,
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>WebGL Unavailable</div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>
            Juke World needs WebGL to render. Try a physical device or enable GPU/WebGL in your emulator settings.
          </div>
        </div>
      </div>
    );
  }

  // Load country boundaries for vector polygon overlay
  useEffect(() => {
    fetch(COUNTRIES_URL)
      .then((res) => res.json())
      .then((topoData) => {
        // Convert TopoJSON to GeoJSON features
        // world-atlas provides TopoJSON; we need to extract features
        if (topoData.objects && topoData.objects.countries) {
          // Use topojson-client-like extraction
          const geometries = topoData.objects.countries.geometries;
          const features = geometries.map((geom: { type: string; arcs: number[][]; properties?: { name?: string } }) => {
            // Simple TopoJSON arc resolution
            return topoJsonFeature(topoData, geom);
          }).filter(Boolean);
          setCountries(features);
        } else if (topoData.features) {
          // Already GeoJSON
          setCountries(topoData.features);
        }
      })
      .catch(() => {
        // Silently fail — globe works without polygons
      });
  }, []);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    const controls = globe.controls();
    controls.autoRotate = false;
    controls.autoRotateSpeed = 0.0;
    controls.enableZoom = true;
    controls.enableRotate = true;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.ROTATE,
    };
    controls.touches = {
      ONE: THREE.TOUCH.ROTATE,
      TWO: THREE.TOUCH.DOLLY,
    };
    controls.enablePan = false;
    globe.pointOfView({ lat: 20, lng: 0, altitude: 2.5 });
  }, [globeRef]);

  // Debounced camera change handler for LOD
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe || !onCameraChange) return;

    const controls = globe.controls();
    const handler = () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const pov = globe.pointOfView();
        onCameraChange(pov);
      }, 300);
    };

    controls.addEventListener('change', handler);
    return () => {
      controls.removeEventListener('change', handler);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [globeRef, onCameraChange]);

  const handlePointClick = useCallback(
    (point: object) => {
      if (onPointClick) onPointClick(point as GlobePoint);
    },
    [onPointClick],
  );

  const pointAltitude = useCallback((d: object) => {
    const p = d as GlobePoint;
    return Math.pow(p.clout, 2) * 0.4;
  }, []);

  const pointRadius = useCallback((d: object) => {
    const p = d as GlobePoint;
    return Math.pow(p.clout, 1.5) * 0.45 + 0.05;
  }, []);

  const pointColor = useCallback((d: object) => {
    const p = d as GlobePoint;
    return getGenreColor(p.top_genre);
  }, []);

  const pointLabel = useCallback((d: object) => {
    const p = d as GlobePoint;
    return `
      <div style="
        background: rgba(0,0,0,0.85);
        border: 1px solid ${getGenreColor(p.top_genre)};
        border-radius: 6px;
        padding: 8px 12px;
        font-family: system-ui, sans-serif;
        color: #fff;
        font-size: 13px;
        min-width: 140px;
        max-width: 220px;
        box-sizing: border-box;
        line-height: 1.25;
        word-break: break-word;
        white-space: normal;
      ">
        <div style="font-weight: 600; margin-bottom: 4px;">${p.display_name}</div>
        <div style="color: #aaa; font-size: 11px;">@${p.username}</div>
        <div style="margin-top: 6px; display: flex; align-items: center; gap: 6px;">
          <div style="
            width: 60px; height: 6px; background: #333; border-radius: 3px; overflow: hidden;
          ">
            <div style="
              width: ${p.clout * 100}%; height: 100%;
              background: ${getGenreColor(p.top_genre)};
              border-radius: 3px;
            "></div>
          </div>
          <span style="color: ${getGenreColor(p.top_genre)}; font-weight: 600; font-size: 11px;">
            ${Math.round(p.clout * 100)}%
          </span>
        </div>
        <div style="margin-top: 4px; color: ${getGenreColor(p.top_genre)}; font-size: 11px; text-transform: capitalize;">
          ${p.top_genre}
        </div>
      </div>
    `;
  }, []);

  // Polygon accessors for country boundaries
  const polygonCapColor = useCallback(() => 'rgba(30, 40, 60, 0.4)', []);
  const polygonSideColor = useCallback(() => 'rgba(20, 30, 50, 0.2)', []);
  const polygonStrokeColor = useCallback(() => 'rgba(100, 180, 255, 0.15)', []);
  const polygonAltitude = useCallback(() => 0.005, []);

  return (
    <GlobeComponent
      ref={globeRef}
      width={width}
      height={height}
      globeImageUrl={EARTH_TEXTURE}
      bumpImageUrl={EARTH_BUMP}
      backgroundColor="rgba(0,0,0,0)"
      atmosphereColor="#00e5ff"
      atmosphereAltitude={0.25}
      // Country polygon overlay (vector — crisp at any zoom)
      polygonsData={countries}
      polygonCapColor={polygonCapColor}
      polygonSideColor={polygonSideColor}
      polygonStrokeColor={polygonStrokeColor}
      polygonAltitude={polygonAltitude}
      // Point layer
      pointsData={points}
      pointLat="lat"
      pointLng="lng"
      pointAltitude={pointAltitude}
      pointRadius={pointRadius}
      pointColor={pointColor}
      pointLabel={pointLabel}
      onPointClick={handlePointClick}
      pointResolution={8}
      pointsMerge={false}
      pointsTransitionDuration={800}
      onGlobeReady={onGlobeReady}
    />
  );
}

/**
 * Minimal TopoJSON → GeoJSON feature conversion.
 * Resolves arcs for Polygon and MultiPolygon geometries.
 */
function topoJsonFeature(
  topology: { arcs: number[][][]; transform?: { scale: number[]; translate: number[] } },
  geom: { type: string; arcs: number[][] | number[][][]; properties?: Record<string, unknown> },
): CountryFeature | null {
  try {
    const transform = topology.transform;
    const arcs = topology.arcs;

    function decodeArc(arcIndex: number): number[][] {
      const reversed = arcIndex < 0;
      const idx = reversed ? ~arcIndex : arcIndex;
      const arc = arcs[idx];
      if (!arc) return [];

      const coords: number[][] = [];
      let x = 0, y = 0;
      for (const point of arc) {
        x += point[0];
        y += point[1];
        if (transform) {
          coords.push([
            x * transform.scale[0] + transform.translate[0],
            y * transform.scale[1] + transform.translate[1],
          ]);
        } else {
          coords.push([x, y]);
        }
      }
      return reversed ? coords.reverse() : coords;
    }

    function decodeRing(ring: number[]): number[][] {
      const coords: number[][] = [];
      for (const arcIdx of ring) {
        const decoded = decodeArc(arcIdx);
        // Skip first point of subsequent arcs (shared with previous arc's last point)
        const start = coords.length > 0 ? 1 : 0;
        for (let i = start; i < decoded.length; i++) {
          coords.push(decoded[i]);
        }
      }
      return coords;
    }

    let geometry: object;
    if (geom.type === 'Polygon') {
      const rings = (geom.arcs as number[][]).map(decodeRing);
      geometry = { type: 'Polygon', coordinates: rings };
    } else if (geom.type === 'MultiPolygon') {
      const polys = (geom.arcs as number[][][]).map((polygon) =>
        polygon.map(decodeRing),
      );
      geometry = { type: 'MultiPolygon', coordinates: polys };
    } else {
      return null;
    }

    return {
      type: 'Feature',
      properties: { name: (geom.properties?.name as string) ?? '' },
      geometry,
    };
  } catch {
    return null;
  }
}
