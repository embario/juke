package fm.juke.core.session

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.jukeCoreSessions by preferencesDataStore(name = "juke_core_session")

private val TOKEN_KEY = stringPreferencesKey("token")
private val USERNAME_KEY = stringPreferencesKey("username")

open class SessionStore(private val context: Context) {
    val snapshot: Flow<SessionSnapshot?> = context.jukeCoreSessions.data.map { prefs ->
        val token = prefs[TOKEN_KEY]
        val username = prefs[USERNAME_KEY]
        if (token == null || username == null) {
            null
        } else {
            SessionSnapshot(username, token)
        }
    }

    open suspend fun save(snapshot: SessionSnapshot) {
        context.jukeCoreSessions.edit { prefs ->
            prefs[TOKEN_KEY] = snapshot.token
            prefs[USERNAME_KEY] = snapshot.username
        }
    }

    open suspend fun clear() {
        context.jukeCoreSessions.edit { prefs ->
            prefs.remove(TOKEN_KEY)
            prefs.remove(USERNAME_KEY)
        }
    }

    suspend fun current(): SessionSnapshot? {
        val prefs = context.jukeCoreSessions.data.first()
        val token = prefs[TOKEN_KEY]
        val username = prefs[USERNAME_KEY]
        if (token == null || username == null) {
            return null
        }
        return SessionSnapshot(username, token)
    }
}
