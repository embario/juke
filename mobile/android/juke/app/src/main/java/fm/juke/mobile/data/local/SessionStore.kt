package fm.juke.mobile.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "juke_session")

private val TOKEN_KEY = stringPreferencesKey("token")
private val USERNAME_KEY = stringPreferencesKey("username")
private val ONBOARDING_COMPLETED_AT_KEY = stringPreferencesKey("onboarding_completed_at")

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

    val onboardingCompleted: Flow<Boolean?> = context.dataStore.data.map { prefs ->
        val value = prefs[ONBOARDING_COMPLETED_AT_KEY]
        value?.isNotBlank()
    }

    suspend fun save(snapshot: SessionSnapshot) {
        context.dataStore.edit { prefs ->
            prefs[TOKEN_KEY] = snapshot.token
            prefs[USERNAME_KEY] = snapshot.username
            prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
        }
    }

    suspend fun clear() {
        context.dataStore.edit { prefs ->
            prefs.remove(TOKEN_KEY)
            prefs.remove(USERNAME_KEY)
            prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
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

    suspend fun setOnboardingCompletedAt(value: String?) {
        context.dataStore.edit { prefs ->
            if (value == null) {
                prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
            } else {
                prefs[ONBOARDING_COMPLETED_AT_KEY] = value
            }
        }
    }
}
