package edu.openwellness.mobile.core.data.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.first

/** [AuthTokenStorage] backed by a multiplatform `DataStore<Preferences>`. */
class DataStoreAuthTokenStorage(
    private val dataStore: DataStore<Preferences>,
) : AuthTokenStorage {

    override suspend fun getAccessToken(): String? =
        dataStore.data.first()[ACCESS_TOKEN_KEY]

    override suspend fun getRefreshToken(): String? =
        dataStore.data.first()[REFRESH_TOKEN_KEY]

    override suspend fun saveTokens(accessToken: String, refreshToken: String) {
        dataStore.edit { prefs ->
            prefs[ACCESS_TOKEN_KEY] = accessToken
            prefs[REFRESH_TOKEN_KEY] = refreshToken
        }
    }

    override suspend fun clear() {
        dataStore.edit { prefs ->
            prefs.remove(ACCESS_TOKEN_KEY)
            prefs.remove(REFRESH_TOKEN_KEY)
        }
    }

    private companion object {
        val ACCESS_TOKEN_KEY = stringPreferencesKey("access_token")
        val REFRESH_TOKEN_KEY = stringPreferencesKey("refresh_token")
    }
}
