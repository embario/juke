package fm.tunetrivia.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import fm.juke.core.design.components.PlatformSpinner
import fm.tunetrivia.mobile.core.design.TuneTriviaPalette

@Composable
fun TuneTriviaSpinner(
    modifier: Modifier = Modifier,
    dotColor: Color = TuneTriviaPalette.Accent,
) {
    PlatformSpinner(modifier = modifier, dotColor = dotColor)
}
