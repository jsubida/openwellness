package edu.openwellness.mobile.feature.auth.presentation.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import androidx.navigation.compose.navigation
import edu.openwellness.mobile.feature.auth.presentation.landing.LandingScreen
import edu.openwellness.mobile.feature.auth.presentation.login.LoginRoot
import edu.openwellness.mobile.feature.auth.presentation.register.RegisterRoot

/**
 * The auth nested graph: Landing → Login / Register. Intra-feature navigation
 * uses [navController]; [onAuthenticated] is the cross-feature callback fired
 * after a successful verify (so this feature never imports the home route).
 */
fun NavGraphBuilder.authGraph(
    navController: NavController,
    onAuthenticated: () -> Unit,
) {
    navigation<AuthGraphRoute>(startDestination = LandingRoute) {
        composable<LandingRoute> {
            LandingScreen(
                onLoginClick = { navController.navigate(LoginRoute) },
                onRegisterClick = { navController.navigate(RegisterRoute) },
            )
        }
        composable<LoginRoute> {
            LoginRoot(onNavigateToHome = onAuthenticated)
        }
        composable<RegisterRoute> {
            RegisterRoot(onNavigateToHome = onAuthenticated)
        }
    }
}
