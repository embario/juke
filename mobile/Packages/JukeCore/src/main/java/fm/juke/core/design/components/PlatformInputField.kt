package fm.juke.core.design.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import fm.juke.core.design.LocalJukePlatformPalette

@Composable
fun PlatformInputField(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    label: @Composable (() -> Unit)? = null,
    error: String? = null,
    cornerRadius: Dp = 14.dp,
    backgroundAlpha: Float = 0.65f,
    borderWidth: Dp = 1.dp,
    errorBorderWidth: Dp = borderWidth,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    singleLine: Boolean = true,
) {
    val palette = LocalJukePlatformPalette.current
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        label?.invoke()
        val shape = RoundedCornerShape(cornerRadius)
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .border(
                    width = if (error != null) errorBorderWidth else borderWidth,
                    color = if (error != null) palette.Error else palette.Border,
                    shape = shape,
                )
                .background(palette.PanelAlt.copy(alpha = backgroundAlpha), shape),
        ) {
            TextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier.fillMaxWidth(),
                textStyle = MaterialTheme.typography.bodyLarge,
                placeholder = { Text(text = placeholder, color = palette.Muted) },
                singleLine = singleLine,
                keyboardOptions = keyboardOptions,
                keyboardActions = keyboardActions,
                visualTransformation = visualTransformation,
                shape = shape,
                isError = error != null,
                colors = TextFieldDefaults.colors(
                    focusedTextColor = palette.Text,
                    unfocusedTextColor = palette.Text,
                    disabledTextColor = palette.Text.copy(alpha = 0.4f),
                    errorTextColor = palette.Error,
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    disabledContainerColor = Color.Transparent,
                    errorContainerColor = Color.Transparent,
                    cursorColor = palette.Accent,
                    errorCursorColor = palette.Error,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    disabledIndicatorColor = Color.Transparent,
                    errorIndicatorColor = Color.Transparent,
                    focusedPlaceholderColor = palette.Muted,
                    unfocusedPlaceholderColor = palette.Muted,
                    disabledPlaceholderColor = palette.Muted.copy(alpha = 0.5f),
                    errorPlaceholderColor = palette.Muted,
                ),
            )
        }
        if (!error.isNullOrBlank()) {
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = error,
                style = MaterialTheme.typography.bodySmall,
                color = palette.Error,
            )
        }
    }
}
