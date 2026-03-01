package fm.shotclock.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import fm.juke.core.design.components.PlatformStatusBanner
import fm.juke.core.design.components.StatusVariant

enum class SCStatusVariant { INFO, SUCCESS, WARNING, ERROR }

@Composable
fun ShotClockStatusBanner(
    message: String?,
    modifier: Modifier = Modifier,
    variant: SCStatusVariant = SCStatusVariant.INFO,
) {
    PlatformStatusBanner(
        message = message,
        modifier = modifier,
        variant = when (variant) {
            SCStatusVariant.INFO -> StatusVariant.INFO
            SCStatusVariant.SUCCESS -> StatusVariant.SUCCESS
            SCStatusVariant.WARNING -> StatusVariant.WARNING
            SCStatusVariant.ERROR -> StatusVariant.ERROR
        },
    )
}
