package fm.tunetrivia.mobile.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "tunetrivia_session")

private val TOKEN_KEY = stringPreferencesKey("token")
private val USERNAME_KEY = stringPreferencesKey("username")

class SessionStore(private val context: Context) {
    val snapshot: Flow<SessionSnapshot?> = context.dataStore.data.map { prefs ->
        val token = prefs[TOKEN_KEY]
        val username = prefs[USERNAME_KEY]
        if (token == null || username == null) {
            null
        } else {
            SessionSnapshot(username, token)
        }
    }

    suspend fun save(snapshot: SessionSnapshot) {
        context.dataStore.edit { prefs ->
            prefs[TOKEN_KEY] = snapshot.token
            prefs[USERNAME_KEY] = snapshot.username
        }
    }

    suspend fun clear() {
        context.dataStore.edit { prefs ->
            prefs.remove(TOKEN_KEY)
            prefs.remove(USERNAME_KEY)
        }
    }

    suspend fun current(): SessionSnapshot? {
        val prefs = context.dataStore.data.first()
        val token = prefs[TOKEN_KEY]
        val username = prefs[USERNAME_KEY]
        if (token == null || username == null) {
            return null
        }
        return SessionSnapshot(username, token)
    }
}
