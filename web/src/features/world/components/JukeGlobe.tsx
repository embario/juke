import { useRef, useEffect, useCallback, useMemo, useState, type MutableRefObject } from 'react';
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
  onHexClick?: (hex: unknown) => void;
  onHexHover?: (hex: unknown | null) => void;
};

type HexLike = {
  lat?: number;
  lng?: number;
  points?: GlobePoint[];
};

export default function JukeGlobe({
  points,
  width,
  height,
  globeRef: externalRef,
  onCameraChange,
  onGlobeReady,
  onHexClick,
  onHexHover,
}: Props) {
  const internalRef = useRef<GlobeMethods | null>(null);
  const globeRef = externalRef ?? internalRef;
  const throttleRef = useRef<{ last: number; timeout: ReturnType<typeof setTimeout> | null }>({
    last: 0,
    timeout: null,
  });
  const [hoverCenter, setHoverCenter] = useState<{ lat: number; lng: number } | null>(null);
  const hoverMeshRef = useRef<THREE.Mesh | null>(null);
  const [countries, setCountries] = useState<CountryFeature[]>([]);
  const [webglSupported, setWebglSupported] = useState(true);
  const [GlobeComponent, setGlobeComponent] = useState<React.ComponentType<Record<string, unknown>> | null>(null);

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
        const testCanvas = document.createElement('canvas');
        const gl = testCanvas.getContext('webgl') || testCanvas.getContext('experimental-webgl');
        const supported = !!gl;
        setWebglSupported(supported);
        if (!supported) return;

        try {
          const renderer = new THREE.WebGLRenderer({ antialias: true });
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

  // Load country boundaries for vector polygon overlay
  useEffect(() => {
    if (!webglSupported || !GlobeComponent) return;
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
  }, [webglSupported, GlobeComponent]);

  useEffect(() => {
    if (!webglSupported || !GlobeComponent) return;
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
      TWO: THREE.TOUCH.PAN,
    };
    controls.enablePan = false;
    globe.pointOfView({ lat: 20, lng: 0, altitude: 2.5 });
  }, [globeRef, webglSupported, GlobeComponent]);

  // Debounced camera change handler for LOD
  useEffect(() => {
    if (!webglSupported || !GlobeComponent) return;
    const globe = globeRef.current;
    if (!globe || !onCameraChange) return;

    const controls = globe.controls();
    const handler = () => {
      const now = Date.now();
      const emit = () => {
        const pov = globe.pointOfView();
        onCameraChange(pov);
        throttleRef.current.last = Date.now();
        throttleRef.current.timeout = null;
      };

      const elapsed = now - throttleRef.current.last;
      if (elapsed >= 400) {
        if (throttleRef.current.timeout) {
          clearTimeout(throttleRef.current.timeout);
          throttleRef.current.timeout = null;
        }
        emit();
      } else if (!throttleRef.current.timeout) {
        throttleRef.current.timeout = setTimeout(emit, 400 - elapsed);
      }
    };

    controls.addEventListener('change', handler);
    const cleanupRef = throttleRef;
    return () => {
      controls.removeEventListener('change', handler);
      if (cleanupRef.current.timeout) {
        clearTimeout(cleanupRef.current.timeout);
        cleanupRef.current.timeout = null;
      }
    };
  }, [globeRef, onCameraChange, webglSupported, GlobeComponent]);

  const hexAltitude = useCallback((d: { sumWeight?: number }) => {
    const scaled = Math.min(0.05, 0.008 + (d.sumWeight ?? 0) * 0.012);
    return scaled;
  }, []);

  const hexTopColor = useCallback((d: { sumWeight?: number; points?: object[] }) => {
    const dominant = getDominantGenre(d.points);
    if (dominant) {
      return brightenColor(getGenreColor(dominant), 60);
    }
    const intensity = Math.min(1, (d.sumWeight ?? 0) / 2.5);
    const base = [20, 180, 255];
    const boost = Math.round(120 * intensity);
    return `rgb(${Math.min(255, base[0] + boost)}, ${Math.min(255, base[1] + boost)}, ${Math.min(255, base[2] + boost)})`;
  }, []);

  const hexSideColor = useCallback((d: { sumWeight?: number; points?: object[] }) => {
    const dominant = getDominantGenre(d.points);
    if (dominant) {
      const color = brightenColor(getGenreColor(dominant), 40);
      return `${color}55`;
    }
    const intensity = Math.min(1, (d.sumWeight ?? 0) / 2.5);
    return `rgba(0, 120, 200, ${0.22 + intensity * 0.35})`;
  }, []);

  const hexLabel = useCallback((d: { points?: object[]; sumWeight?: number }) => {
    const count = d.points?.length ?? 0;
    const dominant = getDominantGenre(d.points);
    const genreLabel = dominant ? dominant : 'mixed';
    return `
      <div style="
        background: rgba(0,0,0,0.85);
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 6px;
        padding: 8px 10px;
        color: #fff;
        font-size: 12px;
        font-family: system-ui, sans-serif;
        min-width: 140px;
      ">
        <div style="font-weight: 600; margin-bottom: 2px;">${count} users</div>
        <div style="color: rgba(255,255,255,0.6); text-transform: capitalize;">${genreLabel}</div>
      </div>
    `;
  }, []);

  useEffect(() => {
    let rafId = 0;
    const start = performance.now();
    const animate = (time: number) => {
      const mesh = hoverMeshRef.current;
      if (mesh) {
        const pov = globeRef.current?.pointOfView();
        const altitude = pov?.altitude ?? 1.0;
        const baseScale = Math.min(5.5, Math.max(1.2, altitude * 1.6));
        const t = (time - start) / 1000;
        const pulseScale = 1 + Math.sin(t * 3.5) * 0.35;
        const scale = baseScale * pulseScale;
        mesh.scale.set(scale, scale, scale);
        const material = mesh.material as THREE.MeshBasicMaterial;
        material.opacity = 0.55 + Math.sin(t * 3.5) * 0.25 + 0.2;
      }
      rafId = requestAnimationFrame(animate);
    };
    rafId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId);
  }, [globeRef]);

  const hoverRingObject = useMemo(() => {
    const geometry = new THREE.RingGeometry(0.6, 0.8, 64);
    const material = new THREE.MeshBasicMaterial({
      color: '#2CFF4E',
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.95,
    });
    const mesh = new THREE.Mesh(geometry, material);
    hoverMeshRef.current = mesh;
    return mesh;
  }, []);

  const hoverRingData = hoverCenter
    ? [{ lat: hoverCenter.lat, lng: hoverCenter.lng }]
    : [];

  // Polygon accessors for country boundaries
  const polygonCapColor = useCallback(() => 'rgba(30, 40, 60, 0.4)', []);
  const polygonSideColor = useCallback(() => 'rgba(20, 30, 50, 0.2)', []);
  const polygonStrokeColor = useCallback(() => 'rgba(100, 180, 255, 0.15)', []);
  const polygonAltitude = useCallback(() => 0.005, []);

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
      // Hex bin density layer
      hexBinPointsData={points}
      hexBinPointLat="lat"
      hexBinPointLng="lng"
      hexBinPointWeight={(d: object) => (d as GlobePoint).clout ?? 0.1}
      hexBinResolution={3}
      hexMargin={0.15}
      hexTopColor={hexTopColor}
      hexSideColor={hexSideColor}
      hexAltitude={hexAltitude}
      hexBinMerge={false}
      hexTransitionDuration={350}
      hexLabel={hexLabel}
      onHexClick={(hex: unknown) => {
        if (onHexClick) onHexClick(hex);
      }}
      onHexHover={(hex: unknown) => {
        if (!hex) {
          setHoverCenter(null);
        } else {
          const hexData = hex as HexLike;
          if (typeof hexData.lat === 'number' && typeof hexData.lng === 'number') {
            setHoverCenter({ lat: hexData.lat, lng: hexData.lng });
          } else if (hexData.points && hexData.points.length > 0) {
            const sum = hexData.points.reduce(
              (acc, point) => {
                acc.lat += point.lat;
                acc.lng += point.lng;
                return acc;
              },
              { lat: 0, lng: 0 },
            );
            setHoverCenter({ lat: sum.lat / hexData.points.length, lng: sum.lng / hexData.points.length });
          } else {
            setHoverCenter(null);
          }
        }
        if (onHexHover) onHexHover(hex);
      }}
      enablePointerInteraction={true}
      // Hover ring (single mesh)
      objectsData={hoverRingData}
      objectLat="lat"
      objectLng="lng"
      objectAltitude={() => 0.02}
      objectFacesSurfaces={() => true}
      objectThreeObject={hoverRingObject}
      objectThreeObjectUpdate={(obj: THREE.Object3D, data: unknown) => {
        obj.visible = Boolean(data);
      }}
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

function getDominantGenre(points?: object[]): string | null {
  if (!points || points.length === 0) {
    return null;
  }
  const counts: Record<string, number> = {};
  points.forEach((point) => {
    const genre = (point as GlobePoint).top_genre ?? 'other';
    counts[genre] = (counts[genre] ?? 0) + 1;
  });
  let top: string | null = null;
  let max = 0;
  Object.entries(counts).forEach(([genre, count]) => {
    if (count > max) {
      max = count;
      top = genre;
    }
  });
  return top;
}

function brightenColor(hex: string, amount: number): string {
  if (!hex.startsWith('#') || hex.length !== 7) {
    return hex;
  }
  const r = Math.min(255, parseInt(hex.slice(1, 3), 16) + amount);
  const g = Math.min(255, parseInt(hex.slice(3, 5), 16) + amount);
  const b = Math.min(255, parseInt(hex.slice(5, 7), 16) + amount);
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}
