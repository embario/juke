package com.juke.juke

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import com.juke.juke.core.di.ServiceLocator

class JukeApplication : Application(), ImageLoaderFactory {
    override fun onCreate() {
        super.onCreate()
        ServiceLocator.init(this)
    }

    override fun newImageLoader(): ImageLoader = ServiceLocator.imageLoader
}
