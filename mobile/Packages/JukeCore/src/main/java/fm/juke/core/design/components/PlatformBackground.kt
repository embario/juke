package fm.juke.core.design.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun PlatformBackground(
    modifier: Modifier = Modifier,
    accentGlowAlpha: Float = 0.2f,
    secondaryGlowAlpha: Float = 0.15f,
    content: @Composable () -> Unit,
) {
    val palette = LocalJukePlatformPalette.current
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                drawRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(palette.Background, palette.Panel),
                        startY = 0f,
                        endY = size.height,
                    ),
                )
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            palette.Accent.copy(alpha = accentGlowAlpha),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * 0.15f, size.height * 0.05f),
                        radius = 350f * (size.maxDimension / 800f),
                    ),
                )
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            palette.Secondary.copy(alpha = secondaryGlowAlpha),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * 0.85f, size.height * 0.95f),
                        radius = 400f * (size.maxDimension / 800f),
                    ),
                )
            },
    ) {
        content()
    }
}
