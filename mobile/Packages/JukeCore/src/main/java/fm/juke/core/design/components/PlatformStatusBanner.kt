package fm.juke.core.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

enum class StatusVariant { INFO, SUCCESS, WARNING, ERROR }

@Composable
fun PlatformStatusBanner(
    message: String?,
    modifier: Modifier = Modifier,
    variant: StatusVariant = StatusVariant.INFO,
    accentOverride: Color? = null,
    cornerRadius: Dp = 14.dp,
    dotSize: Dp = 10.dp,
    dotShadow: Boolean = true,
) {
    if (message.isNullOrBlank()) return
    val palette = LocalJukePlatformPalette.current
    val accent = accentOverride ?: when (variant) {
        StatusVariant.INFO -> palette.Accent
        StatusVariant.SUCCESS -> palette.Success
        StatusVariant.WARNING -> palette.Warning
        StatusVariant.ERROR -> palette.Error
    }
    val bgAlpha = when (variant) {
        StatusVariant.INFO -> 0.12f
        StatusVariant.SUCCESS -> 0.18f
        StatusVariant.WARNING -> 0.18f
        StatusVariant.ERROR -> 0.18f
    }
    val shape = RoundedCornerShape(cornerRadius)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(color = accent.copy(alpha = bgAlpha), shape = shape)
            .border(width = 1.dp, color = accent.copy(alpha = 0.3f), shape = shape)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val dotModifier = if (dotShadow) {
            Modifier
                .size(dotSize)
                .shadow(6.dp, CircleShape, ambientColor = accent.copy(alpha = 0.6f))
                .background(accent, CircleShape)
        } else {
            Modifier
                .size(dotSize)
                .background(accent, CircleShape)
        }
        Box(modifier = dotModifier)
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = palette.Text,
        )
    }
}
