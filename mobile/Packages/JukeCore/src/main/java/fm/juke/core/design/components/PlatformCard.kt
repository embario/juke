package fm.juke.core.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun PlatformCard(
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(20.dp),
    cornerRadius: Dp = 16.dp,
    borderColor: Color = LocalJukePlatformPalette.current.Border,
    borderWidth: Dp = 1.dp,
    elevation: Dp = 20.dp,
    ambientShadowAlpha: Float = 0.4f,
    spotShadowAlpha: Float = 0.4f,
    backgroundColors: List<Color> = listOf(
        LocalJukePlatformPalette.current.Panel.copy(alpha = 0.95f),
        LocalJukePlatformPalette.current.PanelAlt.copy(alpha = 0.90f),
    ),
    accentColor: Color? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(cornerRadius)
    val gradient = Brush.linearGradient(
        colors = backgroundColors,
        start = Offset(0f, 0f),
        end = Offset(600f, 900f),
    )
    Box(
        modifier = modifier
            .shadow(
                elevation = elevation,
                shape = shape,
                clip = false,
                ambientColor = Color.Black.copy(alpha = ambientShadowAlpha),
                spotColor = Color.Black.copy(alpha = spotShadowAlpha),
            )
            .clip(shape)
            .background(gradient)
            .border(width = borderWidth, color = borderColor, shape = shape),
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            if (accentColor != null) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 4.dp)
                        .background(
                            color = accentColor,
                            shape = RoundedCornerShape(
                                topStart = cornerRadius,
                                topEnd = cornerRadius,
                                bottomStart = 0.dp,
                                bottomEnd = 0.dp,
                            ),
                        )
                        .padding(vertical = 3.dp),
                )
            }
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(padding),
                horizontalAlignment = Alignment.Start,
                content = content,
            )
        }
    }
}
