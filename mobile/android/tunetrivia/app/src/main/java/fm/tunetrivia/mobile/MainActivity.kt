package fm.tunetrivia.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import fm.tunetrivia.mobile.core.design.TuneTriviaTheme
import fm.tunetrivia.mobile.core.di.ServiceLocator
import fm.tunetrivia.mobile.ui.navigation.TuneTriviaApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ServiceLocator.init(applicationContext)
        enableEdgeToEdge()
        setContent {
            TuneTriviaTheme {
                TuneTriviaApp()
            }
        }
    }
}
