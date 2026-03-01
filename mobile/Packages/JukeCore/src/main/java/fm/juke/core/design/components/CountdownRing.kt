package fm.juke.core.design.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun CountdownRing(
    progress: Float,
    modifier: Modifier = Modifier,
    size: Dp = 200.dp,
    lineWidth: Dp = 20.dp,
    trackColor: Color = LocalJukePlatformPalette.current.PanelAlt,
    glowColor: Color = LocalJukePlatformPalette.current.Secondary.copy(alpha = 0.3f),
    gradientColors: List<Color> = listOf(
        LocalJukePlatformPalette.current.Secondary,
        LocalJukePlatformPalette.current.Accent,
        LocalJukePlatformPalette.current.Secondary,
    ),
) {
    Canvas(modifier = modifier.size(size)) {
        val strokeWidthPx = lineWidth.toPx()
        val inset = strokeWidthPx / 2
        val arcSize = Size(this.size.width - strokeWidthPx, this.size.height - strokeWidthPx)
        val topLeft = Offset(inset, inset)

        drawArc(
            color = trackColor,
            startAngle = 0f,
            sweepAngle = 360f,
            useCenter = false,
            topLeft = topLeft,
            size = arcSize,
            style = Stroke(width = strokeWidthPx, cap = StrokeCap.Round),
        )

        if (progress > 0f) {
            drawArc(
                color = glowColor,
                startAngle = -90f,
                sweepAngle = 360f * progress,
                useCenter = false,
                topLeft = topLeft,
                size = arcSize,
                style = Stroke(width = strokeWidthPx + 8.dp.toPx(), cap = StrokeCap.Round),
            )
        }

        if (progress > 0f) {
            drawArc(
                brush = Brush.sweepGradient(colors = gradientColors),
                startAngle = -90f,
                sweepAngle = 360f * progress,
                useCenter = false,
                topLeft = topLeft,
                size = arcSize,
                style = Stroke(width = strokeWidthPx, cap = StrokeCap.Round),
            )
        }
    }
}
