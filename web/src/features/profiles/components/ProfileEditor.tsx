import Button from '@uikit/components/Button';
import StatusBanner from '@uikit/components/StatusBanner';
import { useProfileView } from '../hooks/useProfileView';

const ProfileEditor = () => {
  const { draft, updateField, saveDraft, resetDraft, isSaving, formError, canEdit } = useProfileView();

  if (!draft || !canEdit) {
    return null;
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void saveDraft();
  };

  return (
    <form className="card profile__section profile__editor" onSubmit={handleSubmit}>
      <header className="profile__section-header">
        <div>
          <p className="eyebrow">Edit profile</p>
          <p className="muted">Changes save to your private draft before publishing.</p>
        </div>
      </header>
      <div className="profile__section-body">
        <div className="profile__editor-grid">
        <label className="field">
          <span className="field__label">Display name</span>
          <input
            className="field__input"
            value={draft.display_name}
            onChange={(event) => updateField('display_name', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Tagline</span>
          <input
            className="field__input"
            value={draft.tagline}
            onChange={(event) => updateField('tagline', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Location</span>
          <input
            className="field__input"
            value={draft.location}
            onChange={(event) => updateField('location', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Avatar URL</span>
          <input
            className="field__input"
            value={draft.avatar_url}
            onChange={(event) => updateField('avatar_url', event.target.value)}
            placeholder="https://..."
          />
        </label>
        </div>
        <label className="field">
          <span className="field__label">Bio</span>
          <textarea
            className="field__input profile__textarea"
            value={draft.bio}
            onChange={(event) => updateField('bio', event.target.value)}
            rows={4}
          />
        </label>
        <div className="profile__editor-grid">
        <label className="field">
          <span className="field__label">Favorite genres (one per line)</span>
          <textarea
            className="field__input profile__textarea"
            value={draft.favorite_genres_text}
            rows={3}
            onChange={(event) => updateField('favorite_genres_text', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Influential artists</span>
          <textarea
            className="field__input profile__textarea"
            value={draft.favorite_artists_text}
            rows={3}
            onChange={(event) => updateField('favorite_artists_text', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">Essential albums</span>
          <textarea
            className="field__input profile__textarea"
            value={draft.favorite_albums_text}
            rows={3}
            onChange={(event) => updateField('favorite_albums_text', event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">On repeat</span>
          <textarea
            className="field__input profile__textarea"
            value={draft.favorite_tracks_text}
            rows={3}
            onChange={(event) => updateField('favorite_tracks_text', event.target.value)}
          />
        </label>
        </div>
        <StatusBanner variant="error" message={formError} />
        <div className="profile__editor-actions">
          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save profile'}
          </Button>
          <Button type="button" variant="ghost" onClick={resetDraft}>
            Cancel
          </Button>
        </div>
      </div>
    </form>
  );
};

export default ProfileEditor;
