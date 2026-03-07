package com.juke.juke

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.juke.juke.core.design.JukeTheme
import com.juke.juke.core.di.ServiceLocator
import com.juke.juke.ui.navigation.JukeApp

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
