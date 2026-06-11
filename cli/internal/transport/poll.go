package transport

import (
	"context"
	"log"
	"time"

	"github.com/embario/juke/cli/internal/api"
)

// PollTransport implements Transport by polling GET /api/v1/playback/state/
// on a fixed interval. It emits to the updates channel only when the state
// meaningfully changes (see stateChanged). This is the Phase 1b transport;
// Phase 3 replaces it with a real WebSocket client.
type PollTransport struct {
	client   *api.Client
	interval time.Duration
	cancel   context.CancelFunc
}

// NewPollTransport returns a PollTransport that polls on the given interval.
func NewPollTransport(client *api.Client, interval time.Duration) *PollTransport {
	return &PollTransport{client: client, interval: interval}
}

// Connect starts the polling goroutine. Returns nil immediately; errors during
// individual polls are logged and the loop continues.
func (p *PollTransport) Connect(ctx context.Context, updates chan<- *api.PlaybackState) error {
	pctx, cancel := context.WithCancel(ctx)
	p.cancel = cancel
	go p.run(pctx, updates)
	return nil
}

// Mode returns the transport identifier.
func (p *PollTransport) Mode() string { return ModePolling }

// Stop cancels the polling goroutine. The context passed to Connect is the
// primary cancellation path; Stop provides early teardown without it.
func (p *PollTransport) Stop() {
	if p.cancel != nil {
		p.cancel()
	}
}

// run is the polling goroutine. It fires on each tick, fetches state, and
// sends to updates only when the state has meaningfully changed.
func (p *PollTransport) run(ctx context.Context, updates chan<- *api.PlaybackState) {
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()

	var last *api.PlaybackState

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			next, err := p.client.PlaybackState()
			if err != nil {
				log.Printf("transport: poll error: %v", err)
				continue
			}
			if stateChanged(last, next) {
				last = next
				select {
				case updates <- next:
				default:
					// Daemon drain goroutine is backed up; skip this cycle.
				}
			}
		}
	}
}

// stateChanged reports whether the playback state has meaningfully changed
// between prev and next. It uses a shallow comparison on (IsPlaying,
// ProgressMs bucket, Track.URI) to avoid spurious events every 10 seconds
// when the user is idle and only updated_at changes on the backend.
//
// ProgressMs is bucketed to 10-second intervals (÷10000) so normal playback
// progress does not fire an event on every poll; a seek of > 10 seconds does.
func stateChanged(prev, next *api.PlaybackState) bool {
	if prev == nil && next == nil {
		return false
	}
	if prev == nil || next == nil {
		return true // one of them is nil (started / stopped)
	}

	prevURI := trackURI(prev)
	nextURI := trackURI(next)

	return prev.IsPlaying != next.IsPlaying ||
		prev.ProgressMs/10000 != next.ProgressMs/10000 ||
		prevURI != nextURI
}

func trackURI(s *api.PlaybackState) string {
	if s.Track != nil && s.Track.URI != nil {
		return *s.Track.URI
	}
	return ""
}
