package com.juke.shotclock.core.design.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.juke.shotclock.core.design.ShotClockPalette

enum class SCButtonVariant { PRIMARY, SECONDARY, GHOST, DESTRUCTIVE }

@Composable
fun ShotClockButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    variant: SCButtonVariant = SCButtonVariant.PRIMARY,
    contentPadding: PaddingValues = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
    content: @Composable RowScope.() -> Unit,
) {
    val shape = RoundedCornerShape(16.dp)
    val density = androidx.compose.ui.platform.LocalDensity.current

    val brush = when (variant) {
        SCButtonVariant.PRIMARY -> Brush.linearGradient(
            colors = listOf(ShotClockPalette.Accent, ShotClockPalette.AccentSoft),
            start = Offset.Zero,
            end = Offset(density.run { 240.dp.toPx() }, 0f),
        )
        SCButtonVariant.SECONDARY -> Brush.linearGradient(
            colors = listOf(ShotClockPalette.Secondary, ShotClockPalette.Secondary),
        )
        SCButtonVariant.GHOST -> Brush.linearGradient(
            colors = listOf(
                ShotClockPalette.PanelAlt.copy(alpha = 0.5f),
                ShotClockPalette.PanelAlt.copy(alpha = 0.5f),
            ),
        )
        SCButtonVariant.DESTRUCTIVE -> Brush.linearGradient(
            colors = listOf(ShotClockPalette.Error, ShotClockPalette.Error),
        )
    }

    val contentColor = when (variant) {
        SCButtonVariant.PRIMARY -> Color.White
        SCButtonVariant.SECONDARY -> ShotClockPalette.Background
        SCButtonVariant.GHOST -> ShotClockPalette.Text
        SCButtonVariant.DESTRUCTIVE -> Color.White
    }

    val border = when (variant) {
        SCButtonVariant.GHOST -> BorderStroke(1.dp, ShotClockPalette.Border)
        else -> null
    }

    Surface(
        onClick = onClick,
        shape = shape,
        enabled = enabled,
        color = Color.Transparent,
        border = border,
        modifier = modifier,
    ) {
        Box(
            modifier = Modifier
                .background(brush = brush, shape = shape)
                .padding(contentPadding),
            contentAlignment = Alignment.Center,
        ) {
            CompositionLocalProvider(LocalContentColor provides contentColor) {
                ProvideTextStyle(
                    value = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.SemiBold),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
                        content = content,
                    )
                }
            }
        }
    }
}
