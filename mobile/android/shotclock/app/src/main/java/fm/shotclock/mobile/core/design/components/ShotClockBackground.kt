package fm.shotclock.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import fm.juke.core.design.components.PlatformBackground

@Composable
fun ShotClockBackground(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    PlatformBackground(modifier = modifier, content = content)
}
