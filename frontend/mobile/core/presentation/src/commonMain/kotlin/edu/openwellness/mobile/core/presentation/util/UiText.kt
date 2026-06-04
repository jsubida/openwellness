package edu.openwellness.mobile.core.presentation.util

import androidx.compose.runtime.Composable
import org.jetbrains.compose.resources.StringResource
import org.jetbrains.compose.resources.stringResource

/**
 * Text that the UI can render but the lower layers can produce without a
 * `Context`. CMP-adapted: a [StringResourceText] wraps a Compose-resources
 * [StringResource] (not an Android `Int` id), resolved in composition via
 * [asString].
 */
sealed interface UiText {
    data class DynamicString(val value: String) : UiText

    data class StringResourceText(
        val resource: StringResource,
        val args: List<Any> = emptyList(),
    ) : UiText

    @Composable
    fun asString(): String = when (this) {
        is DynamicString -> value
        is StringResourceText -> stringResource(resource, *args.toTypedArray())
    }
}
