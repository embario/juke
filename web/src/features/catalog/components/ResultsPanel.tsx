import ResultList from './ResultList';
import type { CatalogFilter, CatalogResults } from '../types';
import StatusBanner from '@uikit/components/StatusBanner';
import LoadingSpinner from '@uikit/components/Spinner';

type Props = {
  data: CatalogResults;
  filters: CatalogFilter[];
  isLoading: boolean;
  error: string | null;
};

const ResultsPanel = ({ data, filters, isLoading, error }: Props) => (
  <section className="results">
    <div className="results__header">
      <div>
        <p className="eyebrow">Query results</p>
        <h2>{data.albums.length + data.artists.length + data.tracks.length} matches</h2>
      </div>
    </div>
    {isLoading ? <LoadingSpinner /> : null}
    <StatusBanner variant="error" message={error} />
    {!isLoading && !error ? (
      <div className="results__grid">
        {filters.includes('artists') && (
          <ResultList title="Artists" items={data.artists} variant="artist" emptyCopy="No artists found." />
        )}
        {filters.includes('albums') && (
          <ResultList title="Albums" items={data.albums} variant="album" emptyCopy="No albums found." />
        )}
        {filters.includes('tracks') && (
          <ResultList
            title="Tracks"
            items={data.tracks}
            variant="track"
            emptyCopy="No tracks found."
            relatedAlbums={data.albums}
          />
        )}
      </div>
    ) : null}
  </section>
);

export default ResultsPanel;
