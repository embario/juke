package fm.juke.core.testing

import fm.juke.core.session.SessionSnapshot
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

class FakeSessionStore(initialSnapshot: SessionSnapshot? = null) {
    private val snapshotFlow = MutableStateFlow(initialSnapshot)

    val snapshot: Flow<SessionSnapshot?> = snapshotFlow

    suspend fun save(snapshot: SessionSnapshot) {
        snapshotFlow.value = snapshot
    }

    suspend fun clear() {
        snapshotFlow.value = null
    }

    suspend fun current(): SessionSnapshot? = snapshotFlow.value
}
