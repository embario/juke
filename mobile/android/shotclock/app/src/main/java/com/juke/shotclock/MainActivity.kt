package com.juke.shotclock

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.juke.shotclock.core.design.ShotClockTheme
import com.juke.shotclock.core.di.ServiceLocator
import com.juke.shotclock.ui.navigation.ShotClockApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ServiceLocator.init(applicationContext)
        enableEdgeToEdge()
        setContent {
            ShotClockTheme {
                ShotClockApp()
            }
        }
    }
}
