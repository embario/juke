package fm.tunetrivia.mobile.core.design.components

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

enum class TuneTriviaButtonVariant { PRIMARY, SECONDARY, GHOST, LINK, DESTRUCTIVE }

@Composable
fun TuneTriviaButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    variant: TuneTriviaButtonVariant = TuneTriviaButtonVariant.PRIMARY,
    fillMaxWidth: Boolean = true,
    contentPadding: PaddingValues = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
    content: @Composable RowScope.() -> Unit,
) {
    val shape = RoundedCornerShape(999.dp)

    val backgroundColor = when (variant) {
        TuneTriviaButtonVariant.PRIMARY -> TuneTriviaPalette.Accent
        TuneTriviaButtonVariant.SECONDARY -> TuneTriviaPalette.Secondary
        TuneTriviaButtonVariant.GHOST -> TuneTriviaPalette.PanelAlt
        TuneTriviaButtonVariant.LINK -> Color.Transparent
        TuneTriviaButtonVariant.DESTRUCTIVE -> TuneTriviaPalette.Error
    }

    val contentColor = when (variant) {
        TuneTriviaButtonVariant.PRIMARY,
        TuneTriviaButtonVariant.DESTRUCTIVE,
        TuneTriviaButtonVariant.SECONDARY -> Color.White
        TuneTriviaButtonVariant.GHOST -> TuneTriviaPalette.Text
        TuneTriviaButtonVariant.LINK -> TuneTriviaPalette.Secondary
    }

    val border = when (variant) {
        TuneTriviaButtonVariant.GHOST -> BorderStroke(1.dp, TuneTriviaPalette.Border)
        else -> null
    }

    Surface(
        onClick = onClick,
        shape = shape,
        enabled = enabled,
        color = backgroundColor,
        border = border,
        modifier = modifier,
    ) {
        Box(
            modifier = Modifier
                .padding(contentPadding),
            contentAlignment = Alignment.Center,
        ) {
            CompositionLocalProvider(LocalContentColor provides contentColor) {
                ProvideTextStyle(
                    value = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                ) {
                    Row(
                        modifier = if (fillMaxWidth) Modifier.fillMaxWidth() else Modifier,
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
                        content = content,
                    )
                }
            }
        }
    }
}
