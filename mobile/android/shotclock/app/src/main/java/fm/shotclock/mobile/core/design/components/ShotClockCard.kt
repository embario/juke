package fm.shotclock.mobile.core.design.components

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformCard
import fm.shotclock.mobile.core.design.ShotClockPalette

@Composable
fun ShotClockCard(
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(20.dp),
    cornerRadius: Dp = 16.dp,
    borderColor: Color = ShotClockPalette.Border,
    backgroundColors: List<Color> = listOf(
        ShotClockPalette.Panel.copy(alpha = 0.95f),
        ShotClockPalette.PanelAlt.copy(alpha = 0.90f),
    ),
    content: @Composable ColumnScope.() -> Unit,
) {
    PlatformCard(
        modifier = modifier,
        padding = padding,
        cornerRadius = cornerRadius,
        borderColor = borderColor,
        backgroundColors = backgroundColors,
        content = content,
    )
}
