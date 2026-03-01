package fm.tunetrivia.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import fm.juke.core.design.components.PlatformStatusBanner
import fm.juke.core.design.components.StatusVariant
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

enum class TuneTriviaStatusVariant { INFO, SUCCESS, WARNING, ERROR }

@Composable
fun TuneTriviaStatusBanner(
    message: String?,
    modifier: Modifier = Modifier,
    variant: TuneTriviaStatusVariant = TuneTriviaStatusVariant.INFO,
) {
    val accentOverride = when (variant) {
        TuneTriviaStatusVariant.INFO -> TuneTriviaPalette.Secondary
        else -> null
    }
    PlatformStatusBanner(
        message = message,
        modifier = modifier,
        variant = when (variant) {
            TuneTriviaStatusVariant.INFO -> StatusVariant.INFO
            TuneTriviaStatusVariant.SUCCESS -> StatusVariant.SUCCESS
            TuneTriviaStatusVariant.WARNING -> StatusVariant.WARNING
            TuneTriviaStatusVariant.ERROR -> StatusVariant.ERROR
        },
        accentOverride = accentOverride,
    )
}
