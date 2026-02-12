package fm.juke.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import fm.juke.mobile.core.design.JukeTheme
import fm.juke.mobile.core.di.ServiceLocator
import fm.juke.mobile.ui.navigation.JukeApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ServiceLocator.init(applicationContext)
        enableEdgeToEdge()
        setContent {
            JukeTheme {
                JukeApp()
            }
        }
    }
}
