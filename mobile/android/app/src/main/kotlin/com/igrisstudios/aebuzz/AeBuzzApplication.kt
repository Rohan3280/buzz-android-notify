package com.igrisstudios.aebuzz

import android.app.Application

class AeBuzzApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // Before any activity or FCM service runs, so killed-app notifications still work.
        FirebaseBootstrap.initFromSaved(this)
    }
}
