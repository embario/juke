package fm.juke.core.design.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun PlatformChip(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    accentColor: Color = LocalJukePlatformPalette.current.Accent,
    horizontalPadding: Dp = 16.dp,
    verticalPadding: Dp = 8.dp,
    onClick: () -> Unit,
) {
    val palette = LocalJukePlatformPalette.current
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = if (selected) accentColor.copy(alpha = 0.2f) else Color.Transparent,
        contentColor = if (selected) palette.Text else palette.Muted,
        border = BorderStroke(1.dp, if (selected) accentColor else palette.Border),
        modifier = modifier,
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = horizontalPadding, vertical = verticalPadding),
            style = MaterialTheme.typography.bodyMedium.copy(
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            ),
        )
    }
}
