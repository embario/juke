package com.juke.juke.core.design.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import com.juke.juke.core.design.JukePalette
import com.juke.juke.core.design.JukeTheme

@Composable
fun JukeBackground(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .drawBehind {
                drawRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(JukePalette.Background, JukePalette.PanelAlt),
                        startY = 0f,
                        endY = size.height,
                    ),
                )
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(JukePalette.IndigoGlow.copy(alpha = 0.6f), Color.Transparent),
                        center = Offset(size.width * 0.85f, size.height * 0.05f),
                        radius = size.maxDimension * 0.85f,
                    ),
                    alpha = 0.85f,
                )
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(JukePalette.Accent.copy(alpha = 0.35f), Color.Transparent),
                        center = Offset(size.width * 0.15f, size.height * -0.1f),
                        radius = size.maxDimension * 0.7f,
                    ),
                )
            },
    ) {
        content()
    }
}

@Preview(showBackground = true)
@Composable
private fun JukeBackgroundPreview() {
    JukeTheme {
        JukeBackground {}
    }
}
