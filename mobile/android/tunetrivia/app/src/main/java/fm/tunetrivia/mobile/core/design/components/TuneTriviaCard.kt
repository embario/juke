package fm.tunetrivia.mobile.core.design.components

import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformCard
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

@Composable
fun TuneTriviaCard(
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(20.dp),
    cornerRadius: Dp = 16.dp,
    accentColor: Color? = null,
    borderColor: Color = TuneTriviaPalette.Border,
    backgroundColors: List<Color> = listOf(
        TuneTriviaPalette.Panel.copy(alpha = 0.95f),
        TuneTriviaPalette.PanelAlt.copy(alpha = 0.90f),
    ),
    content: @Composable ColumnScope.() -> Unit,
) {
    PlatformCard(
        modifier = modifier,
        padding = padding,
        cornerRadius = cornerRadius,
        borderColor = borderColor,
        backgroundColors = backgroundColors,
        accentColor = accentColor,
        ambientShadowAlpha = 0.1f,
        spotShadowAlpha = 0.1f,
        content = content,
    )
}
