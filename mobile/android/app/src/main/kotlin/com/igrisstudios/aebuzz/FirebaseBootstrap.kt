package com.igrisstudios.aebuzz

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

/**
 * The APK ships without google-services.json so anyone can use it with their own
 * Firebase project. The project's public options arrive in the pairing QR and are
 * kept here, so Firebase can start natively whenever the process starts, including
 * when FCM wakes a killed app to show a notification.
 */
object FirebaseBootstrap {
    private const val PREFS = "aebuzz_firebase"
    private val KEYS = listOf("api_key", "app_id", "project_id", "sender_id")

    fun initFromSaved(context: Context) {
        val saved = load(context) ?: return
        if (FirebaseApp.getApps(context).isEmpty()) {
            FirebaseApp.initializeApp(context, toOptions(saved))
        }
    }

    fun load(context: Context): Map<String, String>? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val values = KEYS.associateWith { prefs.getString(it, null) }
        if (values.values.any { it.isNullOrEmpty() }) return null
        return values.mapValues { it.value!! }
    }

    /** Returns "ok", or "restart_required" when Firebase is already running for another project. */
    fun save(context: Context, options: Map<String, String>): String {
        require(KEYS.all { !options[it].isNullOrEmpty() }) { "missing Firebase option" }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().apply {
            KEYS.forEach { putString(it, options[it]) }
        }.commit()
        val running = FirebaseApp.getApps(context).firstOrNull()
        if (running == null) {
            FirebaseApp.initializeApp(context, toOptions(options))
            return "ok"
        }
        return if (running.options.projectId == options["project_id"]) "ok" else "restart_required"
    }

    private fun toOptions(values: Map<String, String>) = FirebaseOptions.Builder()
        .setApiKey(values.getValue("api_key"))
        .setApplicationId(values.getValue("app_id"))
        .setProjectId(values.getValue("project_id"))
        .setGcmSenderId(values.getValue("sender_id"))
        .build()
}
