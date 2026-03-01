package fm.tunetrivia.mobile.core.design

import androidx.compose.ui.graphics.Color
import fm.juke.core.design.JukePlatformPalette

object TuneTriviaPalette : JukePlatformPalette {
    override val Background = Color(0xFFFAF8F5)
    override val Panel = Color(0xFFFFF5EB)
    override val PanelAlt = Color(0xFFFFFFFF)
    override val Accent = Color(0xFFFF6B6B)
    override val AccentSoft = Color(0xFFFF8E8E)
    override val Secondary = Color(0xFF4ECDC4)
    val Tertiary = Color(0xFF9B5DE5)
    val Highlight = Color(0xFFFFE66D)
    override val Text = Color(0xFF2D3436)
    override val Muted = Color(0xFF636E72)
    override val Border = Color(0x0F000000)          // black @ 6%
    override val Success = Color(0xFF4ECDC4)
    override val Warning = Color(0xFFFFE66D)
    override val Error = Color(0xFFFF6B6B)
}
