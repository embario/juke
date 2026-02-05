package fm.tunetrivia.mobile.core.design.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

@Composable
fun TuneTriviaBackground(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                // Layer 1: Vertical gradient from Background to Panel
                drawRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(TuneTriviaPalette.Background, TuneTriviaPalette.Panel),
                        startY = 0f,
                        endY = size.height,
                    ),
                )
                // Layer 2: Accent glow at top-leading, radius 350
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            TuneTriviaPalette.Accent.copy(alpha = 0.2f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * 0.15f, size.height * 0.05f),
                        radius = 350f * (size.maxDimension / 800f),
                    ),
                )
                // Layer 3: Secondary glow at bottom-trailing, radius 400
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            TuneTriviaPalette.Secondary.copy(alpha = 0.15f),
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
