package fm.juke.mobile.core.design.components

import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import fm.juke.core.design.components.PlatformInputField
import fm.juke.mobile.core.design.JukePalette

@Composable
fun JukeInputField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    error: String? = null,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    singleLine: Boolean = true,
) {
    PlatformInputField(
        value = value,
        onValueChange = onValueChange,
        placeholder = placeholder,
        modifier = modifier,
        label = {
            Text(
                text = label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = JukePalette.Muted,
            )
        },
        error = error,
        cornerRadius = 22.dp,
        backgroundAlpha = 0.35f,
        borderWidth = 1.2.dp,
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        visualTransformation = visualTransformation,
        singleLine = singleLine,
    )
}
