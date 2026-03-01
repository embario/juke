package fm.juke.mobile.core.design

import androidx.compose.ui.graphics.Color
import fm.juke.core.design.JukePlatformPalette

object JukePalette : JukePlatformPalette {
    override val Background = Color(0xFF030712)
    override val Panel = Color(0xFF090F1F)
    override val PanelAlt = Color(0xFF0F172A)
    override val Accent = Color(0xFFF97316)
    override val AccentSoft = Color(0xFFFB923C)
    val AccentDark = Color(0xFFEA580C)
    override val Secondary = AccentDark
    override val Text = Color(0xFFE2E8F0)
    override val Muted = Color(0xFF94A3B8)
    override val Border = Color(0x14FFFFFF)
    override val Success = Color(0xFF16A34A)
    override val Warning = Color(0xFFFACC15)
    override val Error = Color(0xFFEF4444)
    val IndigoGlow = Color(0xFF1E3A8A)
}
