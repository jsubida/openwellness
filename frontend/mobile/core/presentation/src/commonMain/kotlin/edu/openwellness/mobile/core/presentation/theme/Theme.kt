package edu.openwellness.mobile.core.presentation.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable

/** The single app theme. Wrap the whole UI tree (and previews) in this. */
@Composable
fun OpenWellnessTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) OpenWellnessDarkColors else OpenWellnessLightColors,
        typography = OpenWellnessTypography,
        shapes = OpenWellnessShapes,
        content = content,
    )
}
