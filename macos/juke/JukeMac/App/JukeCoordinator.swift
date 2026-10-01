import Foundation

/// Cross-section requests, so Radio (S3), Library + New Station (S4) and
/// Memories/Chat (S5) can hand work to each other without importing each
/// other's views or controllers.
///
/// - Radio shows `RadioRoute.newStation` inside the Radio section (the dial's
///   "+ New" slot and the station sheet's "Pull more records" set it).
/// - Library focuses a record when `libraryFocus` is set (the sleeve's
///   "Open the album" / "Open the artist" set it, then switch to `.library`).
/// - Anyone that creates or picks a station sets `stationRequest`; the radio
///   controller consumes it (plays now or after the current song) and clears it.
@MainActor
@Observable
final class JukeCoordinator {
    enum RadioRoute: Equatable, Sendable {
        case nowPlaying
        case newStation(NewStationDraft)
    }

    /// Where New Station starts and anything already chosen (for example the
    /// station sheet's "Pull more records" passes the station's seeds).
    struct NewStationDraft: Equatable, Sendable {
        enum Start: Equatable, Sendable { case records, feelings }
        var start: Start = .records
        var seeds: [Radio.Seed] = []
        var feelings: [String] = []
    }

    struct LibraryFocus: Equatable, Sendable {
        var kind: Radio.SeedKind
        var spotifyId: String
        /// Used as the crate search query when the item is not in the default crate.
        var title: String
    }

    struct StationRequest: Equatable, Sendable {
        enum Timing: Equatable, Sendable { case now, afterCurrentSong }
        var stationID: Radio.ID
        var timing: Timing
    }

    var radioRoute: RadioRoute = .nowPlaying
    var libraryFocus: LibraryFocus?
    var stationRequest: StationRequest?

    func openNewStation(_ draft: NewStationDraft = NewStationDraft()) {
        radioRoute = .newStation(draft)
    }

    func closeNewStation() {
        radioRoute = .nowPlaying
    }

    func requestStation(_ id: Radio.ID, timing: StationRequest.Timing) {
        radioRoute = .nowPlaying
        stationRequest = StationRequest(stationID: id, timing: timing)
    }

    func focusInLibrary(_ focus: LibraryFocus) {
        libraryFocus = focus
    }
}
