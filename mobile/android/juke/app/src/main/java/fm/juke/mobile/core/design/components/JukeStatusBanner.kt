package fm.juke.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformStatusBanner
import fm.juke.core.design.components.StatusVariant

enum class JukeStatusVariant { INFO, SUCCESS, WARNING, ERROR }

@Composable
fun JukeStatusBanner(
    message: String?,
    modifier: Modifier = Modifier,
    variant: JukeStatusVariant = JukeStatusVariant.INFO,
) {
    PlatformStatusBanner(
        message = message,
        modifier = modifier,
        variant = when (variant) {
            JukeStatusVariant.INFO -> StatusVariant.INFO
            JukeStatusVariant.SUCCESS -> StatusVariant.SUCCESS
            JukeStatusVariant.WARNING -> StatusVariant.WARNING
            JukeStatusVariant.ERROR -> StatusVariant.ERROR
        },
        cornerRadius = 18.dp,
        dotSize = 12.dp,
        dotShadow = false,
    )
}
