package fm.shotclock.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import fm.juke.core.design.components.PlatformSpinner
import fm.shotclock.mobile.core.design.ShotClockPalette

@Composable
fun ShotClockSpinner(
    modifier: Modifier = Modifier,
    dotColor: Color = ShotClockPalette.Accent,
) {
    PlatformSpinner(modifier = modifier, dotColor = dotColor)
}
