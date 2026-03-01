package fm.juke.mobile.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformChip
import fm.juke.mobile.core.design.JukePalette

@Composable
fun JukeChip(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    PlatformChip(
        label = label,
        selected = selected,
        modifier = modifier,
        accentColor = JukePalette.Accent,
        horizontalPadding = 18.dp,
        verticalPadding = 10.dp,
        onClick = onClick,
    )
}
