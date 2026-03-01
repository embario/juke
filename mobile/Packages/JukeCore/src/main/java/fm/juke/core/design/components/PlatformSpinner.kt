package fm.juke.core.design.components

import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.StartOffset
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun PlatformSpinner(
    modifier: Modifier = Modifier,
    dotColor: Color = LocalJukePlatformPalette.current.Accent,
    dotSize: Dp = 10.dp,
    initialValue: Float = 1f,
    targetValue: Float = 0.5f,
    durationMillis: Int = 700,
    easing: Easing = LinearEasing,
    staggerMillis: Int = 150,
    minAlpha: Float = 0.3f,
) {
    val transition = rememberInfiniteTransition(label = "spinner")
    val dots = (0 until 3).map { index ->
        transition.animateFloat(
            initialValue = initialValue,
            targetValue = targetValue,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = durationMillis, easing = easing),
                repeatMode = RepeatMode.Reverse,
                initialStartOffset = StartOffset(offsetMillis = index * staggerMillis),
            ),
            label = "spinner-$index",
        )
    }
    val minScale = minOf(initialValue, targetValue)
    val scaleRange = kotlin.math.abs(targetValue - initialValue)
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        dots.forEach { animation ->
            val scale by animation
            Box(
                modifier = Modifier
                    .size(dotSize)
                    .graphicsLayer {
                        scaleX = scale
                        scaleY = scale
                        alpha = minAlpha + (scale - minScale) / scaleRange * (1f - minAlpha)
                    }
                    .drawBehind {
                        drawCircle(color = dotColor, radius = size.minDimension / 2)
                    },
            )
        }
    }
}
