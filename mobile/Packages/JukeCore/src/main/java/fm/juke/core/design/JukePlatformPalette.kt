package fm.juke.core.design

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

interface JukePlatformPalette {
    val Background: Color
    val Panel: Color
    val PanelAlt: Color
    val Accent: Color
    val AccentSoft: Color
    val Secondary: Color
    val Text: Color
    val Muted: Color
    val Border: Color
    val Success: Color
    val Warning: Color
    val Error: Color
}

val LocalJukePlatformPalette = staticCompositionLocalOf<JukePlatformPalette> {
    error("No JukePlatformPalette provided. Wrap your theme with CompositionLocalProvider.")
}
