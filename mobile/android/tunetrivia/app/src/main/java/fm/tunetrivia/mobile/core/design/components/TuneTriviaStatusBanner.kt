package fm.tunetrivia.mobile.core.design.components

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
import androidx.compose.ui.unit.dp
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

enum class TuneTriviaStatusVariant { INFO, SUCCESS, WARNING, ERROR }

@Composable
fun TuneTriviaStatusBanner(
    message: String?,
    modifier: Modifier = Modifier,
    variant: TuneTriviaStatusVariant = TuneTriviaStatusVariant.INFO,
) {
    if (message.isNullOrBlank()) return
    val accent = when (variant) {
        TuneTriviaStatusVariant.INFO -> TuneTriviaPalette.Secondary
        TuneTriviaStatusVariant.SUCCESS -> TuneTriviaPalette.Success
        TuneTriviaStatusVariant.WARNING -> TuneTriviaPalette.Warning
        TuneTriviaStatusVariant.ERROR -> TuneTriviaPalette.Error
    }
    val bgAlpha = when (variant) {
        TuneTriviaStatusVariant.INFO -> 0.15f
        TuneTriviaStatusVariant.SUCCESS -> 0.18f
        TuneTriviaStatusVariant.WARNING -> 0.2f
        TuneTriviaStatusVariant.ERROR -> 0.18f
    }
    val shape = RoundedCornerShape(14.dp)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(color = accent.copy(alpha = bgAlpha), shape = shape)
            .border(width = 1.dp, color = accent.copy(alpha = 0.3f), shape = shape)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .shadow(6.dp, CircleShape, ambientColor = accent.copy(alpha = 0.6f))
                .background(accent, CircleShape),
        )
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = TuneTriviaPalette.Text,
        )
    }
}
