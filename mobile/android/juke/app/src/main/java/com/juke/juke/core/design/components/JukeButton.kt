package com.juke.juke.core.design.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
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
import com.juke.juke.core.design.JukePalette

enum class JukeButtonVariant { PRIMARY, GHOST, LINK }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JukeButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    variant: JukeButtonVariant = JukeButtonVariant.PRIMARY,
    contentPadding: PaddingValues = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
    content: @Composable RowScope.() -> Unit,
) {
    val shape = RoundedCornerShape(26.dp)
    when (variant) {
        JukeButtonVariant.LINK -> {
            TextButton(
                onClick = onClick,
                enabled = enabled,
                modifier = modifier,
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
            ) {
                CompositionLocalProvider(LocalContentColor provides JukePalette.Accent) {
                    ProvideTextStyle(
                        value = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            content = content,
                        )
                    }
                }
            }
        }
        else -> {
            val density = androidx.compose.ui.platform.LocalDensity.current
            val brush = when (variant) {
                JukeButtonVariant.PRIMARY -> Brush.linearGradient(
                    colors = listOf(JukePalette.Accent, JukePalette.AccentSoft, JukePalette.AccentDark),
                    start = Offset.Zero,
                    end = Offset(density.run { 240.dp.toPx() }, density.run { 120.dp.toPx() }),
                )
                JukeButtonVariant.GHOST -> Brush.linearGradient(
                    colors = listOf(
                        Color.Transparent,
                        Color.Transparent,
                    ),
                    start = Offset.Zero,
                    end = Offset(density.run { 200.dp.toPx() }, density.run { 80.dp.toPx() }),
                )
                else -> Brush.linearGradient(listOf(JukePalette.Accent, JukePalette.AccentSoft))
            }
            val contentColor = when (variant) {
                JukeButtonVariant.PRIMARY -> JukePalette.PanelAlt
                JukeButtonVariant.GHOST -> JukePalette.Text
                else -> JukePalette.Accent
            }
            Surface(
                onClick = onClick,
                shape = shape,
                enabled = enabled,
                color = Color.Transparent,
                shadowElevation = if (variant == JukeButtonVariant.PRIMARY && enabled) 12.dp else 0.dp,
                border = when (variant) {
                    JukeButtonVariant.GHOST -> BorderStroke(1.3.dp, JukePalette.Accent)
                    else -> null
                },
                modifier = modifier,
            ) {
                val backgroundModifier = if (variant == JukeButtonVariant.GHOST) {
                    Modifier
                } else {
                    Modifier.background(brush = brush, shape = shape)
                }
                Box(
                    modifier = backgroundModifier
                        .padding(contentPadding),
                    contentAlignment = Alignment.Center,
                ) {
                    CompositionLocalProvider(LocalContentColor provides contentColor) {
                        ProvideTextStyle(
                            value = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                content = content,
                            )
                        }
                    }
                }
            }
        }
    }
}
