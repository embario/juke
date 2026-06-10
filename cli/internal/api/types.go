// Package api contains the Juke backend HTTP client and mirrored response types.
package api

// PlaybackState mirrors web/src/features/playback/types.ts:36-43.
// It is a stub in Phase 1; the polling transport (Phase 1b) will populate it.
type PlaybackState struct {
	Provider   string        `json:"provider"`
	IsPlaying  bool          `json:"is_playing"`
	ProgressMs int           `json:"progress_ms"`
	Track      *PlaybackTrack  `json:"track,omitempty"`
	Device     *PlaybackDevice `json:"device,omitempty"`
	UpdatedAt  string          `json:"updated_at,omitempty"`
}

// PlaybackTrack is a minimal mirror of the backend track shape.
type PlaybackTrack struct {
	ID         *string `json:"id,omitempty"`
	URI        *string `json:"uri,omitempty"`
	Name       string  `json:"name,omitempty"`
	DurationMs *int    `json:"duration_ms,omitempty"`
	ArtworkURL *string `json:"artwork_url,omitempty"`
}

// PlaybackDevice is a minimal mirror of the backend device shape.
type PlaybackDevice struct {
	ID            *string `json:"id,omitempty"`
	Name          *string `json:"name,omitempty"`
	Type          *string `json:"type,omitempty"`
	VolumePercent *int    `json:"volume_percent,omitempty"`
	IsActive      *bool   `json:"is_active,omitempty"`
}
