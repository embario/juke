import Foundation

/// Thin wrappers for every `/api/v1/radio/` endpoint in the contract.
extension JukeAPI {
    private static let radio = "radio/"

    /// `GET stations/`. The server creates the personal station on first call.
    func stations() async throws -> [Radio.Station] {
        try await get(Self.radio + "stations/", as: Radio.StationList.self).stations
    }

    /// `POST stations/`
    func createStation(name: String? = nil, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station {
        try await send(.post, Self.radio + "stations/", body: Radio.CreateStationRequest(name: name, seeds: seeds, feelings: feelings))
    }

    /// `PATCH stations/<id>/`. The response carries the final frequency.
    func updateStation(_ id: Radio.ID, _ changes: Radio.UpdateStationRequest) async throws -> Radio.Station {
        try await send(.patch, Self.radio + "stations/\(id)/", body: changes)
    }

    /// `DELETE stations/<id>/` (not allowed for the personal station).
    func deleteStation(_ id: Radio.ID) async throws {
        try await delete(Self.radio + "stations/\(id)/")
    }

    /// `POST stations/<id>/exclusions/`
    func addExclusion(stationID: Radio.ID, _ exclusion: Radio.CreateExclusionRequest) async throws -> Radio.Exclusion {
        try await send(.post, Self.radio + "stations/\(stationID)/exclusions/", body: exclusion)
    }

    /// `DELETE exclusions/<id>/`
    func deleteExclusion(_ id: Radio.ID) async throws {
        try await delete(Self.radio + "exclusions/\(id)/")
    }

    /// `PUT reactions/`: replaces this track's reactions.
    func setReactions(spotifyTrackID: String, stationID: Radio.ID?, reactions: [String]) async throws -> Radio.ReactionsResponse {
        try await send(.put, Self.radio + "reactions/", body: Radio.ReactionsRequest(spotifyTrackId: spotifyTrackID, stationId: stationID, reactions: reactions))
    }

    /// `POST stations/<id>/next`
    func nextTracks(stationID: Radio.ID, count: Int? = nil, recentTrackIDs: [String]? = nil) async throws -> Radio.NextTracksResponse {
        let body = Radio.NextTracksRequest(count: count.map { min(10, max(1, $0)) }, recentTrackIds: recentTrackIDs)
        return try await send(.post, Self.radio + "stations/\(stationID)/next", body: body)
    }

    /// `POST play`
    func play(stationID: Radio.ID, mode: Radio.PlayMode, deviceID: String? = nil) async throws -> Radio.PlayResponse {
        try await send(.post, Self.radio + "play", body: Radio.PlayRequest(stationId: stationID, mode: mode, deviceId: deviceID))
    }

    /// `POST events/` (204)
    func postEvent(_ event: Radio.EventRequest) async throws {
        try await sendExpectingNoContent(.post, Self.radio + "events/", body: event)
    }

    /// `GET crate/?kind=&q=`. Without a query: the personal crate. With one: Spotify search.
    func crate(kind: Radio.SeedKind, query: String? = nil) async throws -> [Radio.CrateItem] {
        var items = [URLQueryItem(name: "kind", value: kind.crateQueryValue)]
        if let query = query?.trimmingCharacters(in: .whitespacesAndNewlines), !query.isEmpty {
            items.append(URLQueryItem(name: "q", value: query))
        }
        return try await get(Self.radio + "crate/", query: items, as: Radio.CrateResponse.self).items
    }

    /// `GET session/summary`
    func sessionSummary() async throws -> Radio.SessionSummary {
        try await get(Self.radio + "session/summary")
    }
}
