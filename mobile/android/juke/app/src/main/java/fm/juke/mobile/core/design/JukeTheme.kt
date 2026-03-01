package fm.juke.mobile.core.design

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fm.juke.core.design.LocalJukePlatformPalette

private val DarkColors = darkColorScheme(
    primary = JukePalette.Accent,
    onPrimary = JukePalette.PanelAlt,
    secondary = JukePalette.AccentSoft,
    onSecondary = JukePalette.PanelAlt,
    tertiary = JukePalette.Success,
    onTertiary = JukePalette.PanelAlt,
    background = JukePalette.Background,
    onBackground = JukePalette.Text,
    surface = JukePalette.Panel,
    onSurface = JukePalette.Text,
    surfaceVariant = JukePalette.PanelAlt,
    onSurfaceVariant = JukePalette.Text,
    error = JukePalette.Error,
    onError = JukePalette.Text,
)

private val LightColors = lightColorScheme(
    primary = JukePalette.Accent,
    onPrimary = JukePalette.PanelAlt,
    secondary = JukePalette.AccentSoft,
    onSecondary = JukePalette.PanelAlt,
    tertiary = JukePalette.Success,
    onTertiary = JukePalette.PanelAlt,
    background = JukePalette.Text,
    onBackground = JukePalette.PanelAlt,
    surface = JukePalette.PanelAlt,
    onSurface = JukePalette.Text,
    surfaceVariant = JukePalette.Panel,
    onSurfaceVariant = JukePalette.Text,
    error = JukePalette.Error,
    onError = JukePalette.Text,
)

private val JukeTypography = Typography(
    displayLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 36.sp,
        lineHeight = 42.sp,
    ),
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 28.sp,
        lineHeight = 34.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 18.sp,
        lineHeight = 24.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 22.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 13.sp,
        lineHeight = 18.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 12.sp,
        lineHeight = 14.sp,
        letterSpacing = 0.5.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 13.sp,
        letterSpacing = 0.5.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 10.sp,
        lineHeight = 12.sp,
        letterSpacing = 0.6.sp,
    ),
)

private val JukeShapes = Shapes(
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
)

@Composable
fun JukeTheme(
    useDarkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    CompositionLocalProvider(LocalJukePlatformPalette provides JukePalette) {
        MaterialTheme(
            colorScheme = if (useDarkTheme) DarkColors else LightColors,
            typography = JukeTypography,
            shapes = JukeShapes,
            content = content,
        )
    }
}
