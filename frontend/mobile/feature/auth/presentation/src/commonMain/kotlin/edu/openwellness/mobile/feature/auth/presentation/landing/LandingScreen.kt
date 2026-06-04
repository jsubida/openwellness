package edu.openwellness.mobile.feature.auth.presentation.landing

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import edu.openwellness.mobile.core.presentation.components.PrimaryButton
import edu.openwellness.mobile.core.presentation.components.SecondaryButton
import edu.openwellness.mobile.core.presentation.theme.OpenWellnessTheme
import edu.openwellness.mobile.feature.auth.presentation.resources.Res
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_brand_name
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_landing_login
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_landing_register
import edu.openwellness.mobile.feature.auth.presentation.resources.auth_landing_subtitle
import org.jetbrains.compose.resources.stringResource

/** Static entry screen — no ViewModel. Hero brand + log in / create account. */
@Composable
fun LandingScreen(
    onLoginClick: () -> Unit,
    onRegisterClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .safeContentPadding()
            .padding(horizontal = 24.dp, vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.weight(1f))
        Text(
            text = stringResource(Res.string.auth_brand_name),
            style = MaterialTheme.typography.displayMedium,
            color = MaterialTheme.colorScheme.primary,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.padding(8.dp))
        Text(
            text = stringResource(Res.string.auth_landing_subtitle),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.weight(1f))
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PrimaryButton(
                text = stringResource(Res.string.auth_landing_login),
                onClick = onLoginClick,
                modifier = Modifier.fillMaxWidth(),
            )
            SecondaryButton(
                text = stringResource(Res.string.auth_landing_register),
                onClick = onRegisterClick,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Preview
@Composable
private fun LandingScreenPreview() {
    OpenWellnessTheme {
        LandingScreen(onLoginClick = {}, onRegisterClick = {})
    }
}
