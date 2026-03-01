package fm.juke.mobile.core.design.components

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformSpinner
import fm.juke.mobile.core.design.JukePalette

@Composable
fun JukeSpinner(
    modifier: Modifier = Modifier,
    dotColor: Color = JukePalette.Accent,
) {
    PlatformSpinner(
        modifier = modifier,
        dotColor = dotColor,
        dotSize = 12.dp,
        initialValue = 0.6f,
        targetValue = 1f,
        durationMillis = 800,
        easing = FastOutSlowInEasing,
        staggerMillis = 120,
        minAlpha = 0.4f,
    )
}
