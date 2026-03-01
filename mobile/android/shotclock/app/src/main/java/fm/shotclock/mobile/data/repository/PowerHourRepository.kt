package fm.shotclock.mobile.data.repository

import fm.juke.core.session.SessionStore
import fm.shotclock.mobile.data.network.ShotClockApiService
import fm.shotclock.mobile.data.network.dto.CreateSessionRequest
import fm.shotclock.mobile.data.network.dto.JoinSessionRequest
import fm.shotclock.mobile.data.network.dto.ImportSessionTracksRequest
import fm.shotclock.mobile.model.PowerHourSession
import fm.shotclock.mobile.model.SessionPlayer
import fm.shotclock.mobile.model.SessionTrack
import fm.shotclock.mobile.model.toDomain

class PowerHourRepository(
    private val api: ShotClockApiService,
    private val store: SessionStore,
) {
    suspend fun createSession(body: CreateSessionRequest): Result<PowerHourSession> = runCatching {
        api.createSession(requireToken(), body).toDomain()
    }

    suspend fun listSessions(): Result<List<PowerHourSession>> = runCatching {
        api.listSessions(requireToken()).map { it.toDomain() }
    }

    suspend fun joinSession(inviteCode: String): Result<PowerHourSession> = runCatching {
        api.joinSession(requireToken(), JoinSessionRequest(inviteCode)).toDomain()
    }

    suspend fun getSession(sessionId: String): Result<PowerHourSession> = runCatching {
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun deleteSession(sessionId: String): Result<Unit> = runCatching {
        api.deleteSession(requireToken(), sessionId)
    }

    suspend fun listPlayers(sessionId: String): Result<List<SessionPlayer>> = runCatching {
        api.listPlayers(requireToken(), sessionId).map { it.toDomain() }
    }

    suspend fun listTracks(sessionId: String): Result<List<SessionTrack>> = runCatching {
        api.listTracks(requireToken(), sessionId).map { it.toDomain() }
    }

    suspend fun addTrack(
        sessionId: String,
        trackId: Int,
        startOffsetMs: Int = 0,
    ): Result<SessionTrack> = runCatching {
        api.addTrack(
            token = requireToken(),
            sessionId = sessionId,
            body = fm.shotclock.mobile.data.network.dto.AddTrackRequest(
                trackId = trackId,
                startOffsetMs = startOffsetMs,
            ),
        ).toDomain()
    }

    suspend fun removeTrack(sessionId: String, trackId: String): Result<Unit> = runCatching {
        api.removeTrack(requireToken(), sessionId, trackId)
    }

    suspend fun startSession(sessionId: String): Result<PowerHourSession> = runCatching {
        api.startSession(requireToken(), sessionId)
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun pauseSession(sessionId: String): Result<PowerHourSession> = runCatching {
        api.pauseSession(requireToken(), sessionId)
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun resumeSession(sessionId: String): Result<PowerHourSession> = runCatching {
        api.resumeSession(requireToken(), sessionId)
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun endSession(sessionId: String): Result<PowerHourSession> = runCatching {
        api.endSession(requireToken(), sessionId)
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun nextTrack(sessionId: String): Result<PowerHourSession> = runCatching {
        api.nextTrack(requireToken(), sessionId)
        api.getSession(requireToken(), sessionId).toDomain()
    }

    suspend fun importSessionTracks(
        sessionId: String,
        sourceSessionId: String,
    ): Result<List<SessionTrack>> = runCatching {
        val token = requireToken()
        val existingTrackIds = api.listTracks(token, sessionId).map { it.id }.toSet()
        api.importSessionTracks(token, sessionId, ImportSessionTracksRequest(sourceSessionId))
        api.listTracks(token, sessionId)
            .filterNot { it.id in existingTrackIds }
            .map { it.toDomain() }
    }

    private suspend fun requireToken(): String {
        val session = store.current()
        checkNotNull(session) { "Not authenticated" }
        return "Token ${session.token}"
    }
}
