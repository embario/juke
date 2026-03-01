package fm.juke.mobile.core.design.components

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformCard
import fm.juke.mobile.core.design.JukePalette

@Composable
fun JukeCard(
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(24.dp),
    cornerRadius: Dp = 28.dp,
    borderColor: Color = JukePalette.Border,
    backgroundColors: List<Color> = listOf(
        JukePalette.Panel.copy(alpha = 0.95f),
        JukePalette.PanelAlt.copy(alpha = 0.92f),
    ),
    content: @Composable ColumnScope.() -> Unit,
) {
    PlatformCard(
        modifier = modifier,
        padding = padding,
        cornerRadius = cornerRadius,
        borderColor = borderColor,
        borderWidth = 1.2.dp,
        elevation = 45.dp,
        ambientShadowAlpha = 0.35f,
        spotShadowAlpha = 0.5f,
        backgroundColors = backgroundColors,
        content = content,
    )
}
