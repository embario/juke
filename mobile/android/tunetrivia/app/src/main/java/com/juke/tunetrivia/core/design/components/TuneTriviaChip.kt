package com.juke.tunetrivia.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import fm.juke.core.design.components.PlatformChip
import com.juke.tunetrivia.core.design.TuneTriviaPalette

@Composable
fun TuneTriviaChip(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    accentColor: Color = TuneTriviaPalette.Accent,
    onClick: () -> Unit,
) {
    PlatformChip(
        label = label,
        selected = selected,
        modifier = modifier,
        accentColor = accentColor,
        onClick = onClick,
    )
}
