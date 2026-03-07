package com.juke.shotclock.core.design.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import fm.juke.core.design.components.PlatformSpinner
import com.juke.shotclock.core.design.ShotClockPalette

@Composable
fun ShotClockSpinner(
    modifier: Modifier = Modifier,
    dotColor: Color = ShotClockPalette.Accent,
) {
    PlatformSpinner(modifier = modifier, dotColor = dotColor)
}
