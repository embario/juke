import AlbumCard from './AlbumCard';
import ArtistCard from './ArtistCard';
import TrackCard from './TrackCard';
import type { Album, Artist, Track } from '../types';
import { usePlayback } from '../../playback/hooks/usePlayback';
import { deriveTrackUri } from '../../playback/utils';

const buildAlbumLookup = (albums: Album[]): Map<string, Album> => {
  return albums.reduce((map, album) => {
    const potentialKeys = [album.url, album.spotify_id, album.id !== undefined ? String(album.id) : undefined];
    potentialKeys.forEach((key) => {
      if (key) {
        map.set(key, album);
      }
    });
    return map;
  }, new Map<string, Album>());
};

const extractArtwork = (album?: Album): string | undefined => {
  if (!album) {
    return undefined;
  }
  const firstImage = album.spotify_data?.images?.find((image) => Boolean(image));
  return typeof firstImage === 'string' ? firstImage : undefined;
};

const resolveTrackArtwork = (track: Track, lookup?: Map<string, Album>): string | undefined => {
  if (!lookup?.size) {
    return undefined;
  }

  const references: string[] = [];
  if (track.album) {
    if (typeof track.album === 'string') {
      references.push(track.album);
    } else if (typeof track.album === 'number') {
      references.push(String(track.album));
    } else {
      const albumRef = track.album as Album;
      if (albumRef.url) {
        references.push(albumRef.url);
      }
      if (albumRef.spotify_id) {
        references.push(albumRef.spotify_id);
      }
      if (albumRef.id !== undefined) {
        references.push(String(albumRef.id));
      }
    }
  }

  for (const ref of references) {
    const album = lookup.get(ref);
    const artworkUrl = extractArtwork(album);
    if (artworkUrl) {
      return artworkUrl;
    }
  }

  return undefined;
};

type Props = {
  title: string;
  items: Album[] | Artist[] | Track[];
  variant: 'album' | 'artist' | 'track';
  emptyCopy: string;
  relatedAlbums?: Album[];
};

const ResultList = ({ title, items, variant, emptyCopy, relatedAlbums = [] }: Props) => {
  const albumLookup = relatedAlbums.length ? buildAlbumLookup(relatedAlbums) : undefined;
  const { playTrack, isPlaying: playbackPlaying, isBusy: playbackBusy, activeTrackUri, canControl } = usePlayback();

  return (
    <div className="result-list">
      <div className="result-list__header">
        <p className="eyebrow">{variant}</p>
        <h3>{title}</h3>
      </div>
      {items.length === 0 ? <p className="muted">{emptyCopy}</p> : null}
      <ul>
        {items.map((item) => {
          const resource = item as Album | Artist | Track;
          const key = resource.spotify_id ?? resource.id;
          if (variant === 'album') {
            return (
              <li key={key}>
                <AlbumCard album={resource as Album} />
              </li>
            );
          }
          if (variant === 'artist') {
            return (
              <li key={key}>
                <ArtistCard artist={resource as Artist} />
              </li>
            );
          }
          const track = resource as Track;
          const artworkUrl = albumLookup ? resolveTrackArtwork(track, albumLookup) : undefined;
          const trackUri = deriveTrackUri(track);
          const isActive = Boolean(trackUri && activeTrackUri && trackUri === activeTrackUri);
          const canPlayTrack = Boolean(trackUri) && canControl;
          const handlePlay = canPlayTrack
            ? () => {
                void playTrack(track);
              }
            : undefined;
          return (
            <li key={key}>
              <TrackCard
                track={track}
                artworkUrl={artworkUrl}
                onPlay={handlePlay}
                isActive={isActive}
                isPlaying={isActive && playbackPlaying}
                isDisabled={!canPlayTrack}
                isLoading={isActive && playbackBusy}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default ResultList;
