package com.igrisstudios.aebuzz

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannel()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "aebuzz/native").setMethodCallHandler { call, result ->
            when (call.method) {
                "openBuzz" -> result.success(openBuzz())
                "hasFirebase" -> result.success(FirebaseBootstrap.load(this) != null)
                "setFirebase" -> {
                    @Suppress("UNCHECKED_CAST")
                    val options = call.arguments as Map<String, String>
                    try {
                        result.success(FirebaseBootstrap.save(this, options))
                    } catch (e: IllegalArgumentException) {
                        result.error("bad_options", e.message, null)
                    }
                }
                "openAppSettings" -> {
                    startActivity(
                        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun openBuzz(): Boolean {
        val intent = packageManager.getLaunchIntentForPackage(BUZZ_PACKAGE) ?: return false
        startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return true
    }

    // High importance so forwarded alerts pop on screen instead of landing silently.
    // Android fixes a channel's sound at creation, so a new sound needs a new channel ID.
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        LEGACY_CHANNEL_IDS.forEach(manager::deleteNotificationChannel)
        val sound = Uri.parse("android.resource://$packageName/${R.raw.unison}")
        val audio = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        val channel = NotificationChannel(CHANNEL_ID, "Buzz messages", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Buzz notifications forwarded from your laptop"
            setSound(sound, audio)
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        // Must match ANDROID_CHANNEL_ID in server/aebuzz_server/fcm.py.
        const val CHANNEL_ID = "buzz_messages_unison"
        val LEGACY_CHANNEL_IDS = listOf("buzz_messages")
        const val BUZZ_PACKAGE = "xyz.block.buzz.mobile"
    }
}
