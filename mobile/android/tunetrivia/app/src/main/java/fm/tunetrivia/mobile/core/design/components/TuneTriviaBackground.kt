package fm.tunetrivia.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import fm.juke.core.design.components.PlatformBackground

@Composable
fun TuneTriviaBackground(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    PlatformBackground(modifier = modifier, content = content)
}
