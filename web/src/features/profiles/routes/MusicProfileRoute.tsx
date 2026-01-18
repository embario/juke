import { useParams } from 'react-router-dom';
import { ProfileViewProvider } from '../context/ProfileViewContext';
import ProfileHero from '../components/ProfileHero';
import ProfileEditor from '../components/ProfileEditor';
import ProfileFavoritesGrid from '../components/ProfileFavoritesGrid';
import { useAuth } from '../../auth/hooks/useAuth';
import { useProfileView } from '../hooks/useProfileView';

const ProfileContent = ({ isAuthenticated }: { isAuthenticated: boolean }) => {
  const { mode, canEdit } = useProfileView();

  if (!isAuthenticated) {
    return (
      <div className="card profile__section profile__empty-state">
        <p className="eyebrow">Private workspace</p>
        <h3>Authenticate to curate your music presence.</h3>
        <p className="muted">
          Once signed in you can enter private mode, edit details, and share the URL with collaborators.
        </p>
      </div>
    );
  }

  return (
    <div className="profile__stack">
      <ProfileHero />
      {mode === 'edit' && canEdit ? <ProfileEditor /> : <ProfileFavoritesGrid />}
    </div>
  );
};

const MusicProfileRouteInner = ({ isAuthenticated }: { isAuthenticated: boolean }) => (
  <section className="profile">
    <ProfileContent isAuthenticated={isAuthenticated} />
  </section>
);

const MusicProfileRoute = () => {
  const { username } = useParams<{ username?: string }>();
  const { isAuthenticated } = useAuth();

  return (
    <ProfileViewProvider username={username}>
      <MusicProfileRouteInner isAuthenticated={isAuthenticated} />
    </ProfileViewProvider>
  );
};

export default MusicProfileRoute;
