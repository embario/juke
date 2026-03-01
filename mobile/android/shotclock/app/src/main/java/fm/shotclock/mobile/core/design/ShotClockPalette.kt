package fm.shotclock.mobile.core.design

import androidx.compose.ui.graphics.Color
import fm.juke.core.design.JukePlatformPalette

object ShotClockPalette : JukePlatformPalette {
    override val Background = Color(0xFF0A0118)
    override val Panel = Color(0xFF140B2E)
    override val PanelAlt = Color(0xFF1E1145)
    override val Accent = Color(0xFFE11D89)
    override val AccentSoft = Color(0xFFF472B6)
    override val Secondary = Color(0xFF06B6D4)
    override val Text = Color(0xFFF8FAFC)
    override val Muted = Color(0xFF94A3B8)
    override val Border = Color(0x0FFFFFFF)          // white @ 6%
    override val Success = Color(0xFF10B981)
    override val Warning = Color(0xFFFBBF24)
    override val Error = Color(0xFFF43F5E)
}
