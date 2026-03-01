package fm.tunetrivia.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
fun CountdownRing(
    progress: Float,
    modifier: Modifier = Modifier,
    size: Dp = 200.dp,
    lineWidth: Dp = 20.dp,
) {
    fm.juke.core.design.components.CountdownRing(
        progress = progress,
        modifier = modifier,
        size = size,
        lineWidth = lineWidth,
    )
}
