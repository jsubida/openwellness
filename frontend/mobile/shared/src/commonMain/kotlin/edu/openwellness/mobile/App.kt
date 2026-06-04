package edu.openwellness.mobile

import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import edu.openwellness.mobile.core.presentation.theme.OpenWellnessTheme
import edu.openwellness.mobile.feature.auth.domain.AuthRepository
import edu.openwellness.mobile.feature.auth.presentation.navigation.AuthGraphRoute
import edu.openwellness.mobile.feature.auth.presentation.navigation.authGraph
import edu.openwellness.mobile.home.HomePlaceholderScreen
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

@Composable
fun App() {
    OpenWellnessTheme {
        val navController = rememberNavController()
        NavHost(
            navController = navController,
            startDestination = AuthGraphRoute,
        ) {
            authGraph(
                navController = navController,
                onAuthenticated = {
                    navController.navigate(HomeRoute) {
                        popUpTo(AuthGraphRoute) { inclusive = true }
                    }
                },
            )
            composable<HomeRoute> {
                val authRepository = koinInject<AuthRepository>()
                val scope = rememberCoroutineScope()
                HomePlaceholderScreen(
                    onLogout = {
                        scope.launch {
                            // Best-effort server revoke; storage is cleared regardless.
                            authRepository.revokeCurrent()
                            navController.navigate(AuthGraphRoute) {
                                popUpTo(HomeRoute) { inclusive = true }
                            }
                        }
                    },
                )
            }
        }
    }
}
