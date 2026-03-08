package com.juke.tunetrivia

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.juke.tunetrivia.core.design.TuneTriviaTheme
import com.juke.tunetrivia.core.di.ServiceLocator
import com.juke.tunetrivia.ui.navigation.TuneTriviaApp

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
