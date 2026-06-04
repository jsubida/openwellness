package edu.openwellness.mobile.core.presentation.components

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import edu.openwellness.mobile.core.presentation.theme.OpenWellnessTheme

/**
 * Six-cell OTP entry backed by a single hidden [BasicTextField]. Input is
 * digit-filtered and capped at [length]; [onFilled] fires once the last digit
 * lands. The cells are pure presentation — all state is the caller's [code].
 */
@Composable
fun OtpInputField(
    code: String,
    onCodeChange: (String) -> Unit,
    contentDescription: String,
    modifier: Modifier = Modifier,
    length: Int = 6,
    isError: Boolean = false,
    enabled: Boolean = true,
    onFilled: () -> Unit = {},
) {
    BasicTextField(
        value = code,
        onValueChange = { new ->
            val filtered = new.filter(Char::isDigit).take(length)
            if (filtered != code) onCodeChange(filtered)
            if (filtered.length == length) onFilled()
        },
        enabled = enabled,
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.NumberPassword,
            imeAction = ImeAction.Done,
        ),
        keyboardActions = KeyboardActions(onDone = { if (code.length == length) onFilled() }),
        modifier = modifier.semantics { this.contentDescription = contentDescription },
        decorationBox = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                repeat(length) { index ->
                    val char = code.getOrNull(index)?.toString().orEmpty()
                    val borderColor = when {
                        isError -> MaterialTheme.colorScheme.error
                        char.isNotEmpty() -> MaterialTheme.colorScheme.primary
                        else -> MaterialTheme.colorScheme.outline
                    }
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier
                            .size(width = 44.dp, height = 52.dp)
                            .border(
                                width = if (isError) 2.dp else 1.dp,
                                color = borderColor,
                                shape = MaterialTheme.shapes.small,
                            ),
                    ) {
                        Text(
                            text = char,
                            style = MaterialTheme.typography.headlineSmall,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                    }
                }
            }
        },
    )
}

@Preview
@Composable
private fun OtpInputFieldPreview() {
    OpenWellnessTheme {
        OtpInputField(
            code = "1234",
            onCodeChange = {},
            contentDescription = "Verification code",
        )
    }
}
