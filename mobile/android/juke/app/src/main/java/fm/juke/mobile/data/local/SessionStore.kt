package fm.juke.mobile.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import fm.juke.core.session.SessionSnapshot
import fm.juke.core.session.SessionStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.jukeOnboarding by preferencesDataStore(name = "juke_onboarding")

private val ONBOARDING_COMPLETED_AT_KEY = stringPreferencesKey("onboarding_completed_at")

class JukeSessionStore(private val context: Context) : SessionStore(context) {

    val onboardingCompleted: Flow<Boolean?> = context.jukeOnboarding.data.map { prefs ->
        val value = prefs[ONBOARDING_COMPLETED_AT_KEY]
        value?.isNotBlank()
    }

    override suspend fun save(snapshot: SessionSnapshot) {
        super.save(snapshot)
        context.jukeOnboarding.edit { prefs ->
            prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
        }
    }

    override suspend fun clear() {
        super.clear()
        context.jukeOnboarding.edit { prefs ->
            prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
        }
    }

    suspend fun setOnboardingCompletedAt(value: String?) {
        context.jukeOnboarding.edit { prefs ->
            if (value == null) {
                prefs.remove(ONBOARDING_COMPLETED_AT_KEY)
            } else {
                prefs[ONBOARDING_COMPLETED_AT_KEY] = value
            }
        }
    }
}
