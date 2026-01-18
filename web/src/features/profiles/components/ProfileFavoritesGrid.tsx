import StatusBanner from '@uikit/components/StatusBanner';
import LoadingSpinner from '@uikit/components/Spinner';
import { useProfileView } from '../hooks/useProfileView';

const ProfileFavoritesGrid = () => {
  const { profile, isLoading, profileError } = useProfileView();

  if (profileError) {
    return <StatusBanner variant="error" message={profileError} />;
  }

  if (isLoading) {
    return (
      <section className="card profile__section">
        <LoadingSpinner />
      </section>
    );
  }

  if (!profile) {
    return (
      <section className="card profile__section">
        <p>No profile data yet. Use your header username button to enter private mode and start drafting.</p>
      </section>
    );
  }

  const favoriteSections = [
    {
      title: 'Favorite genres',
      subtitle: 'Your sonic palette',
      items: profile.favorite_genres ?? [],
    },
    {
      title: 'Influential artists',
      subtitle: 'Voices that raised you',
      items: profile.favorite_artists ?? [],
    },
    {
      title: 'Essential albums',
      subtitle: 'Desert island pressings',
      items: profile.favorite_albums ?? [],
    },
    {
      title: 'On repeat',
      subtitle: 'What is looping now',
      items: profile.favorite_tracks ?? [],
    },
  ];

  return (
    <div className="profile__sections">
      <section className="card profile__section profile__section--about">
        <header className="profile__section-header">
          <div>
            <p className="eyebrow">About</p>
            <p className="profile__section-subtitle">Bio and recent presence</p>
          </div>
        </header>
        <div className="profile__section-body profile__section-body--accent">
          <p className="profile__bio">{profile.bio || 'This artist has not published a bio yet.'}</p>
        </div>
        <footer className="profile__section-footer">
          <span className="profile__timestamp-pill">Updated {new Date(profile.modified_at).toLocaleString()}</span>
        </footer>
      </section>
      {favoriteSections.map((section) => (
        <section key={section.title} className="card profile__section profile__section--stacked">
          <header className="profile__section-header">
            <div>
              <p className="eyebrow">{section.title}</p>
              <p className="profile__section-subtitle">{section.subtitle}</p>
            </div>
          </header>
          <div className="profile__section-body">
            {section.items.length === 0 ? (
              <p className="profile__section-empty">Nothing documented.</p>
            ) : (
              <ul className="profile__section-list">
                {section.items.map((item) => (
                  <li key={item}>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      ))}
    </div>
  );
};

export default ProfileFavoritesGrid;
