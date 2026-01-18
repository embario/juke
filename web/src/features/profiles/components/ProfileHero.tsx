import Button from '@uikit/components/Button';
import { useProfileView } from '../hooks/useProfileView';

const ProfileHero = () => {
  const { profile, canEdit, mode, toggleMode } = useProfileView();

  if (!profile) {
    return null;
  }

  return (
    <div className="card profile__section profile__hero">
      <div className="profile__identity">
        {profile.avatar_url ? (
          <img src={profile.avatar_url} alt={profile.display_name || profile.username} />
        ) : (
          <div className="profile__avatar-placeholder" aria-hidden />
        )}
        <div>
          <h2>{profile.display_name || profile.username}</h2>
          <p className="muted">@{profile.username}</p>
          {profile.location ? <p className="profile__location">{profile.location}</p> : null}
        </div>
      </div>
      <div className="profile__hero-details">
        <p className="profile__tagline">{profile.tagline || 'No tagline yet. Broadcast your sonic identity.'}</p>
        {canEdit ? (
          <div className="profile__hero-actions">
            <Button variant="ghost" onClick={toggleMode} aria-label="toggle-edit">
              {mode === 'edit' ? 'Done' : 'Edit'}
            </Button>
            <span className="profile__mode-pill">{mode === 'edit' ? 'Editing private draft' : 'Viewing published profile'}</span>
          </div>
        ) : profile.is_owner ? (
          <span className="pill pill--link">Private mode available via header</span>
        ) : (
          <span className="pill">Listening in private guest mode</span>
        )}
      </div>
    </div>
  );
};

export default ProfileHero;
