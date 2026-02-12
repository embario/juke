package fm.juke.mobile

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import fm.juke.mobile.core.di.ServiceLocator

class JukeApplication : Application(), ImageLoaderFactory {
    override fun onCreate() {
        super.onCreate()
        ServiceLocator.init(this)
    }

    override fun newImageLoader(): ImageLoader = ServiceLocator.imageLoader
}
