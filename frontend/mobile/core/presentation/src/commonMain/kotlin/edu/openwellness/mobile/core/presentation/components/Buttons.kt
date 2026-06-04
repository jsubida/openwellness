package edu.openwellness.mobile.core.presentation.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import edu.openwellness.mobile.core.presentation.theme.OpenWellnessTheme

private val ButtonMinHeight = 48.dp

/** High-emphasis filled action. */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier.heightIn(min = ButtonMinHeight),
    ) {
        Text(text = text, style = MaterialTheme.typography.labelLarge)
    }
}

/** Lower-emphasis outlined action. */
@Composable
fun SecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier.heightIn(min = ButtonMinHeight),
    ) {
        Text(text = text, style = MaterialTheme.typography.labelLarge)
    }
}

/**
 * Filled action that swaps its label for a spinner while [isLoading]; disabled
 * (non-clickable) for the duration so a slow request can't be double-submitted.
 */
@Composable
fun LoadingButton(
    text: String,
    isLoading: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !isLoading,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier.heightIn(min = ButtonMinHeight),
    ) {
        if (isLoading) {
            CircularProgressIndicator(
                strokeWidth = 2.dp,
                color = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier.size(20.dp),
            )
        } else {
            Text(text = text, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Preview
@Composable
private fun ButtonsPreview() {
    OpenWellnessTheme {
        PrimaryButton(text = "Send code", onClick = {}, modifier = Modifier.fillMaxWidth())
    }
}

@Preview
@Composable
private fun LoadingButtonPreview() {
    OpenWellnessTheme {
        LoadingButton(text = "Verify", isLoading = true, onClick = {}, modifier = Modifier.fillMaxWidth())
    }
}
