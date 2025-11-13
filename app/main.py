package com.zafer.smm
import com.google.gson.annotations.SerializedName
import androidx.compose.ui.draw.alpha
import androidx.compose.runtime.rememberCoroutineScope
import android.app.KeyguardManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.OutlinedButton
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.IconButton
import android.content.ClipData
import android.content.ClipboardManager
import androidx.compose.material3.Card
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.mutableStateListOf
import android.content.Context
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.TextButton
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.window.DialogProperties
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.ceil
import kotlin.random.Random
import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Notification
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.google.firebase.messaging.FirebaseMessaging
import com.google.android.gms.tasks.Task
import androidx.lifecycle.lifecycleScope
import java.util.concurrent.TimeUnit
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.Constraints
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ListenableWorker
import com.zafer.smm.ui.UpdatePromptHost
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Divider
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.offset
import androidx.compose.ui.text.style.TextAlign
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import androidx.annotation.Keep




private const val OWNER_UID_BACKEND = "OWNER-0001" // يجب أن يطابق OWNER_UID في السيرفر


private val Dim = androidx.compose.ui.graphics.Color(0xFFADB5BD)
/* =========================
   Notifications (system-level)
   ========================= */
object AppNotifier {
    private const val CHANNEL_ID = "zafer_main_high"
    private const val CHANNEL_NAME = "App Alerts"
    private const val CHANNEL_DESC = "User orders, balance updates, and general alerts"

    fun ensureChannel(ctx: android.content.Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = CHANNEL_DESC
                enableVibration(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            val nm = ctx.getSystemService(android.content.Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(ch)
        }
    }

    fun requestPermissionIfNeeded(activity: androidx.activity.ComponentActivity) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ActivityCompat.checkSelfPermission(activity, "android.permission.POST_NOTIFICATIONS")
                != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(activity, arrayOf("android.permission.POST_NOTIFICATIONS"), 9911)
            }
        }
    }

    fun notifyNow(ctx: android.content.Context, title: String, body: String) {
        ensureChannel(ctx)
        val tapIntent = Intent(ctx, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        val pi = PendingIntent.getActivity(
            ctx, (System.currentTimeMillis()%10000).toInt(), tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = NotificationCompat.Builder(ctx, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_chat) // uses system icon to avoid resource issues
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setContentIntent(pi)
        NotificationManagerCompat.from(ctx).notify((System.currentTimeMillis()%Int.MAX_VALUE).toInt(), builder.build())
    }
}


    // --- Pricing cache (prefix+amounts -> map) persisted in SharedPreferences with TTL ---
    private object PricingCache {
        private fun verKey(prefix: String, amounts: List<Int>) = "ver:" + key(prefix, amounts)
        fun getVersion(ctx: Context, prefix: String, amounts: List<Int>): Long = prefs(ctx).getLong(verKey(prefix, amounts), 0L)
        fun saveVersion(ctx: Context, prefix: String, amounts: List<Int>, ver: Long) {
            prefs(ctx).edit().putLong(verKey(prefix, amounts), ver).apply()
        }
        private const val PREF = "pricing_cache_v1"
        private const val TTL_HOURS_DEFAULT = 12L

        private fun prefs(ctx: Context): SharedPreferences =
            ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)

        private fun key(prefix: String, amounts: List<Int>) =
            prefix + ":" + amounts.joinToString(",")

        fun load(ctx: Context, prefix: String, amounts: List<Int>): Map<String, PublicPricingEntry> {
            val json = prefs(ctx).getString("data:" + key(prefix, amounts), null) ?: return emptyMap()
            return try {
                val type = object : TypeToken<Map<String, PublicPricingEntry>>() {}.type
                Gson().fromJson<Map<String, PublicPricingEntry>>(json, type) ?: emptyMap()
            } catch (_: Throwable) { emptyMap() }
        }

        fun save(ctx: Context, prefix: String, amounts: List<Int>, data: Map<String, PublicPricingEntry>) {
            val k = key(prefix, amounts)
            prefs(ctx).edit()
                .putString("data:" + k, Gson().toJson(data))
                .putLong("ts:" + k, System.currentTimeMillis())
                .apply()
        }

        fun isFresh(ctx: Context, prefix: String, amounts: List<Int>, ttlHours: Long = TTL_HOURS_DEFAULT): Boolean {
            val ts = prefs(ctx).getLong("ts:" + key(prefix, amounts), 0L)
            if (ts <= 0L) return false
            val age = System.currentTimeMillis() - ts
            return age < ttlHours * 60L * 60L * 1000L
        }
    }
    
    // --- API Services Pricing cache (per category) with server version ---
    private object ApiPricingCache {
        private const val PREF = "api_pricing_cache_v1"
        private fun prefs(ctx: Context): SharedPreferences =
            ctx.getSharedPreferences(PREF, Context.MODE_PRIVATE)
        private fun mapKey(cat: String) = "map:" + cat
        private fun verKey(cat: String) = "ver:" + cat

        fun load(ctx: Context, cat: String): Map<String, PublicPricingEntry> {
            if (cat.isEmpty()) return emptyMap()
            val s = prefs(ctx).getString(mapKey(cat), null) ?: return emptyMap()
            return try {
                val obj = org.json.JSONObject(s)
                val out = mutableMapOf<String, PublicPricingEntry>()
                val it = obj.keys()
                while (it.hasNext()) {
                    val k = it.next()
                    val v = obj.optJSONObject(k) ?: continue
                    out[k] = PublicPricingEntry(
                        pricePerK = v.optDouble("price_per_k", 0.0),
                        minQty    = v.optInt("min_qty", 0),
                        maxQty    = v.optInt("max_qty", 0),
                        mode      = v.optString("mode", "per_k")
                    )
                }
                out
            } catch (_: Throwable) { emptyMap() }
        }

        fun save(ctx: Context, cat: String, map: Map<String, PublicPricingEntry>) {
            if (cat.isEmpty() || map.isEmpty()) return
            val obj = org.json.JSONObject()
            for ((k, v) in map) {
                val o = org.json.JSONObject()
                    .put("price_per_k", v.pricePerK)
                    .put("min_qty", v.minQty)
                    .put("max_qty", v.maxQty)
                    .put("mode", v.mode)
                obj.put(k, o)
            }
            prefs(ctx).edit().putString(mapKey(cat), obj.toString()).apply()
            prefs(ctx).edit().putLong("ts:" + mapKey(cat), System.currentTimeMillis()).apply()
        }

        fun getVersion(ctx: Context, cat: String): Long = prefs(ctx).getLong(verKey(cat), 0L)
        fun saveVersion(ctx: Context, cat: String, ver: Long) { prefs(ctx).edit().putLong(verKey(cat), ver).apply() }
    }
    // -------------------------------------------------------------------------------
    @Composable
private fun NoticeBody(text: String) {
    val clip = LocalClipboardManager.current
    val codeRegex = "(?:الكود|code|card|voucher|redeem)\\s*[:：-]?\\s*([A-Za-z0-9][A-Za-z0-9-]{5,})".toRegex(RegexOption.IGNORE_CASE)
    val match = codeRegex.find(text)
    if (match != null) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            SelectionContainer {
                Text(text, color = Dim, fontSize = 10.sp, modifier = Modifier.weight(1f))
            }
            TextButton(onClick = {
                val c = match.groupValues.getOrNull(1) ?: text
                clip.setText(AnnotatedString(c))
            }) { Text("نسخ") }
        }
    } else {
        SelectionContainer {
            Text(text, color = Dim, fontSize = 10.sp)
        }
    }
}

/* =========================
   إعدادات الخادم
   ========================= */
private const val API_BASE =
    "https://ratluzen-smm-backend-e12a704bf3c1.herokuapp.com" // عدّلها إذا تغيّر الباكند

/** اتصال مباشر مع مزوّد SMM (اختياري) */
private const val PROVIDER_DIRECT_URL = "https://kd1s.com/api/v2"
private const val PROVIDER_DIRECT_KEY_VALUE = "25a9ceb07be0d8b2ba88e70dcbe92e06"

/** مسارات الأدمن (مطابقة للباكند الموحد) */
private object AdminEndpoints {
    const val pendingServices = "/api/admin/pending/services"
    const val pendingItunes   = "/api/admin/pending/itunes"
    const val pendingPubg     = "/api/admin/pending/pubg"
    const val pendingLudo     = "/api/admin/pending/ludo"
    const val pendingBalances = "/api/admin/pending/balances"

    // ✅ الكروت المعلّقة لأسيا سيل
    const val pendingCards    = "/api/admin/pending/cards"
    fun topupCardReject(id: Int) = "/api/admin/topup_cards/$id/reject"
    fun topupCardExecute(id: Int) = "/api/admin/topup_cards/$id/execute"

    const val orderApprove    = "/api/admin/orders/%d/approve"
    const val orderDeliver    = "/api/admin/orders/%d/deliver"
    const val orderReject     = "/api/admin/orders/%d/reject"

    // قد تتوفر في باكندك، وإلا ستظهر "تعذر جلب البيانات"
    const val walletTopup     = "/api/admin/wallet/topup"
    const val walletDeduct    = "/api/admin/wallet/deduct"
    const val usersCount      = "/api/admin/users/count"
    const val usersBalances   = "/api/admin/users/balances"
    const val providerBalance = "/api/admin/provider/balance"

    // Overrides for service IDs (server-level)
    const val svcIdsList = "/api/admin/service_ids/list"
    const val svcIdSet   = "/api/admin/service_ids/set"
    const val svcIdClear = "/api/admin/service_ids/clear"

    // Pricing overrides
    const val pricingList = "/api/admin/pricing/list"
    const val pricingSet  = "/api/admin/pricing/set"
    const val pricingClear= "/api/admin/pricing/clear"
    const val orderSetPrice = "/api/admin/pricing/order/set"
    const val orderClearPrice = "/api/admin/pricing/order/clear"
    const val orderSetQty = "/api/admin/pricing/order/set_qty"
    const val announcementCreate = "/api/admin/announcement/create"
    const val announcementsList = "/api/public/announcements"
    const val announcementsAdminList = "/api/admin/announcements"
    fun announcementDelete(id: Int) = "/api/admin/announcement/$id/delete"
    fun announcementUpdate(id: Int) = "/api/admin/announcement/$id/update"
    // Auto-exec (admin) endpoints
    const val autoExecStatus = "/api/admin/auto_exec/status"
    const val autoExecToggle = "/api/admin/auto_exec/toggle"
    const val autoExecRun    = "/api/admin/auto_exec/run"
    // --- Code Pools (iTunes + Phone Cards)
    const val itunesCodesList = "/api/admin/codes/itunes/list"
    const val itunesCodesAdd  = "/api/admin/codes/itunes/add"
    fun itunesCodeDelete(id: Int) = "/api/admin/codes/itunes/$id/delete"

    fun cardCodesList(telco: String) = "/api/admin/codes/cards/$telco/list"   // telco: "atheir" | "asiacell" | "korek"
    fun cardCodesAdd(telco: String)  = "/api/admin/codes/cards/$telco/add"
    fun cardCodeDelete(telco: String, id: Int) = "/api/admin/codes/cards/$telco/$id/delete"

    // --- Scoped Auto-Exec
    fun autoExecStatusScoped(scope: String) = "/api/admin/auto_exec/status?scope=$scope"  // scope: "itunes" | "cards"
    const val autoExecSet = "/api/admin/auto_exec/set"  // POST {scope, enabled}

    
}


/* =========================
   Admin Service ID Overrides API
   ========================= */
private suspend fun apiAdminListSvcOverrides(token: String): Map<String, Long> {
    val (code, txt) = httpGet(AdminEndpoints.svcIdsList, headers = mapOf("x-admin-password" to token))
    if (code !in 200..299 || txt == null) return emptyMap()
    return try {
        val result = mutableMapOf<String, Long>()
        val trimmed = txt.trim()
        if (trimmed.startsWith("{")) {
            val o = JSONObject(trimmed)
            if (o.has("list")) {
                val arr = o.optJSONArray("list") ?: JSONArray()
                for (i in 0 until arr.length()) {
                    val it = arr.optJSONObject(i) ?: continue
                    val k = it.optString("ui_key", "")
                    val v = it.optLong("service_id", 0L)
                    if (k.isNotBlank() && v > 0) result[k] = v
                }
            } else {
                // maybe dict style
                val it = o.keys()
                while (it.hasNext()) {
                    val k = it.next()
                    val v = o.optLong(k, 0L)
                    if (k.isNotBlank() && v > 0) result[k] = v
                }
            }
        } else {
            // not expected
        }
        result
    } catch (_: Exception) { emptyMap() }
}

private suspend fun apiAdminSetSvcOverride(token: String, uiKey: String, id: Long): Boolean {
    val body = JSONObject().put("ui_key", uiKey).put("service_id", id)
    val (code, _) = httpPost(AdminEndpoints.svcIdSet, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminClearSvcOverride(token: String, uiKey: String): Boolean {
    val body = JSONObject().put("ui_key", uiKey)
    val (code, _) = httpPost(AdminEndpoints.svcIdClear, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

/* =========================
*/

   

data class PendingSvcItem(val id: Long, val title: String, val quantity: Int, val price: Double)

private suspend fun apiAdminFetchPendingServices(token: String): List<PendingSvcItem> {
    val (code, txt) = httpGet(AdminEndpoints.pendingServices, headers = mapOf("x-admin-password" to token))
    if (code !in 200..299 || txt == null) return emptyList()
    return try {
        val out = mutableListOf<PendingSvcItem>()
        val o = JSONObject(txt)
        val arr = o.optJSONArray("list") ?: JSONArray()
        for (i in 0 until arr.length()) {
            val it = arr.optJSONObject(i) ?: continue
            val id = it.optLong("id", -1)
            val title = it.optString("title", "")
            val qty = it.optInt("quantity", 0)
            val price = it.optDouble("price", 0.0)
            if (id > 0) out.add(PendingSvcItem(id, title, qty, price))
        }
        out
    } catch (_: Exception) { emptyList() }
}

private suspend fun apiAdminSetOrderPrice(token: String, orderId: Long, price: Double): Boolean {
    val body = JSONObject().put("order_id", orderId).put("price", price)
    val (code, _) = httpPost(AdminEndpoints.orderSetPrice, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminSetOrderQty(token: String, orderId: Long, quantity: Int, reprice: Boolean = false): Boolean {
    val body = JSONObject().put("order_id", orderId).put("quantity", quantity).put("reprice", reprice)
    val (code, _) = httpPost(AdminEndpoints.orderSetQty, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
private suspend fun apiAdminClearOrderPrice(token: String, orderId: Long): Boolean {
    val body = JSONObject().put("order_id", orderId)
    val (code, _) = httpPost(AdminEndpoints.orderClearPrice, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
/* =========================
   Admin Pricing Overrides API
   ========================= */
data class PricingOverride(val pricePerK: Double, val minQty: Int, val maxQty: Int, val mode: String = "per_k")

private suspend fun apiAdminListPricing(token: String): Map<String, PricingOverride> {
    val (code, txt) = httpGet(AdminEndpoints.pricingList, headers = mapOf("x-admin-password" to token))
    if (code !in 200..299 || txt == null) return emptyMap()
    return try {
        val result = mutableMapOf<String, PricingOverride>()
        val trimmed = txt.trim()
        if (trimmed.startsWith("{")) {
            val o = JSONObject(trimmed)
            if (o.has("list")) {
                val arr = o.optJSONArray("list") ?: JSONArray()
                for (i in 0 until arr.length()) {
                    val it = arr.optJSONObject(i) ?: continue
                    val k = it.optString("ui_key", "")
                    val p = it.optDouble("price_per_k", Double.NaN)
                        val min = it.optInt("min_qty", 0)
                        val max = it.optInt("max_qty", 0)
                        val md = it.optString("mode", "per_k")
                    if (k.isNotBlank() && !p.isNaN()) {
                        result[k] = PricingOverride(p, min, max, md)
                    }
                }
            }
        }
        result
    } catch (_: Exception) { emptyMap() }
}

private suspend fun apiAdminSetPricing(token: String, uiKey: String, pricePerK: Double, minQty: Int, maxQty: Int, mode: String? = null): Boolean {
    val body = JSONObject().put("ui_key", uiKey).put("price_per_k", pricePerK).put("min_qty", minQty).put("max_qty", maxQty).apply { if (mode != null) put("mode", mode) }
    val (code, _) = httpPost(AdminEndpoints.pricingSet, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminClearPricing(token: String, uiKey: String): Boolean {
    val body = JSONObject().put("ui_key", uiKey)
    val (code, _) = httpPost(AdminEndpoints.pricingClear, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
/* =========================
   Public Pricing (read-only for client)
   ========================= */
@Keep
data class PublicPricingEntry(
    @SerializedName(value = "pricePerK", alternate = ["price_per_k", "flat_price"])
    val pricePerK: Double = 0.0,
    @SerializedName(value = "minQty", alternate = ["min_qty"])
    val minQty: Int = 0,
    @SerializedName(value = "maxQty", alternate = ["max_qty"])
    val maxQty: Int = 0,
    @SerializedName(value = "mode", alternate = ["pricing_mode"])
    val mode: String = "per_k"
)

private suspend fun /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys: List<String>): Map<String, PublicPricingEntry> {
    if (keys.isEmpty()) return emptyMap()
    val encoded = keys.joinToString(",") { java.net.URLEncoder.encode(it, "UTF-8") }
    val (code, txt) = httpGet("/api/public/pricing/bulk?keys=$encoded")
    if (code !in 200..299 || txt == null) return emptyMap()
    return try {
        val out = mutableMapOf<String, PublicPricingEntry>()
        val root = org.json.JSONObject(txt)
        val map = root.optJSONObject("map") ?: org.json.JSONObject()
        val iter = map.keys()
        while (iter.hasNext()) {
            val k = iter.next()
            val obj = map.optJSONObject(k) ?: continue
            out[k] = PublicPricingEntry(
                pricePerK = obj.optDouble("price_per_k", 0.0),
                minQty    = obj.optInt("min_qty", 0),
                maxQty    = obj.optInt("max_qty", 0),
                mode      = obj.optString("mode", "per_k")
            )
        }
        out
    } catch (_: Exception) { emptyMap() }
}

private suspend fun apiPublicPricingVersion(): Long {
    val (code, txt) = httpGet("/api/public/pricing/version")
    if (code !in 200..299 || txt == null) return 0L
    return try { org.json.JSONObject(txt).optLong("version", 0L) } catch (_: Exception) { 0L }
}

@Composable
private fun PricingEditorScreen(token: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var selectedCat by remember { mutableStateOf<String?>(null) }
    var overrides by remember { mutableStateOf<Map<String, PricingOverride>>(emptyMap()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var refreshKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }

    val cats = listOf("مشاهدات تيكتوك", "لايكات تيكتوك", "متابعين تيكتوك", "مشاهدات بث تيكتوك", "رفع سكور تيكتوك",
        "مشاهدات انستغرام", "لايكات انستغرام", "متابعين انستغرام", "مشاهدات بث انستا", "خدمات التليجرام",
        "ببجي", "لودو"
    ,
        "ايتونز", "أثير", "اسياسيل", "كورك"
    )

    fun servicesFor(cat: String): List<ServiceDef> {
        fun hasAll(key: String, vararg words: String) = words.all { key.contains(it) }
        return servicesCatalog.filter { svc ->
            val k = svc.uiKey
            when (cat) {
                "مشاهدات تيكتوك"   -> hasAll(k, "مشاهدات", "تيكتوك")
                "لايكات تيكتوك"     -> hasAll(k, "لايكات", "تيكتوك")
                "متابعين تيكتوك"    -> hasAll(k, "متابعين", "تيكتوك")
                "مشاهدات بث تيكتوك" -> hasAll(k, "مشاهدات", "بث", "تيكتوك")
                "رفع سكور تيكتوك"   -> hasAll(k, "رفع", "سكور", "تيكتوك") || hasAll(k, "رفع", "سكور", "بث") || hasAll(k, "رفع", "سكور", "بث")
                "مشاهدات انستغرام"  -> hasAll(k, "مشاهدات", "انستغرام")
                "لايكات انستغرام"    -> hasAll(k, "لايكات", "انستغرام")
                "متابعين انستغرام"   -> hasAll(k, "متابعين", "انستغرام")
                "مشاهدات بث انستا"   -> hasAll(k, "مشاهدات", "بث", "انستا")
                "خدمات التليجرام"    -> k.contains("تيليجرام") || k.contains("التليجرام") || k.contains("تلي")
                else -> false
            }
        }
    }

    LaunchedEffect(refreshKey) {
        loading = true; err = null
        try { overrides = apiAdminListPricing(token) } catch (t: Throwable) { err = t.message }
        loading = false
    }

    val ctx = LocalContext.current
    val Dim = Color(0xFFADB5BD)

    Column(Modifier.fillMaxSize().background(Bg).padding(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("تغيير الأسعار والكميات", fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = OnBg)
        }
        
if (loading) { CircularProgressIndicator(color = Accent); return@Column }
// removed misplaced dialog invocation
// removed misplaced dialog invocation
// removed misplaced dialog invocation

        snack?.let { s -> Snackbar(Modifier.fillMaxWidth()) { Text(s) }; LaunchedEffect(s) { kotlinx.coroutines.delay(2000); snack = null } }
        err?.let { e -> Text("تعذر جلب البيانات: $e", color = Bad); return@Column }

        if (selectedCat == null) {
            cats.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth()) {
                    row.forEach { c ->
                        Card(
                            modifier = Modifier.weight(1f).padding(4.dp).clickable { selectedCat = c },
                            colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                        ) { Text(c, Modifier.padding(16.dp), fontWeight = FontWeight.SemiBold) }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        } else {
            val list = servicesFor(selectedCat!!)
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selectedCat = null }) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
                Spacer(Modifier.width(6.dp))
                Text(selectedCat!!, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = OnBg)

/* PUBG/Ludo Orders Editor */
if (selectedCat in listOf("ببجي", "لودو", "ايتونز", "أثير", "اسياسيل", "كورك")) {
    // عرض باقات ببجي/لودو وباقات مبالغ (ايتونز/أثير/اسياسيل/كورك) وتعديل السعر/الكمية
    data class PkgSpec(val key: String, val title: String, val defQty: Int, val defPrice: Double)
    val scope = rememberCoroutineScope()

    val pkgs: List<PkgSpec> = when (selectedCat) {
        "ببجي" -> listOf(
            PkgSpec("pkg.pubg.60",   "60 شدة",    60,    2.0),
            PkgSpec("pkg.pubg.325",  "325 شدة",   325,   9.0),
            PkgSpec("pkg.pubg.660",  "660 شدة",   660,   15.0),
            PkgSpec("pkg.pubg.1800", "1800 شدة",  1800,  40.0),
            PkgSpec("pkg.pubg.3850", "3850 شدة",  3850,  55.0),
            PkgSpec("pkg.pubg.8100", "8100 شدة",  8100,  100.0),
            PkgSpec("pkg.pubg.16200","16200 شدة", 16200, 185.0)
        )
        "لودو" -> listOf(
            // Diamonds
            PkgSpec("pkg.ludo.diamonds.810",     "810 الماسة",       810,     5.0),
            PkgSpec("pkg.ludo.diamonds.2280",    "2280 الماسة",      2280,    10.0),
            PkgSpec("pkg.ludo.diamonds.5080",    "5080 الماسة",      5080,    15.0),
            PkgSpec("pkg.ludo.diamonds.12750",    "12750 الماسة",      12750,    35.0),
            PkgSpec("pkg.ludo.diamonds.27200",   "27200 الماسة",     27200,   85.0),
            PkgSpec("pkg.ludo.diamonds.54900",   "54900 الماسة",     54900,   165.0),
            PkgSpec("pkg.ludo.diamonds.164800",  "164800 الماسة",    164800,  475.0),
            PkgSpec("pkg.ludo.diamonds.275400",  "275400 الماسة",    275400,  800.0),
            // Gold
            PkgSpec("pkg.ludo.gold.66680",       "66680 ذهب",        66680,   5.0),
            PkgSpec("pkg.ludo.gold.219500",      "219500 ذهب",       219500,  10.0),
            PkgSpec("pkg.ludo.gold.1443000",     "1443000 ذهب",      1443000, 20.0),
            PkgSpec("pkg.ludo.gold.3627000",     "3627000 ذهب",      3627000, 35.0),
            PkgSpec("pkg.ludo.gold.9830000",     "9830000 ذهب",      9830000, 85.0),
            PkgSpec("pkg.ludo.gold.24835000",    "24835000 ذهب",     24835000,165.0),
            PkgSpec("pkg.ludo.gold.74550000",    "74550000 ذهب",     74550000,475.0),
            PkgSpec("pkg.ludo.gold.124550000",   "124550000 ذهب",    124550000,800.0)
        )
        "ايتونز" -> COMMON_AMOUNTS.map { usd ->
            PkgSpec("topup.itunes.$usd", "${usd}$ ايتونز", usd, usd.toDouble())
        }
        "أثير" -> COMMON_AMOUNTS.map { usd ->
            PkgSpec("topup.atheer.$usd", "${usd}$ اثير", usd, usd.toDouble())
        }
        "اسياسيل" -> COMMON_AMOUNTS.map { usd ->
            PkgSpec("topup.asiacell.$usd", "${usd}$ اسياسيل", usd, usd.toDouble())
        }
        "كورك" -> COMMON_AMOUNTS.map { usd ->
            PkgSpec("topup.korek.$usd", "${usd}$ كورك", usd, usd.toDouble())
        }
        else -> emptyList()
    }

    LazyColumn(Modifier.fillMaxSize().padding(16.dp)) {
        items(pkgs) { p ->
            val ov = overrides[p.key]
            val curPrice = ov?.pricePerK ?: p.defPrice
            val curQty   = if (ov != null && ov.minQty > 0) ov.minQty else p.defQty

            var open by remember { mutableStateOf(false) }
            Card(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(p.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                    Spacer(Modifier.height(4.dp))
                    Text("الكمية الحالية: $curQty  •  السعر الحالي: ${"%.2f".format(curPrice)}", color = Dim, fontSize = 10.sp)
                    Spacer(Modifier.height(8.dp))
                    Row {
                        Button(onClick = { open = true }, colors = ButtonDefaults.buttonColors(containerColor = Accent)) {
                            Text("تعديل", color = Color.White)
                        }
                        Spacer(Modifier.width(8.dp))
                        if (ov != null) {
                            OutlinedButton(onClick = {
                                scope.launch {
                                    val ok = apiAdminClearPricing(token, p.key)
                                    if (ok) { snack = "تم حذف التعديل"; refreshKey++ } else snack = "فشل الحذف"
                                }
                            }) { Text("حذف التعديل") }
                        }
                    }
                }
            }

            if (open) {
                var priceInput by remember { mutableStateOf(curPrice.toString()) }
                var qtyInput by remember { mutableStateOf(curQty.toString()) }
                AlertDialog(
                    onDismissRequest = { open = false },
                    confirmButton = {
                        TextButton(onClick = {
                            val newPrice = priceInput.toDoubleOrNull()
                            val newQty   = qtyInput.toIntOrNull()
                            if (newPrice != null && newQty != null) {
                                scope.launch {
                                    val ok = apiAdminSetPricing(token, p.key, newPrice, newQty, newQty, "package")
                                    if (ok) { snack = "تم الحفظ"; open = false; refreshKey++ } else snack = "فشل الحفظ"
                                }
                            } else snack = "تحقق من القيم."
                        }) { Text("حفظ") }
                    },
                    dismissButton = { TextButton(onClick = { open = false }) { Text("إلغاء") } },
                    title = { Text("تعديل ${p.title}", color = OnBg) },
                    text = {
            Column {
                // شرح مبسّط للمستخدم
                Text("اربط كلمة مرور لحسابك الحالي المرتبط بالـ UID. ستستخدم هذه الكلمة لاحقًا لتسجيل الدخول على أي جهاز آخر. احتفظ بها سريًا.", color = OnBg)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = priceInput, onValueChange = { priceInput = it }, label = { Text("السعر") })
                            Spacer(Modifier.height(8.dp))
                            OutlinedTextField(value = qtyInput, onValueChange = { qtyInput = it }, label = { Text("الكمية") })
                        }
                    }
                )
            }
        }
    }
}

            }
            Spacer(Modifier.height(10.dp))

            LazyColumn {
                items(list) { svc ->
                    var showEdit by remember { mutableStateOf(false) }
                    val key = svc.uiKey
                    val ov  = overrides[key]
                    val has = ov != null
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(key, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            val tip = if (has) " (معدل)" else " (افتراضي)"
                            Text("السعر/ألف: ${ov?.pricePerK ?: svc.pricePerK}  •  الحد الأدنى: ${ov?.minQty ?: svc.min}  •  الحد الأقصى: ${ov?.maxQty ?: svc.max}$tip", color = Dim, fontSize = 10.sp)
                            Spacer(Modifier.height(8.dp))
                            Row {
                                TextButton(onClick = { showEdit = true }) { Text("تعديل") }
                                Spacer(Modifier.width(6.dp))
                                if (has) {
                                    TextButton(onClick = {
                                        scope.launch {
                                            val ok = apiAdminClearPricing(token, key)
                                            if (ok) { snack = "تم حذف التعديل"; refreshKey++ } else snack = "فشل الحذف"
                                        }
                                    }) { Text("حذف التعديل") }
                                }
                            }
                        }
                    }

                    if (showEdit) {
                        var price by remember { mutableStateOf(TextFieldValue((ov?.pricePerK ?: svc.pricePerK).toString())) }
                        var min by remember { mutableStateOf(TextFieldValue((ov?.minQty ?: svc.min).toString())) }
                        var max by remember { mutableStateOf(TextFieldValue((ov?.maxQty ?: svc.max).toString())) }
                        AlertDialog(
                            onDismissRequest = { showEdit = false },
                            confirmButton = {
                                TextButton(onClick = {
                                    scope.launch {
                                        val p = price.text.toDoubleOrNull() ?: 0.0
                                        val mn = min.text.toIntOrNull() ?: 0
                                        val mx = max.text.toIntOrNull() ?: mn
                                        val ok = apiAdminSetPricing(token, key, p, mn, mx, mode = "flat")
                                        if (ok) { snack = "تم الحفظ"; showEdit = false; refreshKey++ } else snack = "فشل الحفظ"
                                    }
                                }) { Text("حفظ") }
                            },
                            dismissButton = { TextButton(onClick = { showEdit = false }) { Text("إلغاء") } },
                            title = { Text("تعديل: $key") },
                            text = {
                                Column {
                                    OutlinedTextField(value = price, onValueChange = { price = it }, label = { Text("السعر المباشر") }, singleLine = true)
                                    Spacer(Modifier.height(6.dp))
                                    OutlinedTextField(value = min, onValueChange = { min = it }, label = { Text("الحد الأدنى") }, singleLine = true)
                                    Spacer(Modifier.height(6.dp))
                                    OutlinedTextField(value = max, onValueChange = { max = it }, label = { Text("الحد الأقصى") }, singleLine = true)
                                }
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun GlobalPricingCard(
    title: String,
    key: String,                 // "cat.pubg" أو "cat.ludo"
    token: String,
    overrides: Map<String, PricingOverride>,
    onSaved: () -> Unit,
    onSnack: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf(false) }
    val ov = overrides[key]

    Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(4.dp)
                .clickable { open = true },
        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
    ) {
        Text(title, Modifier.padding(16.dp), fontWeight = FontWeight.SemiBold)
    }

    if (open) {
        var price by remember { mutableStateOf(TextFieldValue((ov?.pricePerK ?: 0.0).toString())) }
        AlertDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        val p = price.text.toDoubleOrNull() ?: 0.0
                        val ok = apiAdminSetPricing(token, key, p, 0, 0, mode = "flat")
                        if (ok) { onSnack("تم الحفظ"); open = false; onSaved() } else onSnack("فشل الحفظ")
                    }
                }) { Text("حفظ") }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = { open = false }) { Text("إلغاء") }
                    if (ov != null) {
                        TextButton(onClick = {
                            scope.launch {
                                val ok = apiAdminClearPricing(token, key)
                                if (ok) { onSnack("تم حذف التعديل"); open = false; onSaved() } else onSnack("فشل الحذف")
                            }
                        }) { Text("حذف التعديل") }
                    }
                }
            },
            title = { Text(title) },
            text = {
                Column {
                    OutlinedTextField(
                        value = price,
                        onValueChange = { v -> price = v },
                        label = { Text("السعر المباشر") },
                        singleLine = true
                    )
                }
            }
        )
    }
}
/* =========================
   Theme
   ========================= */
private val Bg       = Color(0xFF0F1113)
private val Surface1 = Color(0xFF161B20)
private val OnBg     = Color(0xFFF2F4F7)
private val Accent   = Color(0xFFB388FF)
private val Good     = Color(0xFF4CAF50)
private val Bad      = Color(0xFFE53935)

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            background = Bg,
            surface = Surface1,
            primary = Accent,
            onBackground = OnBg,
            onSurface = OnBg
        ),
        content = content
    )
}

/* =========================
   نماذج/حالات
   ========================= */
enum class Tab { HOME, SERVICES, WALLET, ORDERS, SUPPORT }

data class AppNotice(
    val title: String,
    val body: String,
    val ts: Long = System.currentTimeMillis(),
    val orderId: String? = null,
    val serviceName: String? = null,
    val amount: String? = null,
    val code: String? = null,
    val status: String? = null,
    val forOwner: Boolean = false
)
data class ServiceDef(
    val uiKey: String,
    val serviceId: Long,
    val min: Int,
    val max: Int,
    val pricePerK: Double,
    val category: String
)
enum class OrderStatus { Pending, Processing, Done, Rejected, Refunded }
data class OrderItem(
    val id: String,
    val title: String,
    val quantity: Int,
    val price: Double,
    val payload: String,
    val status: OrderStatus,
    val createdAt: Long,
    val uid: String = ""            // ✅ إن توفّر من الباكند
    , val accountId: String = ""
)
/* ✅ نموذج خاص بكروت أسيا سيل (لواجهة المالك) */
data class PendingCard(
    val id: Int,
    val uid: String,
    val card: String,
    val createdAt: Long
)

private val servicesCatalog = listOf(
    ServiceDef("متابعين تيكتوك",   16256,   100, 1_000_000, 3.5, "المتابعين"),
    ServiceDef("متابعين انستغرام", 16267,   100, 1_000_000, 3.0, "المتابعين"),
    ServiceDef("لايكات تيكتوك",    12320,   100, 1_000_000, 1.0, "الايكات"),
    ServiceDef("لايكات انستغرام",  1066500, 100, 1_000_000, 1.0, "الايكات"),
    ServiceDef("مشاهدات تيكتوك",    9448,     100, 1_000_000, 0.1, "المشاهدات"),
    ServiceDef("مشاهدات انستغرام",  64686464, 100, 1_000_000, 0.1, "المشاهدات"),
    ServiceDef("مشاهدات بث تيكتوك", 14442, 100, 1_000_000, 2.0, "مشاهدات البث المباشر"),
    ServiceDef("مشاهدات بث انستا",   646464,100, 1_000_000, 2.0, "مشاهدات البث المباشر"),
    ServiceDef("رفع سكور البث",     14662, 100, 1_000_000, 2.0, "رفع سكور تيكتوك"),
    ServiceDef("اعضاء قنوات تلي",   955656, 100, 1_000_000, 3.0, "خدمات التليجرام"),
    ServiceDef("اعضاء كروبات تلي",  644656, 100, 1_000_000, 3.0, "خدمات التليجرام"),
)
private val serviceCategories = listOf(
    "قسم المتابعين",
    "قسم الايكات",
    "قسم المشاهدات",
    "قسم مشاهدات البث المباشر",
    "قسم رفع سكور تيكتوك",
    "قسم خدمات التليجرام",
    "قسم شراء رصيد ايتونز",
    "قسم شراء رصيد هاتف",
    "قسم شحن شدات ببجي",
    "قسم خدمات الودو"
)

/* =========================
   Activity
   ========================= */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {

super.onCreate(savedInstanceState)
        
        AppNotifier.ensureChannel(this)
        AppNotifier.requestPermissionIfNeeded(this)
        OrderDoneCheckWorker.schedule(this)
        // === FCM token — خطوة 1 (تشغيلياً من داخل الملف الرئيسي) ===
        // يحصّل توكن FCM ويطبعه في اللوغ ويرسله لسيرفرك لربطه مع UID المستخدم
        try {
    FirebaseMessaging.getInstance().token.addOnCompleteListener { task: com.google.android.gms.tasks.Task<String> ->
        if (task.isSuccessful) {
            val token = task.result
            android.util.Log.i("FCM", "Device FCM token: $token")
            val uid = loadOrCreateUid(this@MainActivity)
            lifecycleScope.launch {
                try {
                    val ok = apiUpdateFcmToken(uid, token)
                    android.util.Log.i("FCM", "token sent to backend: $ok")
                    if (loadOwnerMode(this@MainActivity)) {
                        try {
                            val okOwner = apiUpdateFcmToken(OWNER_UID_BACKEND, token)
                            android.util.Log.i("FCM", "owner token sent: $okOwner")
                        } catch (e: Exception) {
                            android.util.Log.w("FCM", "owner token failed: " + (e.message ?: ""))
                        }
                    }
                } catch (e: Exception) {
                    android.util.Log.w("FCM", "send token failed: " + (e.message ?: ""))
                }
            }
        } else {
            android.util.Log.w("FCM", "Failed to get FCM token", task.exception)
        }
    }
} catch (e: Exception) {
    android.util.Log.e("FCM", "Exception while getting token", e)
}

        com.zafer.smm.crash.CrashKitV2.init(application)
setContent { AppTheme { UpdatePromptHost(); AppRoot() } }
        prefetchPricingOnLaunch(this)
    }
}

/* =========================
   Root
   ========================= */

@Composable
fun AppRoot() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    // Prefetch moved to onCreate (non-Compose)

    var uid by remember { mutableStateOf(loadOrCreateUid(ctx)) }
    var ownerMode by remember { mutableStateOf(loadOwnerMode(ctx)) }
    var ownerToken by remember { mutableStateOf(loadOwnerToken(ctx)) }

    var online by remember { mutableStateOf<Boolean?>(null) }
    var toast by remember { mutableStateOf<String?>(null) }
    var showSettings by remember { mutableStateOf(false) }

    var notices by remember { mutableStateOf(loadNotices(ctx)) }
    var noticeTick by remember { mutableStateOf(0) }
    var showNoticeCenter by remember { mutableStateOf(false) }

    var lastSeenUser by remember { mutableStateOf(loadLastSeen(ctx, false)) }
    var lastSeenOwner by remember { mutableStateOf(loadLastSeen(ctx, true)) }

    val unreadUser = notices.count { !it.forOwner && it.ts > lastSeenUser }
    val unreadOwner = notices.count { it.forOwner && it.ts > lastSeenOwner }
    var topBalance by remember { mutableStateOf<Double?>(null) }
    LaunchedEffect(Unit) { try { topBalance = apiGetBalance(uid) } catch (_: Exception) { } }
var currentTab by remember { mutableStateOf(Tab.HOME) }

    LaunchedEffect(noticeTick) { try { topBalance = apiGetBalance(uid) } catch (_: Exception) { } }

    // فحص الصحة + تسجيل UID
    LaunchedEffect(Unit) {
        scope.launch { tryUpsertUid(uid) }
        while (true) {
            online = pingHealth()
            delay(15_000)
        }
    }
// تحديث فوري عند الدخول ولدى تغيّر التبويب
    LaunchedEffect(Unit) {
        try { topBalance = apiGetBalance(uid) } catch (_: Exception) { }
    }
    LaunchedEffect(currentTab) {
        try { topBalance = apiGetBalance(uid) } catch (_: Exception) { }
    }


// ✅ جلب الإشعارات من الخادم ودمجها، وتحديث العداد تلقائيًا
// ✅ جلب إشعارات المالك من الخادم عندما يكون وضع المالك مُفعّلاً
LaunchedEffect(loadOwnerMode(ctx)) {
    while (loadOwnerMode(ctx)) {
        try {
            val remoteOwner = apiFetchNotificationsByUid(OWNER_UID_BACKEND) ?: emptyList()
            val ownerMarked = remoteOwner.map { it.copy(forOwner = true) }
            val before = notices.size
            val mergedOwner = mergeNotices(notices.filter { it.forOwner }, ownerMarked)
            val mergedAll = notices.filter { !it.forOwner } + mergedOwner
            if (mergedAll.size != before) {
                notices = mergedAll
                saveNotices(ctx, notices)
                noticeTick++
            }
        } catch (_: Exception) {
            // ignore, retry
        }
        kotlinx.coroutines.delay(10_000)
    }
}

// ✅ جلب إشعارات المستخدم من الخادم ودمجها في الجرس (تمامًا مثل المالك)
LaunchedEffect(uid) {
    while (true) {
        try {
            val remoteUser = apiFetchNotificationsByUid(uid) ?: emptyList()
            val userOnly = remoteUser.map { it.copy(forOwner = false) }
            val before = notices.size
            val mergedUser = mergeNotices(notices.filter { !it.forOwner }, userOnly)
            val mergedAll = mergedUser + notices.filter { it.forOwner }
            if (mergedAll.size != before) {
                notices = mergedAll
                saveNotices(ctx, notices)
                noticeTick++
            }
        } catch (_: Exception) {
            // ignore, retry
        }
        kotlinx.coroutines.delay(10_000)
    }
}






    // ✅ مراقبة تغيّر حالة الطلبات إلى Done أثناء فتح التطبيق (تنبيه فوري داخل النظام)
    LaunchedEffect(uid) {
        // نحفظ أول مسح حتى لا نرسل إشعارات قديمة
        var initialized = false
        var lastMap = loadOrderStatusMap(ctx)
        while (true) {
            try {
                val current = (apiGetMyOrders(uid) ?: emptyList())
                val newMap = lastMap.toMutableMap()
                if (initialized) {
                    current.forEach { o ->
                        val prev = lastMap[o.id]
                        val cur = o.status.name
                        if (cur == "Done" && prev != "Done") {
                            // أرسل إشعار نظام + خزّنه في مركز الإشعارات
                            AppNotifier.notifyNow(ctx, "تم اكتمال الطلب", "تم تنفيذ ${o.title} بنجاح.")
                            val nn = AppNotice("اكتمال الطلب", "تم تنفيذ ${o.title} بنجاح.", forOwner = false)
                            notices = notices + nn
                            saveNotices(ctx, notices)
                        }
                        newMap[o.id] = cur
                    }
                    saveOrderStatusMap(ctx, newMap)
                } else {
                    // أول مرة: فقط نبني الخريطة بدون تنبيهات
                    current.forEach { o -> newMap[o.id] = o.status.name }
                    saveOrderStatusMap(ctx, newMap)
                    initialized = true
                }
                lastMap = newMap
            } catch (_: Exception) { /* ignore */ }
            delay(10_000)
        }
    }
    // Auto hide toast بعد 2 ثواني
    LaunchedEffect(toast) {
        if (toast != null) {
            delay(2000)
            toast = null
        }
    }
Column(
    modifier = Modifier
        .fillMaxSize()
        .background(Bg)
) {
    FixedTopBar(
        online = online,
        unread = if (ownerMode) unreadOwner else unreadUser,
        balance = topBalance,
        onOpenNotices = { showNoticeCenter = true },
        onOpenSettings = { showSettings = true },
        onOpenWallet = { currentTab = Tab.WALLET }
    )
    Box(
        modifier = Modifier
            .fillMaxSize()
    ) {

        when (currentTab) {
            Tab.HOME -> {
                if (ownerMode) {
                    OwnerPanel(
                        token = ownerToken,
                        onNeedLogin = { showSettings = true },
                        onToast = { toast = it }
                    )
                } else {
                    HomeScreen()
                }
            }
            Tab.SERVICES -> ServicesScreen(
                uid = uid,
                onAddNotice = {
                    notices = notices + it
                    saveNotices(ctx, notices)
                },
                onToast = { toast = it }
            )
            Tab.WALLET -> WalletScreen(
                uid = uid,
                noticeTick = noticeTick,
                onAddNotice = {
                    notices = notices + it
                    saveNotices(ctx, notices)
                },
                onToast = { toast = it }
            )
            Tab.ORDERS -> OrdersScreen(uid = uid)
            Tab.SUPPORT -> SupportScreen()
        }

        BottomNavBar(
            current = currentTab,
            onChange = { currentTab = it },
            modifier = Modifier.align(Alignment.BottomCenter)
        )

        toast?.let { msg ->
            Box(Modifier.fillMaxSize()) {
                Surface(
                    color = Surface1, tonalElevation = 6.dp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 90.dp)
                ) {
                    Text(msg, Modifier.padding(horizontal = 16.dp, vertical = 10.dp), color = OnBg)
                }
            }
        }
    
    }
}


// removed duplicate scope
    if (showSettings) {
        SettingsDialog(
            uid = uid,
            ownerMode = ownerMode,
            onUserLogin = { newUid ->
                saveUid(ctx, newUid)
                uid = newUid
                ownerMode = false
                scope.launch { try { topBalance = apiGetBalance(newUid) } catch (_: Exception) {} }
                            },
            onOwnerLogin = { token ->
                ownerToken = token
                ownerMode = true
                saveOwnerMode(ctx, true)
                saveOwnerToken(ctx, token)
            },
            onOwnerLogout = {
                ownerToken = null
                ownerMode = false
                saveOwnerMode(ctx, false)
                saveOwnerToken(ctx, null)
            },
            onDismiss = { showSettings = false }
        )
    }

    if (showNoticeCenter) {
        NoticeCenterDialog(
            notices = if (ownerMode) notices.filter { it.forOwner } else notices.filter { !it.forOwner },
            onClear = {
                notices = if (ownerMode) notices.filter { !it.forOwner } else notices.filter { it.forOwner }
                saveNotices(ctx, notices)
            },
            onDismiss = {
                if (ownerMode) {
                    lastSeenOwner = System.currentTimeMillis()
                    saveLastSeen(ctx, true, lastSeenOwner)
                } else {
                    lastSeenUser = System.currentTimeMillis()
                    saveLastSeen(ctx, false, lastSeenUser)
                }
                showNoticeCenter = false
            }
        )
    }
}

/* =========================
   شاشات عامة
   ========================= */

@Composable private fun HomeScreen() {
    Box(Modifier.fillMaxSize().background(Bg)) {
        HomeAnnouncementsList()
    }
}


@Composable private fun SupportScreen() {
    val uri = LocalUriHandler.current
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("الدعم", color = OnBg, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        Text("للتواصل أو الاستفسار اختر إحدى الطرق التالية:", color = OnBg)
        Spacer(Modifier.height(12.dp))
        ContactCard(
            title = "واتساب", subtitle = "+964 776 341 0970",
            actionText = "افتح واتساب", onClick = { uri.openUri("https://wa.me/9647763410970") }, icon = Icons.Filled.Call
        )
        Spacer(Modifier.height(10.dp))
        ContactCard(
            title = "تيليجرام", subtitle = "@z396r",
            actionText = "افتح تيليجرام", onClick = { uri.openUri("https://t.me/z396r") }, icon = Icons.Filled.Send
        )
    }
}
@Composable private fun ContactCard(
    title: String, subtitle: String, actionText: String,
    onClick: () -> Unit, icon: androidx.compose.ui.graphics.vector.ImageVector
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        colors = CardDefaults.cardColors(
            containerColor = Surface1,
            contentColor = OnBg
        )
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = Accent, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold, color = OnBg)
                Text(subtitle, color = Dim, fontSize = 13.sp)
            }
            TextButton(onClick = onClick) { Text(actionText) }
        }
    }
}




// =========================
// Announcements (App-wide)
// =========================
data class Announcement(val id: Int? = null, val title: String?, val body: String, val createdAt: Long)


private suspend fun apiAdminCreateAnnouncement(token: String, title: String?, body: String): Boolean {
    val obj = org.json.JSONObject().put("body", body)
    if (!title.isNullOrBlank()) obj.put("title", title)
    val (code, _) = httpPost(AdminEndpoints.announcementCreate, obj, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminUpdateAnnouncement(token: String, id: Int, title: String?, body: String): Boolean {
    val obj = org.json.JSONObject().put("body", body)
    if (!title.isNullOrBlank()) obj.put("title", title)
    val (code, _) = httpPost(AdminEndpoints.announcementUpdate(id), obj, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
private suspend fun apiAdminDeleteAnnouncement(token: String, id: Int): Boolean {
    val (code, _) = httpPost(AdminEndpoints.announcementDelete(id), org.json.JSONObject(), headers = mapOf("x-admin-password" to token))
    return code in 200..299
}



private suspend fun apiFetchAnnouncements(limit: Int = 50): List<Announcement> {
    val (code, txt) = httpGet(AdminEndpoints.announcementsList + "?limit=" + limit)
    if (code !in 200..299 || txt == null) return emptyList()
    return try {
        val arr = org.json.JSONArray(txt.trim())
        val out = mutableListOf<Announcement>()

        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            out.add(
                Announcement(
                    title = if (o.has("title")) o.optString("title", null) else null,
                    body = o.optString("body",""),
                    createdAt = o.optLong("created_at", 0L)
                )
            )
        }
        out
    } catch (_: Exception) { emptyList() }
}

private suspend fun apiFetchAdminAnnouncements(token: String, limit: Int = 200): List<Announcement> {
    val (code, txt) = httpGet(AdminEndpoints.announcementsAdminList + "?limit=" + limit, headers = mapOf("x-admin-password" to token))
    if (code !in 200..299 || txt == null) return emptyList()
    return try {
        val arr = org.json.JSONArray(txt.trim())
        val out = mutableListOf<Announcement>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val idValue = if (o.has("id")) {
                val tmp = o.optInt("id", -1)
                if (tmp > 0) tmp else null
            } else null
            out.add(
                Announcement(
                    id = idValue,
                    title = if (o.has("title")) o.optString("title", null) else null,
                    body = o.optString("body",""),
                    createdAt = o.optLong("created_at", 0L)
                )
            )
        }
        out
    } catch (_: Exception) { emptyList() }
}




@Composable
private fun HomeAnnouncementsList() {
    var list by remember { mutableStateOf<List<Announcement>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        loading = true; err = null
        try {
            list = apiFetchAnnouncements(50)
        } catch (e: Exception) {
            err = "تعذر جلب الإعلانات"
        } finally {
            loading = false
        }
    }
    when {
        loading -> Box(Modifier.fillMaxWidth().padding(16.dp)) { CircularProgressIndicator(Modifier.align(Alignment.Center)) }
        err != null -> Text(err!!, color = Bad, modifier = Modifier.padding(16.dp))
        list.isEmpty() -> Text("لا توجد إعلانات حالياً", color = Dim, modifier = Modifier.padding(16.dp))
        else -> {
            LazyColumn(
                modifier = Modifier.fillMaxSize().background(Bg),
                contentPadding = PaddingValues(vertical = 8.dp)
            ) {
                items(list.size) { idx ->
                    val ann = list[idx]
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        shape = RoundedCornerShape(16.dp)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(ann.title ?: "إعلان مهم 📢", fontSize = 18.sp, color = OnBg, fontWeight = FontWeight.Bold)
                            Spacer(Modifier.height(8.dp))
                            Text(ann.body, fontSize = 16.sp, color = OnBg)
                            Spacer(Modifier.height(8.dp))
                            val ts = if (ann.createdAt > 0) ann.createdAt else System.currentTimeMillis()
                            val formatted = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.getDefault())
                                .format(java.util.Date(ts))
                            Text(formatted, fontSize = 10.sp, color = Dim)
                        }
                    }
                }
            }
        }
    }
}


@Composable
private fun AdminAnnouncementScreen(token: String, onBack: () -> Unit, onSent: () -> Unit = {}) {
    val scope = rememberCoroutineScope()
    var title by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("إعلان التطبيق", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = OnBg, modifier = Modifier.weight(1f))
            TextButton(onClick = onBack) { Text("رجوع") }
        }
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = title, onValueChange = { title = it }, singleLine = true,
            label = { Text("العنوان (اختياري)") }, modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = body, onValueChange = { body = it },
            label = { Text("نص الإعلان") }, minLines = 5, modifier = Modifier.fillMaxWidth()
        )
        if (error != null) { Spacer(Modifier.height(6.dp)); Text(error!!, color = Bad, fontSize = 10.sp) }
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = {
                if (body.isBlank()) { error = "النص مطلوب"; return@Button }
                scope.launch {
                    sending = true; error = null
                    val ok = apiAdminCreateAnnouncement(token, title.ifBlank { null }, body)
                    sending = false
                    if (ok) { onSent(); onBack() } else { error = "فشل إرسال الإعلان" }
                }
            },
            enabled = !sending
        ) { Text(if (sending) "جاري الإرسال..." else "إرسال") }
    }
}


/* =========================
   الشريط العلوي يمين — (عمودي)
   ========================= */


/* =========================
   تبويب الخدمات + الطلب اليدوي
   ========================= */
@Composable private fun ServicesScreen(
    uid: String,
    onAddNotice: (AppNotice) -> Unit,
    onToast: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var selectedCategory by remember { mutableStateOf<String?>(null) }
    var selectedService by remember { mutableStateOf<ServiceDef?>(null) }

    if (selectedCategory == null) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
            Text("الخدمات", color = OnBg, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))
            serviceCategories.forEach { cat ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 8.dp)
                        .clickable { selectedCategory = cat },
                    colors = CardDefaults.cardColors(
                        containerColor = Surface1,
                        contentColor = OnBg
                    )
                ) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.ChevronLeft, null, tint = Accent)
                        Spacer(Modifier.width(8.dp))
                        Text(cat, fontWeight = FontWeight.SemiBold, color = OnBg)
                    }
                }
            }
        }
        return
    }

    val inCat = when (selectedCategory) {
        "قسم المتابعين"            -> servicesCatalog.filter { it.category == "المتابعين" }
        "قسم الايكات"              -> servicesCatalog.filter { it.category == "الايكات" }
        "قسم المشاهدات"            -> servicesCatalog.filter { it.category == "المشاهدات" }
        "قسم مشاهدات البث المباشر" -> servicesCatalog.filter { it.category == "مشاهدات البث المباشر" }
        "قسم رفع سكور تيكتوك"     -> servicesCatalog.filter { it.category == "رفع سكور تيكتوك" }
        "قسم خدمات التليجرام"      -> servicesCatalog.filter { it.category == "خدمات التليجرام" }
        else -> emptyList()
    }

    // Overlay live pricing on top of catalog using produceState (no try/catch around composables)
// Overlay live pricing on top of catalog with cache + version (same behavior as manual sections)
    val apiCtx = LocalContext.current
    val keys = remember(inCat, selectedCategory) { inCat.map { it.uiKey } }
    var apiEffectiveMap by remember(selectedCategory) { mutableStateOf<Map<String, PublicPricingEntry>>(emptyMap()) }

    LaunchedEffect(selectedCategory) {
        val cat = selectedCategory ?: ""
        val cached = ApiPricingCache.load(apiCtx, cat)
        if (cached.isNotEmpty()) apiEffectiveMap = cached

        val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
        val localVer = ApiPricingCache.getVersion(apiCtx, cat)
        val needRefresh = (srvVer > 0L && srvVer != localVer) || apiEffectiveMap.isEmpty()

        if (needRefresh) {
            val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
            if (fresh.isNotEmpty()) {
                apiEffectiveMap = fresh
                ApiPricingCache.save(apiCtx, cat, fresh)
                if (srvVer > 0L) ApiPricingCache.saveVersion(apiCtx, cat, srvVer)
            }
        }
    }

    val listToShow = remember(inCat, apiEffectiveMap) {
        inCat.map { s ->
            val ov = apiEffectiveMap[s.uiKey]
            if (ov != null) s.copy(min = ov.minQty, max = ov.maxQty, pricePerK = ov.pricePerK) else s
        }
    }
    if (listToShow.isNotEmpty()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selectedCategory = null }) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg)
                }
                Spacer(Modifier.width(6.dp))
                Text(selectedCategory!!, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
            }
            Spacer(Modifier.height(10.dp))

            listToShow.forEach { svc ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 8.dp)
                        .clickable { selectedService = svc },
                    colors = CardDefaults.cardColors(
                        containerColor = Surface1,
                        contentColor = OnBg
                    )
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text(svc.uiKey, fontWeight = FontWeight.SemiBold, color = OnBg)
                        Text("الكمية: ${svc.min} - ${svc.max}", color = Dim, fontSize = 10.sp)
                        Text("السعر لكل 1000: ${svc.pricePerK}\$", color = Dim, fontSize = 10.sp)
                    }
                }
            }
        }
    } else {
        ManualSectionsScreen(
            title = selectedCategory!!,
            uid = uid,
            onBack = { selectedCategory = null },
            onToast = onToast,
            onAddNotice = onAddNotice
        )
    }

    selectedService?.let { svc ->
        ServiceOrderDialog(
            uid = uid, service = svc,
            onDismiss = { selectedService = null },
            onOrdered = { ok, msg ->
                onToast(msg)
                if (ok) {
                    onAddNotice(AppNotice("طلب جديد (${svc.uiKey})", "تم استلام طلبك وسيتم تنفيذه قريبًا.", forOwner = false))
                    onAddNotice(AppNotice("طلب خدمات معلّق", "طلب ${svc.uiKey} من UID=$uid بانتظار المعالجة/التنفيذ", forOwner = true))
                }
            }
        )
    }
}

@Composable private fun ServiceOrderDialog(
    uid: String, service: ServiceDef,
    onDismiss: () -> Unit,
    onOrdered: (Boolean, String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var link by remember { mutableStateOf("") }
    var qtyText by remember { mutableStateOf(service.min.toString()) }
    val qty = qtyText.toIntOrNull() ?: 0
    val price = ceil((qty / 1000.0) * service.pricePerK * 100) / 100.0

    var loading by remember { mutableStateOf(false) }
    var userBalance by remember { mutableStateOf<Double?>(null) }

    LaunchedEffect(Unit) { userBalance = apiGetBalance(uid) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(enabled = !loading, onClick = {
                if (link.isBlank()) { onOrdered(false, "الرجاء إدخال الرابط"); return@TextButton }
                if (qty < service.min || qty > service.max) { onOrdered(false, "الكمية يجب أن تكون بين ${service.min} و ${service.max}"); return@TextButton }
                val bal = userBalance ?: 0.0
                if (bal < price) { onOrdered(false, "رصيدك غير كافٍ. السعر: $price\$ | رصيدك: ${"%.2f".format(bal)}\$"); return@TextButton }

                loading = true
                val svcName = service.uiKey
                scope.launch {
                    val ok = apiCreateProviderOrder(
                        uid = uid,
                        serviceId = service.serviceId,
                        serviceName = svcName,
                        link = link,
                        quantity = qty,
                        price = price
                    )
                    loading = false
                    if (ok) onOrdered(true, "تم إرسال الطلب بنجاح.")
                    else onOrdered(false, "فشل إرسال الطلب.")
                    onDismiss()
                }
            }) { Text(if (loading) "يرسل" else "شراء") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("إلغاء") } },
        title = { Text(service.uiKey) },
        text = {
            Column {
                Text("الكمية بين ${service.min} و ${service.max}", color = Dim, fontSize = 10.sp)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    value = qtyText,
                    onValueChange = { s -> if (s.all { it.isDigit() }) qtyText = s },
                    label = { Text("الكمية") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        cursorColor = Accent,
                        focusedBorderColor = Accent, unfocusedBorderColor = Dim,
                        focusedLabelColor = OnBg, unfocusedLabelColor = Dim
                    )
                )
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    value = link, onValueChange = { link = it },
                    label = { Text("الرابط (أرسل الرابط وليس اليوزر)") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        cursorColor = Accent,
                        focusedBorderColor = Accent, unfocusedBorderColor = Dim,
                        focusedLabelColor = OnBg, unfocusedLabelColor = Dim
                    )
                )
                // === Notes for Instagram & Telegram services ===
                if (service.uiKey.contains("انستغرام")) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "يرجى إطفاء زر 'تم' (تم التقييد) داخل حسابك الانستغرام قبل إرسال رابط الخدمة لضمان إكمال طلبك!",
                        color = Dim, fontSize = 10.sp
                    )
                }
                if (service.uiKey.contains("تلي") || service.uiKey.contains("تيليجرام") || service.uiKey.contains("التليجرام")) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "الرجاء إرسال رابط دعوة انضمام وليس رابط القناة ام المجموعة أو اسم المستخدم (مثل: https://t.me/+xxxx).\n"
                        + "خطوات إنشاء رابط الدعوة الخاص:\n"
                        + "1. ادخل إلى القناة او المجموعة\n"
                        + "2. اختر خيار المشتركون.\n"
                        + "3. اضغط على الدعوة عبر رابط خاص.\n"
                        + "4. أنشئ رابط دعوة جديد.",
                        color = Dim, fontSize = 10.sp
                    )
                }
    
                Spacer(Modifier.height(8.dp))
                Text("السعر التقريبي: $price\$", fontWeight = FontWeight.SemiBold, color = OnBg)
                Spacer(Modifier.height(4.dp))
                Text("رصيدك الحالي: ${userBalance?.let { "%.2f".format(it) } ?: ""}\$", color = Dim, fontSize = 10.sp)
            }
        }
    )
}

/* =========================
   Amount Picker (iTunes & Phone Cards)
   ========================= */
data class AmountOption(val label: String, val usd: Int)

private fun priceForItunes(usd: Int): Double {
    return usd.toDouble()
}
private fun priceForAtheerOrAsiacell(usd: Int): Double {
    return usd.toDouble()
}
private fun priceForKorek(usd: Int): Double {
    return usd.toDouble()
}

@Composable
private fun AmountGrid(
    title: String,
    subtitle: String,
    labelSuffix: String = "",
    amounts: List<Int>,
    keyPrefix: String? = null,
    priceOf: (Int) -> Double,
    onSelect: (usd: Int, price: Double) -> Unit,
    onBack: () -> Unit
) {
    
    
    // --- Dynamic pricing for topups with local cache + version ---
    val ctx = LocalContext.current
    val effectiveMap: Map<String, PublicPricingEntry> = if (keyPrefix != null) {
        val keys = remember(amounts, keyPrefix) { amounts.map { keyPrefix + it } }
        var cached by remember(keys) { mutableStateOf<Map<String, PublicPricingEntry>>(emptyMap()) }
        var map by remember(keys) { mutableStateOf<Map<String, PublicPricingEntry>>(emptyMap()) }

        LaunchedEffect(keys) {
            // load from cache immediately
            cached = PricingCache.load(ctx, keyPrefix!!, amounts)
            if (cached.isNotEmpty()) map = cached

            val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
            val localVer = PricingCache.getVersion(ctx, keyPrefix!!, amounts)
            val needRefresh = (srvVer > 0L && srvVer != localVer) || map.isEmpty()

            if (needRefresh) {
                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                if (fresh.isNotEmpty()) {
                    map = fresh
                    PricingCache.save(ctx, keyPrefix!!, amounts, fresh)
                    if (srvVer > 0L) PricingCache.saveVersion(ctx, keyPrefix!!, amounts, srvVer)
                }
            }
        }
        map
    } else emptyMap()

    fun effectiveFor(usd: Int): Pair<Int, Double> {
        val entry = if (keyPrefix != null) effectiveMap[keyPrefix + usd] else null
        val effUsd = if (entry != null && entry.minQty > 0) entry.minQty else usd
        val effPrice = if (entry != null && entry.pricePerK > 0.0) entry.pricePerK else priceOf(effUsd)
        return Pair(effUsd, effPrice)
    }
    // ---------------------------------------------------------------------------
    
Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .padding(bottom = 100.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Column {
                Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
                if (subtitle.isNotBlank()) Text(subtitle, color = Dim, fontSize = 10.sp)
            }
        }
        Spacer(Modifier.height(10.dp))

        amounts.chunked(2).forEach { pair ->
            Row(Modifier.fillMaxWidth()) {
                pair.forEach { usd ->
                    val (effUsd, price) = effectiveFor(usd)
                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .padding(4.dp)
                            .clickable { onSelect(effUsd, price) },
                        colors = CardDefaults.cardColors(containerColor = Surface1)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            val label = if (labelSuffix.isBlank()) "$${effUsd}" else "$${effUsd} $labelSuffix"
                            Text(label, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            run {
                                val priceTxt = if (price % 1.0 == 0.0) price.toInt().toString() else "%.2f".format(price)
                                Text("السعر: \$${priceTxt}", color = Dim, fontSize = 10.sp)
                            }
                        }
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f).padding(4.dp))
            }
        }
    }
}

@Composable
private fun ConfirmAmountDialog(
    sectionTitle: String,
    usd: Int,
    price: Double,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onConfirm) { Text("تأكيد الشراء") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("إلغاء") } },
        title = { Text(sectionTitle, color = OnBg) },
        text = {
            Column {
                Text("القيمة المختارة: ${usd}$", color = OnBg, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text(String.format(java.util.Locale.getDefault(), "السعر المستحق: %.2f$", price), color = Dim)
                Spacer(Modifier.height(8.dp))
                Text("سيتم إرسال الطلب للمراجعة من قِبل المالك وسيصلك إشعار عند التنفيذ.", color = Dim, fontSize = 10.sp)
            }
        }
    )

}



// قائمة مبالغ افتراضية مشتركة لاستخدامها في ايتونز/رصيد الهاتف
private val COMMON_AMOUNTS = listOf(5,10,15,20,25,30,40,50,100)
/* الأقسام اليدوية (ايتونز/هاتف/ببجي/لودو) */

/* =========================
   Package Picker (PUBG / Ludo)
   ========================= */
data class PackageOption(val label: String, val priceUsd: Double)

val pubgPackages = listOf(
    PackageOption("60 شدة", 2.0),
    PackageOption("325 شدة", 9.0),
    PackageOption("660 شدة", 15.0),
    PackageOption("1800 شدة", 40.0),
    PackageOption("3850 شدة", 55.0),
    PackageOption("8100 شدة", 100.0),
    PackageOption("16200 شدة", 185.0)
)
val ludoDiamondsPackages = listOf(
    PackageOption("810 الماسة", 5.0),
    PackageOption("2280 الماسة", 10.0),
    PackageOption("5080 الماسة", 20.0),
    PackageOption("12750 الماسة", 35.0),
    PackageOption("27200 الماسة", 85.0),
    PackageOption("54900 الماسة", 165.0),
    PackageOption("164800 الماسة", 475.0),
    PackageOption("275400 الماسة", 800.0)
)
val ludoGoldPackages = listOf(
    PackageOption("66680 ذهب", 5.0),
    PackageOption("219500 ذهب", 10.0),
    PackageOption("1443000 ذهب", 20.0),
    PackageOption("3627000 ذهب", 35.0),
    PackageOption("9830000 ذهب", 85.0),
    PackageOption("24835000 ذهب", 165.0),
    PackageOption("74550000 ذهب", 475.0),
    PackageOption("124550000 ذهب", 800.0)
)

/* ===== App launch prefetch for pricing (version-based, non-Compose) ===== */
private fun prefetchPricingOnLaunch(ctx: android.content.Context) {
    // Run in background; avoid blocking UI
    kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
        val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
        if (srvVer <= 0L) return@launch

        // --- Topup providers ---
        val topupPrefixes = listOf("topup.itunes.", "topup.atheer.", "topup.asiacell.", "topup.zain.", "topup.korek.")
        for (prefix in topupPrefixes) {
            val amounts = COMMON_AMOUNTS
            val localVer = PricingCache.getVersion(ctx, prefix, amounts)
            if (localVer != srvVer) {
                val keys = amounts.map { prefix + it }
                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                if (fresh.isNotEmpty()) {
                    PricingCache.save(ctx, prefix, amounts, fresh)
                    PricingCache.saveVersion(ctx, prefix, amounts, srvVer)
                }
            }
        }

        // --- PUBG ---
        run {
            val amounts = pubgPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
            val prefix = "pkg.pubg."
            val localVer = PricingCache.getVersion(ctx, prefix, amounts)
            if (localVer != srvVer) {
                val keys = amounts.map { prefix + it }
                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                if (fresh.isNotEmpty()) {
                    PricingCache.save(ctx, prefix, amounts, fresh)
                    PricingCache.saveVersion(ctx, prefix, amounts, srvVer)
                }
            }
        }

        // --- Ludo (Diamonds & Gold) ---
        run {
            val diaAmounts = ludoDiamondsPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
            val goldAmounts = ludoGoldPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
            val diaPrefix = "pkg.ludo.diamonds."
            val goldPrefix = "pkg.ludo.gold."

            val localDia = PricingCache.getVersion(ctx, diaPrefix, diaAmounts)
            if (localDia != srvVer) {
                val keys = diaAmounts.map { diaPrefix + it }
                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                if (fresh.isNotEmpty()) {
                    PricingCache.save(ctx, diaPrefix, diaAmounts, fresh)
                    PricingCache.saveVersion(ctx, diaPrefix, diaAmounts, srvVer)
                }
            }

            val localGold = PricingCache.getVersion(ctx, goldPrefix, goldAmounts)
            if (localGold != srvVer) {
                val keys = goldAmounts.map { goldPrefix + it }
                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                if (fresh.isNotEmpty()) {
                    PricingCache.save(ctx, goldPrefix, goldAmounts, fresh)
                    PricingCache.saveVersion(ctx, goldPrefix, goldAmounts, srvVer)
                }
            }
        }
    }
}
/* ===== End prefetch ===== */
/* ===== Helpers for PUBG/Ludo package overrides ===== */
private fun extractDigits(s: String): String = s.filter { it.isDigit() }

@Composable
private fun packagesWithOverrides(
    base: List<PackageOption>,
    keyPrefix: String,
    unit: String
): List<PackageOption> {
    val ctx = LocalContext.current
    // Cache-only: read overrides from PricingCache that were prefetched by the screen-level effect.
    val amounts = remember(base) { base.mapNotNull { opt -> opt.label.filter { it.isDigit() }.toIntOrNull() } }
    val map = remember(keyPrefix, amounts) { PricingCache.load(ctx, keyPrefix, amounts) }
    return remember(base, map) {
        base.map { opt ->
            val qtyStr = opt.label.filter { it.isDigit() }
            val k = if (qtyStr.isEmpty()) "" else "$keyPrefix$qtyStr"
            val ov = map[k]
            val newQty = ov?.minQty?.takeIf { it > 0 } ?: qtyStr.toIntOrNull() ?: 0
            val newPrice = ov?.pricePerK ?: opt.priceUsd.toDouble()
            val newLabel = if (newQty > 0) "$newQty $unit" else opt.label
            PackageOption(newLabel, newPrice)
        }
    }
}

@Composable
fun PackageGrid(
    title: String,
    subtitle: String,
    packages: List<PackageOption>,
    onSelect: (PackageOption) -> Unit,
    onBack: () -> Unit
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Column {
                Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
                if (subtitle.isNotBlank()) Text(subtitle, color = Dim, fontSize = 10.sp)
            }
        }
        Spacer(Modifier.height(12.dp))

        val rows = packages.chunked(2)
        rows.forEach { pair ->
            Row(Modifier.fillMaxWidth()) {
                pair.forEach { opt ->
                    Card(
                        modifier = Modifier.weight(1f)
                            .padding(4.dp)
                            .clickable { onSelect(opt) },
                        colors = CardDefaults.cardColors(containerColor = Surface1)
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Text(opt.label, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            run {
                            val p = opt.priceUsd
                            val priceTxt = if (p % 1.0 == 0.0) p.toInt().toString() else "%.2f".format(p)
                            Text("السعر: $${priceTxt}", color = Dim, fontSize = 10.sp)
                        }
                        }
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
fun ConfirmPackageDialog(
    sectionTitle: String,
    label: String,
    priceUsd: Int,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onConfirm) { Text("تأكيد الشراء") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("إلغاء") } },
        title = { Text(sectionTitle, color = OnBg) },
        text = {
            Column {
                Text("الباقة المختارة: $label", color = OnBg, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text(String.format(java.util.Locale.getDefault(), "السعر المستحق: %.2f$", priceUsd), color = Dim)
                Spacer(Modifier.height(8.dp))
                Text("سيتم إرسال الطلب للمراجعة من قِبل المالك وسيصلك إشعار عند التنفيذ.", color = Dim, fontSize = 10.sp)
            }
        }
    )
}

@Composable
fun ConfirmPackageIdDialog(
    sectionTitle: String,
    label: String,
    priceUsd: Double,
    onConfirm: (accountId: String) -> Unit,
    onDismiss: () -> Unit
) {
    var accountId by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                enabled = accountId.trim().isNotEmpty(),
                onClick = { onConfirm(accountId.trim()) }
            ) { Text("تأكيد الشراء") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("إلغاء") } },
        title = { Text(sectionTitle, color = OnBg) },
        text = {
            Column {
                Text("الباقة المختارة: $label", color = OnBg, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                Text(String.format(java.util.Locale.getDefault(), "السعر المستحق: %.2f$", priceUsd), color = Dim)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = accountId,
                    onValueChange = { accountId = it },
                    singleLine = true,
                    label = { Text("معرّف اللاعب / Game ID") }
                )
                Spacer(Modifier.height(6.dp))
                Text("أدخل رقم الحساب بدقة. الطلب لن يُرسل بدون هذا الحقل.", color = Dim, fontSize = 10.sp)
            }
        }
    )
}

@Composable private fun ManualSectionsScreen(
    title: String,
    uid: String,
    onBack: () -> Unit,
    onToast: (String) -> Unit,
    onAddNotice: (AppNotice) -> Unit
) {
    val scope = rememberCoroutineScope()
    var selectedManualFlow by remember { mutableStateOf<String?>(null) }
    var pendingUsd by remember { mutableStateOf<Int?>(null) }
    var pendingPrice by remember { mutableStateOf<Double?>(null) }
    var pendingPkgLabel by remember { mutableStateOf<String?>(null) }
    var pendingPkgPrice by remember { mutableStateOf<Double?>(null) }

    val items = when (title) {
        "قسم شراء رصيد ايتونز" -> listOf("شراء رصيد ايتونز")
        "قسم شراء رصيد هاتف"  -> listOf("شراء رصيد اثير", "شراء رصيد اسياسيل", "شراء رصيد كورك")
        "قسم شحن شدات ببجي"    -> listOf("شحن شدات ببجي")
        "قسم خدمات الودو"       -> listOf("شراء الماسات لودو", "شراء ذهب لودو")
        else -> emptyList()
    }
    if (selectedManualFlow == null) {

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))

        items.forEach { name ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
                    .clickable {
                        selectedManualFlow = name
                    },
                colors = CardDefaults.cardColors(
                    containerColor = Surface1,
                    contentColor = OnBg
                )
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.ChevronLeft, null, tint = Accent)
                    Spacer(Modifier.width(8.dp))
                    Text(name, fontWeight = FontWeight.SemiBold, color = OnBg)
                }
            }
        }
    }

    // ----- Manual flows UI -----
    }

    // ---- Manual flows moved outside the null-check ----
        when (selectedManualFlow) {
            "شراء رصيد ايتونز" -> {
                AmountGrid(
                    title = "شراء رصيد ايتونز",
                    subtitle = "اختر المبلغ",
                    labelSuffix = "ايتونز",
                    keyPrefix = "topup.itunes.",

                    amounts = COMMON_AMOUNTS,
                    priceOf = { usd -> usd.toDouble() },
                    onSelect = { usd, price ->
                        pendingUsd = usd
                        pendingPrice = price
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شراء رصيد اثير" -> {
                AmountGrid(
                    title = "شراء رصيد اثير",
                    subtitle = "اختر المبلغ",
                    labelSuffix = "اثير",
                    keyPrefix = "topup.atheer.",

                    amounts = COMMON_AMOUNTS,
                    priceOf = { usd -> usd.toDouble() },
                    onSelect = { usd, price ->
                        pendingUsd = usd
                        pendingPrice = price
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شراء رصيد اسياسيل" -> {
                AmountGrid(
                    title = "شراء رصيد اسياسيل",
                    subtitle = "اختر المبلغ",
                    labelSuffix = "اسياسيل",
                    keyPrefix = "topup.asiacell.",

                    amounts = COMMON_AMOUNTS,
                    priceOf = { usd -> usd.toDouble() },
                    onSelect = { usd, price ->
                        pendingUsd = usd
                        pendingPrice = price
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شراء رصيد كورك" -> {
                AmountGrid(
                    title = "شراء رصيد كورك",
                    subtitle = "اختر المبلغ",
                    labelSuffix = "كورك",
                    keyPrefix = "topup.korek.",

                    amounts = COMMON_AMOUNTS,
                    priceOf = { usd -> usd.toDouble() },
                    onSelect = { usd, price ->
                        pendingUsd = usd
                        pendingPrice = price
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شحن شدات ببجي" -> {
                // One-time version check & cache refresh for PUBG (on screen entry)
                run {
                    val ctx = LocalContext.current
                    LaunchedEffect("pubg_once") {
                        val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
                        if (srvVer > 0L) {
                            val prefix = "pkg.pubg."
                            val amounts = pubgPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
                            val localVer = PricingCache.getVersion(ctx, prefix, amounts)
                            if (localVer != srvVer) {
                                val keys = amounts.map { prefix + it }
                                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                                if (fresh.isNotEmpty()) {
                                    PricingCache.save(ctx, prefix, amounts, fresh)
                                    PricingCache.saveVersion(ctx, prefix, amounts, srvVer)
                                }
                            }
                        }
                    }
                }
                PackageGrid(
                    title = "شحن شدات ببجي",
                    subtitle = "اختر الباقة",
                    packages = packagesWithOverrides(pubgPackages, "pkg.pubg.", "شدة"),
                    onSelect = { opt ->
                        pendingPkgLabel = opt.label
                        pendingPkgPrice = opt.priceUsd
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شراء الماسات لودو" -> {
                // One-time version check & cache refresh for Ludo Diamonds (on screen entry)
                run {
                    val ctx = LocalContext.current
                    LaunchedEffect("ludo_dia_once") {
                        val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
                        if (srvVer > 0L) {
                            val prefix = "pkg.ludo.diamonds."
                            val amounts = ludoDiamondsPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
                            val localVer = PricingCache.getVersion(ctx, prefix, amounts)
                            if (localVer != srvVer) {
                                val keys = amounts.map { prefix + it }
                                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                                if (fresh.isNotEmpty()) {
                                    PricingCache.save(ctx, prefix, amounts, fresh)
                                    PricingCache.saveVersion(ctx, prefix, amounts, srvVer)
                                }
                            }
                        }
                    }
                }
                PackageGrid(
                    title = "شراء الماسات لودو",
                    subtitle = "اختر الباقة",
                    packages = packagesWithOverrides(ludoDiamondsPackages, "pkg.ludo.diamonds.", "الماسة"),
                    onSelect = { opt ->
                        pendingPkgLabel = opt.label
                        pendingPkgPrice = opt.priceUsd
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شراء ذهب لودو" -> {
                // One-time version check & cache refresh for Ludo Gold (on screen entry)
                run {
                    val ctx = LocalContext.current
                    LaunchedEffect("ludo_gold_once") {
                        val srvVer = try { apiPublicPricingVersion() } catch (_: Throwable) { 0L }
                        if (srvVer > 0L) {
                            val prefix = "pkg.ludo.gold."
                            val amounts = ludoGoldPackages.mapNotNull { extractDigits(it.label).toIntOrNull() }
                            val localVer = PricingCache.getVersion(ctx, prefix, amounts)
                            if (localVer != srvVer) {
                                val keys = amounts.map { prefix + it }
                                val fresh = try { /*DISABLED_LIVE_CALL*/ apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
                                if (fresh.isNotEmpty()) {
                                    PricingCache.save(ctx, prefix, amounts, fresh)
                                    PricingCache.saveVersion(ctx, prefix, amounts, srvVer)
                                }
                            }
                        }
                    }
                }
                PackageGrid(
                    title = "شراء ذهب لودو",
                    subtitle = "اختر الباقة",
                    packages = packagesWithOverrides(ludoGoldPackages, "pkg.ludo.gold.", "ذهب"),
                    onSelect = { opt ->
                        pendingPkgLabel = opt.label
                        pendingPkgPrice = opt.priceUsd
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }

        }

    
    if (selectedManualFlow in listOf("شحن شدات ببجي","شراء الماسات لودو","شراء ذهب لودو") &&
        pendingPkgLabel != null && pendingPkgPrice != null) {
    ConfirmPackageIdDialog(
        sectionTitle = selectedManualFlow!!,
        label = pendingPkgLabel!!,
        priceUsd = pendingPkgPrice!!,
        onConfirm = { accountId ->
            val flow = selectedManualFlow
            val priceInt = pendingPkgPrice
            scope.launch {
                if (flow != null && priceInt != null) {
                    val bal = apiGetBalance(uid) ?: 0.0
                    if (bal < priceInt) {
                        onToast("رصيدك غير كافٍ. السعر: ${'$'}$priceInt | رصيدك: ${"%.2f".format(bal)}${'$'}")
                    } else {
                        val product = when (flow) {
                            "شحن شدات ببجي" -> "pubg_uc"
                            "شراء الماسات لودو" -> "ludo_diamonds"
                            "شراء ذهب لودو" -> "ludo_gold"
                            else -> "manual"
                        }
                        val (ok, txt) = apiCreateManualPaidOrder(uid, product, priceInt.toDouble(), accountId)
                        if (ok) {
                            onToast("تم استلام طلبك (${pendingPkgLabel}).")
                            onAddNotice(AppNotice("طلب معلّق", "تم إرسال طلب ${pendingPkgLabel} للمراجعة.", forOwner = false))
                            onAddNotice(AppNotice("طلب جديد", "طلب ${pendingPkgLabel} من UID=${uid} (Player: ${accountId}) يحتاج مراجعة.", forOwner = true))
                        } else {
                            val msg = (txt ?: "").lowercase()
                            if (msg.contains("insufficient")) {
                                onToast("رصيدك غير كافٍ لإتمام العملية.")
                            } else {
                                onToast("تعذر إرسال الطلب. حاول لاحقًا.")
                            }
                        }
                    }
                }
                pendingPkgLabel = null
                pendingPkgPrice = null
                selectedManualFlow = null
            }
        },
        onDismiss = {
            pendingPkgLabel = null
            pendingPkgPrice = null
        }
    )
}
if (selectedManualFlow != null && pendingUsd != null && pendingPrice != null) {
        ConfirmAmountDialog(
            sectionTitle = selectedManualFlow!!,
            usd = pendingUsd!!,
            price = pendingPrice!!,
            onConfirm = {
                val flow = selectedManualFlow
                val amount = pendingUsd
                scope.launch {
                    if (flow != null && amount != null) {
                        val product = when (flow) {
                            "شراء رصيد ايتونز" -> "itunes"
                            "شراء رصيد اثير" -> "atheer"
                            "شراء رصيد اسياسيل" -> "asiacell"
                            "شراء رصيد كورك" -> "korek"
                            else -> "manual"
                        }
                        val (ok, txt) = apiCreateManualPaidOrder(uid, product, amount)
                        if (ok) {
                            val label = "$flow ${amount}$"
                            onToast("تم استلام طلبك ($label).")
                            onAddNotice(AppNotice("طلب معلّق", "تم إرسال طلب $label للمراجعة.", forOwner = false))
                            onAddNotice(AppNotice("طلب جديد", "طلب $label من UID=$uid يحتاج مراجعة.", forOwner = true))
                        } else {
                            val msg = (txt ?: "").lowercase()
                            if (msg.contains("insufficient")) {
                                onToast("رصيدك غير كافٍ لإتمام العملية.")
                            } else {
                                onToast("تعذر إرسال الطلب. حاول لاحقًا.")
                            }
                        }
                    }
                    pendingUsd = null
                    pendingPrice = null
                    selectedManualFlow = null
                }
            },
            onDismiss = {
                pendingUsd = null
                pendingPrice = null
            }
        )
    }

}
@Composable private fun WalletScreen(
    uid: String,
    noticeTick: Int = 0,
    onAddNotice: (AppNotice) -> Unit,
    onToast: (String) -> Unit
) {
    val scope = rememberCoroutineScope()
    var balance by remember { mutableStateOf<Double?>(null) }
    var askAsiacell by remember { mutableStateOf(false) }
    var cardNumber by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    var banPopup by remember { mutableStateOf<String?>(null) }
    var showPayTabs by remember { mutableStateOf(false) }
    var payTabsAmount by remember { mutableStateOf("") }
    var payTabsSending by remember { mutableStateOf(false) }
    var payTabsUrl by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) { balance = apiGetBalance(uid) }
    LaunchedEffect(noticeTick) { balance = apiGetBalance(uid) }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("رصيدي", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = OnBg)
        Spacer(Modifier.height(8.dp))
        Text(
            "الرصيد الحالي: ${balance?.let { "%.2f".format(it) } ?: ""}$",
            fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = OnBg
        )
        Spacer(Modifier.height(16.dp))
        Text("طرق الشحن:", fontWeight = FontWeight.SemiBold, color = OnBg)
        Spacer(Modifier.height(8.dp))

        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp)
                .clickable {
                    val until = loadAsiacellBanUntil(ctx)
                    if (until > 0L && until > System.currentTimeMillis()) {
                        val mins = asiacellBanRemainingMinutes(ctx)
                        banPopup = "تم حضرك موقتا بسبب انتهاك سياسة التطبيق.\\nسينتهي الحظر بعد ${mins} دقيقة."
                    } else {
                        askAsiacell = true
                    }
                },
            colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
        ) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.SimCard, null, tint = Accent)
                Spacer(Modifier.width(8.dp))
                Text("شحن عبر أسيا سيل (كارت)", fontWeight = FontWeight.SemiBold, color = OnBg)
            }
        }

        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 8.dp)
                .clickable { showPayTabs = true },
            colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
        ) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.CreditCard, null, tint = Accent)
                Spacer(Modifier.width(8.dp))
                Text(
                    "شحن عبر بطاقة ماستر / فيزا (PayTabs)",
                    fontWeight = FontWeight.SemiBold,
                    color = OnBg
                )
            }
        }
    }

    if (showPayTabs) {
        AlertDialog(
            onDismissRequest = { if (!payTabsSending) showPayTabs = false },
            confirmButton = {
                TextButton(enabled = !payTabsSending, onClick = {
                    val amount = payTabsAmount.replace(',', '.').toDoubleOrNull()
                    if (amount == null) {
                        onToast("الرجاء إدخال مبلغ صحيح بالدولار.")
                        return@TextButton
                    }
                    if (amount < 1.0) {
                        onToast("أقل مبلغ للشحن هو 1 دولار.")
                        return@TextButton
                    }
                    payTabsSending = true
                    scope.launch {
                        val url = apiCreatePayTabsPayment(uid, amount)
                        payTabsSending = false
                        if (url != null) {
                            onAddNotice(
                                AppNotice(
                                    "شحن رصيد",
                                    "تم إنشاء رابط دفع PayTabs بمبلغ ${amount}$",
                                    forOwner = false
                                )
                            )
                            payTabsUrl = url
                            showPayTabs = false
                            payTabsAmount = ""
                        } else {
                            onToast("فشل إنشاء رابط الدفع، حاول مرة أخرى.")
                        }
                    }
                }) {
                    Text(if (payTabsSending) "ينشئ الرابط" else "متابعة")
                }
            },
            dismissButton = {
                TextButton(enabled = !payTabsSending, onClick = { showPayTabs = false }) {
                    Text("إلغاء")
                }
            },
            title = { Text("شحن عبر بطاقة ماستر / فيزا", color = OnBg) },
            text = {
                Column {
                    Text("أدخل مبلغ الشحن بالدولار (USD)", color = OnBg)
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = payTabsAmount,
                        onValueChange = { payTabsAmount = it },
                        label = { Text("المبلغ بالدولار") }
                    )
                }
            }
        )
    }

    
    if (payTabsUrl != null) {
        AlertDialog(
            onDismissRequest = { payTabsUrl = null },
            confirmButton = {
                TextButton(onClick = { payTabsUrl = null }) {
                    Text("إغلاق")
                }
            },
            properties = DialogProperties(usePlatformDefaultWidth = false),
            title = { Text("إتمام الدفع", color = OnBg) },
            text = {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .fillMaxHeight(0.9f)
                ) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { context ->
                            WebView(context).apply {
                                settings.javaScriptEnabled = true
                                settings.domStorageEnabled = true
                                webViewClient = object : WebViewClient() {
                                    override fun onPageFinished(view: WebView?, url: String?) {
                                        super.onPageFinished(view, url)
                                        val js = """
                                            (function() {
                                                try {
                                                    // ابحث عن عنصر يحتوي على نص "وضع تجريبي"
                                                    var nodes = document.querySelectorAll('div, span');
                                                    var testNode = null;
                                                    for (var i = 0; i < nodes.length; i++) {
                                                        if (nodes[i].innerText && nodes[i].innerText.indexOf('وضع تجريبي') !== -1) {
                                                            testNode = nodes[i];
                                                            break;
                                                        }
                                                    }
                                                    if (testNode && testNode.parentElement && testNode.parentElement.previousElementSibling) {
                                                        // إخفاء القسم العلوي (الهيدر الأزرق) الذي يسبق الكارت الأبيض
                                                        testNode.parentElement.previousElementSibling.style.display = 'none';
                                                    }
                                                } catch (e) {
                                                    console.log('ratluzen header hide error', e);
                                                }
                                            })();
                                        """.trimIndent()

                                        view?.evaluateJavascript(js, null)
                                    }
                                }
                                loadUrl(payTabsUrl!!)
                            }
                        },
                        update = { view ->
                            if (payTabsUrl != null && view.url != payTabsUrl) {
                                view.loadUrl(payTabsUrl!!)
                            }
                        }
                    )
                }
            }
        )
    }

    if (askAsiacell) {
        AlertDialog(
            onDismissRequest = { if (!sending) askAsiacell = false },
            confirmButton = {
                val scope2 = rememberCoroutineScope()
                TextButton(enabled = !sending, onClick = {
                    val digits = cardNumber.filter { it.isDigit() }
                    if (digits.length <= 10) return@TextButton

                    val (allowed, _) = asiacellPreCheckAndRecord(ctx, digits)
                    if (!allowed) {
                        askAsiacell = false
                        sending = false
                        val mins = asiacellBanRemainingMinutes(ctx)
                        banPopup = "تم حضرك موقتا بسبب انتهاك سياسة التطبيق.\\nسينتهي الحظر بعد ${mins} دقيقة."
                        onToast("تم حضرك موقتا بسبب انتهاك سياسة التطبيق")
                        return@TextButton
                    }

                    sending = true
                    scope2.launch {
                        val ok = apiSubmitAsiacellCard(uid, digits)
                        if (ok) { balance = apiGetBalance(uid) }
                        sending = false
                        if (ok) {
                            onAddNotice(AppNotice("تم استلام كارتك", "تم إرسال كارت أسيا سيل إلى المالك للمراجعة.", forOwner = false))
                            onAddNotice(AppNotice("كارت أسيا سيل جديد", "UID=$uid | كارت: $digits", forOwner = true))
                            onToast("تم إرسال الكارت بنجاح")
                            cardNumber = ""
                            askAsiacell = false
                        } else {
                            onAddNotice(AppNotice("فشل إرسال الكارت", "تحقق من الاتصال وحاول مجددًا.", forOwner = false))
                            onToast("فشل إرسال الكارت")
                        }
                    }
                }) { Text(if (sending) "يرسل" else "إرسال") }
            },
            dismissButton = { TextButton(enabled = !sending, onClick = { askAsiacell = false }) { Text("إلغاء") } },
            title = { Text("شحن عبر أسيا سيل", color = OnBg) },
            text = {
                Column {
                    Text("أدخل رقم الكارت (فوق 10 أرقام):", color = Dim, fontSize = 10.sp)
                    Spacer(Modifier.height(6.dp))
                    OutlinedTextField(
                        value = cardNumber,
                        onValueChange = { s -> if (s.all { it.isDigit() }) cardNumber = s },
                        singleLine = true,
                        label = { Text("رقم الكارت") },
                        colors = OutlinedTextFieldDefaults.colors(
                            cursorColor = Accent,
                            focusedBorderColor = Accent, unfocusedBorderColor = Dim,
                            focusedLabelColor = OnBg, unfocusedLabelColor = Dim
                        )
                    )
                }
            }
        )
    }

    banPopup?.let { msg ->
        AlertDialog(
            onDismissRequest = { banPopup = null },
            confirmButton = { TextButton(onClick = { banPopup = null }) { Text("حسنًا") } },
            title = { Text("تنبيه", color = OnBg) },
            text = { Text(msg, color = OnBg) }
        )
    }
}
/* =========================
   تبويب طلباتي
   ========================= */
@Composable private fun OrdersScreen(uid: String) {
    var orders by remember { mutableStateOf<List<OrderItem>?>(null) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(uid) {
        loading = true
        err = null
        orders = apiGetMyOrders(uid).also { loading = false }
        if (orders == null) err = "تعذر جلب الطلبات"
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("طلباتي", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = OnBg)
        Spacer(Modifier.height(10.dp))

        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            orders.isNullOrEmpty() -> Text("لا توجد طلبات حتى الآن.", color = Dim)
            else -> LazyColumn {
                items(orders!!) { o ->
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(o.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Text("الكمية: ${o.quantity} | السعر: ${"%.2f".format(o.price)}$", color = Dim, fontSize = 10.sp)
                            Text("المعرف: ${o.id}", color = Dim, fontSize = 10.sp)
                            Text("الحالة: ${o.status}", color = when (o.status) {
                                OrderStatus.Done -> Good
                                OrderStatus.Rejected -> Bad
                                OrderStatus.Refunded -> Accent
                                else -> OnBg
                            }, fontSize = 10.sp)
                        }
                    }
                }
            }
        }
    }
}

/* =========================
   فلاتر لتصنيف الطلبات
   ========================= */

private fun isIraqTelcoCardPurchase(title: String): Boolean {
    val t = title.lowercase()
    // must be one of the 3 Iraqi telcos
    val telco = t.contains("اثير") || t.contains("asiacell") || t.contains("أسيا") || t.contains("اسياسيل") || t.contains("korek") || t.contains("كورك")
    // words that indicate physical/virtual CARD purchase (not direct top-up)
    val hasCardWord = t.contains("شراء") || t.contains("كارت") || t.contains("بطاقة") || t.contains("voucher") || t.contains("كود") || t.contains("رمز")
    // negative list: anything that implies DIRECT TOP-UP / via Asiacell
    val isTopup = t.contains("شحن") || t.contains("topup") || t.contains("top-up") || t.contains("recharge") || t.contains("شحن عبر") || t.contains("شحن اسيا") || t.contains("direct")
    // explicitly exclude iTunes
    val notItunes = !t.contains("itunes") && !t.contains("ايتونز")
    // accept only if telco + card purchase semantics, and strictly NOT a top-up wording
    return telco && hasCardWord && !isTopup && notItunes
}

private fun isPhoneTopupTitle(title: String): Boolean {
    val t = title.lowercase()
    return t.contains("شراء رصيد") || t.contains("رصيد هاتف")
            || t.contains("اثير") || t.contains("اسياسيل") || t.contains("أسيا") || t.contains("asiacell")
            || t.contains("كورك")
}
/* ✅ تشديد تعريف “طلب API” حتى لا تظهر الطلبات اليدوية (ومنها أسيا سيل) داخل قسم الخدمات */
private fun isApiOrder(o: OrderItem): Boolean {
    val tl = o.title.lowercase()
    val notManualPhone = !isPhoneTopupTitle(o.title)
    val notItunes = !tl.contains("ايتونز") && !tl.contains("itunes")
    val notPubg = !tl.contains("ببجي") && !tl.contains("pubg")
    val notLudo = !tl.contains("لودو") && !tl.contains("ludo")
    val notCard = !tl.contains("كارت") && !tl.contains("card")
    // طلب API يجب أن يكون له quantity > 0 (خدمات المزود) ولا ينتمي لأي قسم يدوي:
    return (o.quantity > 0) && notManualPhone && notItunes && notPubg && notLudo && notCard
}

/* =========================
   لوحة تحكم المالك
   ========================= */
@Composable private fun OwnerPanel(
    token: String?,
    onNeedLogin: () -> Unit,
    onToast: (String) -> Unit
) {
    var current by remember { mutableStateOf<String?>(null) }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("لوحة تحكم المالك", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = OnBg, modifier = Modifier.weight(1f))
            // [Removed] أيقونة الجرس الصغيرة داخل شاشة المالك بناءً على طلبك
}
        Spacer(Modifier.height(12.dp))

        fun needToken(): Boolean {
            if (token.isNullOrBlank()) {
                onToast("سجل دخول المالك أولًا من الإعدادات.")
                onNeedLogin()
                return true
            }
            return false
        }

        if (current == null) {
            val buttons = listOf(
                "طلبات خدمات API المعلقة" to "pending_services",
                "طلبات الايتونز المعلقة"   to "pending_itunes",
                "طلبات ببجي المعلقة"          to "pending_pubg",
                "طلبات لودو المعلقة"       to "pending_ludo",
                "طلبات شراء الكارتات"    to "pending_phone",   // ✅ جديد
                "طلبات شحن أسيا سيل"     to "pending_cards",
                "إضافة الرصيد"             to "topup",
                "خصم الرصيد"               to "deduct",
                "عدد المستخدمين"           to "users_count",
                "أرصدة المستخدمين"         to "users_balances",
                "فحص رصيد API"             to "provider_balance",
                            "تغيير رقم خدمات API" to "edit_svc_ids",
                "تغيير الأسعار والكميات" to "edit_pricing",
                "إعلان التطبيق"           to "announce",
)
            buttons.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth()) {
                    row.forEach { (title, key) ->
                        ElevatedButton(
                            onClick = { if (!needToken()) current = key },
                            modifier = Modifier.weight(1f)
                                .padding(4.dp),
                            colors = ButtonDefaults.elevatedButtonColors(
                                containerColor = Accent.copy(alpha = 0.18f),
                                contentColor = OnBg
                            )
                        ) { Text(title, fontSize = 10.sp) }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        } else {
            when (current) {
                "announce" -> AdminAnnouncementsHub(token = token!!, onBack = { current = null })
                "edit_svc_ids" -> ServiceIdEditorScreen(
                    token = token!!,
                    onBack = { current = null }
                )

"edit_pricing" -> PricingEditorScreen(
    token = token!!,
    onBack = { current = null }
)

                "pending_services" -> AdminPendingGenericList(
                    title = "طلبات خدمات API المعلقة",
                    token = token!!,
                    fetchUrl = AdminEndpoints.pendingServices,
                    itemFilter = { true },                  // ✅ فقط طلبات API
                    approveWithCode = false,
                    onBack = { current = null }
                )
                "pending_itunes" -> PendingItunesWithTools(
                    token = token!!,
                    onBack = { current = null }
                )
                // original params moved out to avoid signature mismatch:
                // fetchUrl = AdminEndpoints.pendingItunes,
                // itemFilter = { true },
                // approveWithCode = true,
                // codeFieldLabel = "كود الايتونز",
//                     title = "طلبات ببجي المعلقة",
                "pending_pubg" -> AdminPendingGenericList(
//                 "pending_pubg" -> AdminPendingGenericList(
                    title = "طلبات ببجي المعلقة",
                    token = token!!,
                    fetchUrl = AdminEndpoints.pendingPubg,
                    itemFilter = { true },
                    approveWithCode = false,
                    onBack = { current = null }
                )
                "pending_ludo" -> AdminPendingGenericList(
                    title = "طلبات لودو المعلقة",
                    token = token!!,
                    fetchUrl = AdminEndpoints.pendingLudo,
                    itemFilter = { true },
                    approveWithCode = false,
                    onBack = { current = null }
                )
                "pending_phone" -> PendingPhoneCardsWithTools(
                    token = token!!,
                    onBack = { current = null }
                )
//                     approveWithCode = true,                                      // ✅ يطلب رقم الكارت
//                     codeFieldLabel = "كود الكارت",
//                     onBack = { current = null }
//                 )
                // ✅ شاشة الكروت المعلّقة الخاصة — UID + كارت + تنفيذ/رفض + وقت
                "pending_cards" -> AdminPendingCardsScreen(
                    token = token!!,
                    onBack = { current = null }
                )
                // إجراءات رصيد
                "topup" -> TopupDeductScreen(
                    title = "إضافة الرصيد",
                    token = token!!,
                    endpoint = AdminEndpoints.walletTopup,
                    onBack = { current = null }
                )
                "deduct" -> TopupDeductScreen(
                    title = "خصم الرصيد",
                    token = token!!,
                    endpoint = AdminEndpoints.walletDeduct,
                    onBack = { current = null }
                )
                "users_count" -> UsersCountScreen(
                    token = token!!,
                    onBack = { current = null }
                )
                "users_balances" -> UsersBalancesScreen(
                    token = token!!,
                    onBack = { current = null }
                )
                "provider_balance" -> ProviderBalanceScreen(
                    token = token!!,
                    onBack = { current = null }
                )
            }
        }
    }
}

/** قائمة عامة للمعلّقات مع مُرشِّح OrderItem + خيار “تنفيذ بكود” */

/* =========================
   Pending Wrappers with Tools
   ========================= */

@Composable private fun PendingItunesWithTools(
    token: String,
    onBack: () -> Unit
) {
    var reloadKey by remember { mutableStateOf(0) }
    var showAdd by remember { mutableStateOf(false) }
    var showView by remember { mutableStateOf(false) }
    var autoEnabled by remember { mutableStateOf(false) }
    var loadingAuto by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit, reloadKey) {
        loadingAuto = true
        autoEnabled = adminAutoExecGetScoped(token, "itunes")
        loadingAuto = false
    }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("طلبات iTunes المعلقة", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                Text("التنفيذ التلقائي", color = OnBg)
                Spacer(Modifier.width(6.dp))
                Switch(
                    checked = autoEnabled,
                    enabled = !loadingAuto,
                    onCheckedChange = { en ->
                        scope.launch {
                            loadingAuto = true
                            val ok = adminAutoExecSetScoped(token, "itunes", en)
                            if (ok) autoEnabled = en
                            loadingAuto = false
                        }
                    },
                    colors = SwitchDefaults.colors(
                        checkedTrackColor = Accent.copy(alpha = 0.45f),
                        checkedThumbColor = Accent
                    )
                )
            }
            OutlinedButton(onClick = { showAdd = true }) { Text("إضافة أكواد") }
            OutlinedButton(onClick = { showView = true }) { Text("عرض الأكواد") }
        }

        Spacer(Modifier.height(8.dp))
        Divider(color = Surface1)
        // القائمة المعتادة تحت الأزرار
        AdminPendingGenericList(
            title = "",
            token = token,
            fetchUrl = AdminEndpoints.pendingItunes,
            itemFilter = { true },
            approveWithCode = true,
            codeFieldLabel = "كود الايتونز",
            onBack = onBack
        )
    }

    if (showAdd) {
        CodesAddDialog(
            title = "إضافة أكواد iTunes",
            telcoTabs = false,
            serviceName = "itunes",
            onSubmit = { telco, category, codes ->
                scope.launch {
                    val ok = apiAdminAddItunesCodes(token, category ?: "", codes)
                    showAdd = false
                }
            },
            onDismiss = { showAdd = false }
        )
    }
    if (showView) {
        CodesListDialogItunes(
            token = token,
            onDismiss = { showView = false }
        )
    }
}

@Composable private fun PendingPhoneCardsWithTools(
    token: String,
    onBack: () -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    var showView by remember { mutableStateOf(false) }
    var autoEnabled by remember { mutableStateOf(false) }
    var loadingAuto by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        loadingAuto = true
        autoEnabled = adminAutoExecGetScoped(token, "cards")
        loadingAuto = false
    }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("طلبات شراء الكارتات", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                Text("التنفيذ التلقائي", color = OnBg)
                Spacer(Modifier.width(6.dp))
                Switch(
                    checked = autoEnabled,
                    enabled = !loadingAuto,
                    onCheckedChange = { en ->
                        scope.launch {
                            loadingAuto = true
                            val ok = adminAutoExecSetScoped(token, "cards", en)
                            if (ok) autoEnabled = en
                            loadingAuto = false
                        }
                    },
                    colors = SwitchDefaults.colors(
                        checkedTrackColor = Accent.copy(alpha = 0.45f),
                        checkedThumbColor = Accent
                    )
                )
            }
            OutlinedButton(onClick = { showAdd = true }) { Text("إضافة أكواد") }
            OutlinedButton(onClick = { showView = true }) { Text("عرض الأكواد") }
        }

        Spacer(Modifier.height(8.dp))
        Divider(color = Surface1)

        AdminPendingGenericList(
            title = "",
            token = token,
            fetchUrl = AdminEndpoints.pendingBalances,
            itemFilter = { item -> isIraqTelcoCardPurchase(item.title) },
            approveWithCode = true,
            codeFieldLabel = "كود الكارت",
            onBack = onBack
        )
    }

    if (showAdd) {
        CodesAddDialog(
            title = "إضافة أكواد رصيد الهاتف",
            telcoTabs = true,
            onSubmit = { telco, category, codes ->
                val tel = telco ?: "asiacell"
                scope.launch {
                    val ok = apiAdminAddCardCodes(token, tel, category ?: "", codes)
                    showAdd = false
                }
            },
            onDismiss = { showAdd = false }
        )
    }
    if (showView) {
        CodesListDialogCards(
            token = token,
            onDismiss = { showView = false }
        )
    }
}

/* ===== Dialogs ===== */

@Composable private fun CodesAddDialog(
    title: String,
    telcoTabs: Boolean,
    categories: List<String> = listOf("5","10","15","20","25","30","40","50","100"),
    serviceName: String? = null, // e.g. "itunes" for iTunes
    onSubmit: (telco: String?, category: String?, codes: List<String>) -> Unit,
    onDismiss: () -> Unit
) {
    var selectedTab by remember { mutableStateOf(0) } // 0: asiacell, 1: atheir, 2: korek when telcoTabs
    var selectedCategoryIdx by remember { mutableStateOf(0) }
    var text by remember { mutableStateOf(TextFieldValue("")) }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                val clean = text.text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
                val telco = if (telcoTabs) listOf("atheir","asiacell","korek")[selectedTab] else null
                val category = categories.getOrNull(selectedCategoryIdx)
                onSubmit(telco, category, clean)
            }) { Text("حفظ") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("إلغاء") } },
        title = { Text(title, color = OnBg) },
        text = {
            Column {
                if (telcoTabs) {
                    TabRow(selectedTabIndex = selectedTab, containerColor = Surface1, contentColor = OnBg) {
                        listOf("أثير","أسيا سيل","كورك").forEachIndexed { i, label ->
                            Tab(selected = selectedTab==i, onClick = { selectedTab = i }, text = { Text(label) })
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }
                // Category selector
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("الفئة", color = OnBg)
                    Spacer(Modifier.width(12.dp))
                    var expanded by remember { mutableStateOf(false) }
                    Box {
                        OutlinedButton(onClick = { expanded = true }) {
                            Text(categories.getOrNull(selectedCategoryIdx) ?: categories.firstOrNull() ?: "")
                        }
                        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                            categories.forEachIndexed { i, c ->
                                DropdownMenuItem(text = { Text(c) }, onClick = { selectedCategoryIdx = i; expanded = false })
                            }
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    modifier = Modifier.fillMaxWidth().height(160.dp),
                    textStyle = LocalTextStyle.current.copy(color = OnBg),
                    label = { Text("ألصق الأكواد (كل سطر كود)") }
                )
            }
        }
    )
}

@Composable private fun CodesListDialogItunes(
    token: String,
    onDismiss: () -> Unit
) {
    var list by remember { mutableStateOf<List<StoredCode>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        loading = true
        list = apiAdminListItunesCodes(token).filter { !it.used }
        loading = false
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("إغلاق") } },
        title = { Text("أكواد iTunes غير المستخدمة", color = OnBg) },
        text = {
            if (loading) {
                CircularProgressIndicator()
            } else {
                LazyColumn(Modifier.height(300.dp)) {
                    items(list) { c ->
                        Row(Modifier.fillMaxWidth().padding(vertical=6.dp), verticalAlignment = Alignment.CenterVertically) {
                            SelectionContainer { Text("[الخدمة: ${c.service ?: (c.telco ?: "—")}] [الفئة: ${c.category ?: "-"}]  ${c.code}", color = OnBg) }
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = {
                                scope.launch {
                                    if (apiAdminDeleteItunesCode(token, c.id)) {
                                        list = list.filter { it.id != c.id }
                                    }
                                }
                            }) { Text("حذف") }
                        }
                    }
                }
            }
        }
    )
}

@Composable private fun CodesListDialogCards(
    token: String,
    onDismiss: () -> Unit
) {
    var selectedTab by remember { mutableStateOf(0) }
    var map by remember { mutableStateOf<Map<String,List<StoredCode>>>(emptyMap()) }
    var loading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    fun telByIdx(i:Int) = listOf("atheir","asiacell","korek")[i]
    fun label(i:Int) = listOf("أثير","أسيا سيل","كورك")[i]

    LaunchedEffect(Unit) {
        loading = true
        val a = apiAdminListCardCodes(token, "atheir").filter { !it.used }
        val b = apiAdminListCardCodes(token, "asiacell").filter { !it.used }
        val c = apiAdminListCardCodes(token, "korek").filter { !it.used }
        map = mapOf("atheir" to a, "asiacell" to b, "korek" to c)
        loading = false
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("إغلاق") } },
        title = { Text("أكواد رصيد الهاتف غير المستخدمة", color = OnBg) },
        text = {
            Column {
                TabRow(selectedTabIndex = selectedTab, containerColor = Surface1, contentColor = OnBg) {
                    (0..2).forEach { i -> Tab(selected = selectedTab==i, onClick = { selectedTab = i }, text = { Text(label(i)) }) }
                }
                Spacer(Modifier.height(8.dp))
                if (loading) {
                    CircularProgressIndicator()
                } else {
                    val list = map[telByIdx(selectedTab)] ?: emptyList()
                    LazyColumn(Modifier.height(280.dp)) {
                        items(list) { c ->
                            Row(Modifier.fillMaxWidth().padding(vertical=6.dp), verticalAlignment = Alignment.CenterVertically) {
                                SelectionContainer { Text("[الخدمة: ${c.service ?: (c.telco ?: "—")}] [الفئة: ${c.category ?: "-"}]  ${c.code}", color = OnBg) }
                                Spacer(Modifier.weight(1f))
                                TextButton(onClick = {
                                    scope.launch {
                                        if (apiAdminDeleteCardCode(token, telByIdx(selectedTab), c.id)) {
                                            map = map.toMutableMap().also { m ->
                                                m[telByIdx(selectedTab)] = list.filter { it.id != c.id }
                                            }
                                        }
                                    }
                                }) { Text("حذف") }
                            }
                        }
                    }
                }
            }
        }
    )
}

/* =========================
   /Pending Wrappers with Tools
   ========================= */
@Composable private fun AdminPendingGenericList(
    title: String,
    token: String,
    fetchUrl: String,
    itemFilter: ((OrderItem) -> Boolean)?,
    approveWithCode: Boolean,
    codeFieldLabel: String = "الرمز/الكود",
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<OrderItem>?>(null) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var reloadKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }

    // Auto-exec toggle state (only used for pendingServices list)
    var autoEnabled by remember { mutableStateOf(false) }
    var autoBusy by remember { mutableStateOf(false) }
    
    var approveFor by remember { mutableStateOf<OrderItem?>(null) }
    var codeText by remember { mutableStateOf("") }

    
    LaunchedEffect(Unit) {
        if (fetchUrl == AdminEndpoints.pendingServices) {
            runCatching { autoEnabled = adminAutoExecStatus(token) }
        }
    }
    
    LaunchedEffect(autoEnabled) {
        if (fetchUrl == AdminEndpoints.pendingServices && autoEnabled) {
            while (autoEnabled) {
                runCatching { adminAutoExecRun(token, limit = 3, onlyWhenEnabled = true) }
                kotlinx.coroutines.delay(8000)
            }
        }
    }
    LaunchedEffect(reloadKey) {
        loading = true; err = null
        val (code, txt) = httpGet(fetchUrl, headers = mapOf("x-admin-password" to token))
        if (code in 200..299 && txt != null) {
            try {
                val parsed = mutableListOf<OrderItem>()
                val trimmed = txt.trim()
                val arr: JSONArray = if (trimmed.startsWith("[")) {
                    JSONArray(trimmed)
                } else {
                    val obj = JSONObject(trimmed)
                    when {
                        obj.has("list") -> obj.optJSONArray("list") ?: JSONArray()
                        obj.has("data") -> obj.optJSONArray("data") ?: JSONArray()
                        else -> JSONArray()
                    }
                }
                for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    val item = OrderItem(
                        id = o.optString("id", o.optInt("id", 0).toString()),
                        title = o.optString("title",""),
                        quantity = o.optInt("quantity", 0),
                        price = o.optDouble("price", 0.0),
                        payload = o.optString("link",""),
                        status = OrderStatus.Pending,
                        createdAt = o.optLong("created_at", 0L),
                        uid = o.optString("uid",""),
                        accountId = o.optString("account_id","")
                    )
if (itemFilter == null || itemFilter.invoke(item)) {
                        parsed += item
                    }
                }
                list = parsed
            } catch (_: Exception) {
                list = null
                err = "تعذر جلب البيانات"
            }
        } else {
            list = null
            err = "تعذر جلب البيانات"
        }
        loading = false
    }

    suspend fun doApprovePlain(id: String): Boolean =
        apiAdminPOST(String.format(AdminEndpoints.orderApprove, id.toInt()), token)

    suspend fun doDeliverPlain(id: String): Boolean =
        apiAdminPOST(String.format(AdminEndpoints.orderDeliver, id.toInt()), token)

    suspend fun doReject(id: String): Boolean =
        apiAdminPOST(String.format(AdminEndpoints.orderReject, id.toInt()), token, JSONObject().put("reason","Rejected by owner"))

    suspend fun doDeliverWithCode(id: String, code: String): Boolean =
        apiAdminPOST(
            String.format(AdminEndpoints.orderDeliver, id.toInt()),
            token,
            JSONObject().put("code", code)            // ✅ يمرّر الكود للباكند
        )

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))
        if (fetchUrl == AdminEndpoints.pendingServices) {
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("تنفيذ تلقائي", fontSize = 16.sp, color = OnBg)
                Switch(
                    checked = autoEnabled,
                    onCheckedChange = { on ->
                        autoEnabled = on
                        if (!autoBusy) {
                            autoBusy = true
                            scope.launch {
                                runCatching { adminAutoExecToggle(token, on) }
                                autoBusy = false
                            }
                        }
                    },
                    enabled = !autoBusy
                )
            }
        }


        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            list.isNullOrEmpty() -> Text("لا يوجد شيء معلق.", color = Dim)
            else -> LazyColumn {
                items(list!!) { o ->
                    val dt = if (o.createdAt > 0) {
                        SimpleDateFormat("yyyy/MM/dd HH:mm", Locale.getDefault()).format(Date(o.createdAt))
                    } else ""
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(o.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                            if (o.uid.isNotBlank()) Text("UID: ${o.uid}", color = Dim, fontSize = 10.sp)
                            if (o.payload.isNotBlank()) {
                                Spacer(Modifier.height(4.dp))
                                Text("تفاصيل: ${o.payload}", color = Dim, fontSize = 10.sp)
                            }
                            if (dt.isNotEmpty()) {
                                Spacer(Modifier.height(4.dp))
                                Text("الوقت: $dt", color = Dim, fontSize = 10.sp)
                            }
                            if (o.accountId.isNotBlank()) {
                                Spacer(Modifier.height(4.dp))
                                val clip = LocalClipboardManager.current
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("Player ID: ", color = OnBg)
                                    Text(
                                        o.accountId,
                                        color = Accent,
                                        modifier = Modifier
                                            .clickable { clip.setText(AnnotatedString(o.accountId)) }
                                            .padding(4.dp)
                                    )
                                }
                            }

Spacer(Modifier.height(8.dp))
Row {

                                TextButton(onClick = {
                                    if (approveWithCode) {
                                        approveFor = o
                                    } else {
                                        scope.launch {
                                            val ok = doApprovePlain(o.id)
                                            snack = if (ok) "تم التنفيذ" else "فشل التنفيذ"
                                            if (ok) reloadKey++
                                        }
                                    }
                                }) { Text("تنفيذ") }
                                TextButton(onClick = {
                                    scope.launch {
                                        val ok = doReject(o.id)
                                        snack = if (ok) "تم الرفض" else "فشل التنفيذ"
                                        if (ok) reloadKey++
                                    }
                                }) { Text("رفض") }
                            }
                        }
                    }
                }
            }
        }

        snack?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, color = OnBg)
            LaunchedEffect(it) { delay(2000); snack = null }
        }
    }

    if (approveFor != null && approveWithCode) {
        AlertDialog(
            onDismissRequest = { approveFor = null; codeText = "" },
            confirmButton = {
                val scope2 = rememberCoroutineScope()
                TextButton(onClick = {
                    val code = codeText.trim()
                    if (code.isEmpty()) return@TextButton
                    scope2.launch {
                        val ok = doDeliverWithCode(approveFor!!.id, code)
                        if (ok) {
                            // نجاح — يفترض أن الباكند سيضيف إشعارًا للمستخدم
                        }
                        approveFor = null
                        codeText = ""
                        snack = if (ok) "تم الإرسال" else "فشل الإرسال"
                        if (ok) reloadKey++
                    }
                }) { Text("إرسال") }
            },
            dismissButton = { TextButton(onClick = { approveFor = null; codeText = "" }) { Text("إلغاء") } },
            title = { Text("إدخال $codeFieldLabel", color = OnBg) },
            text = {
                Column {
                    OutlinedTextField(
                        value = codeText,
                        onValueChange = { codeText = it },
                        singleLine = true,
                        label = { Text(codeFieldLabel) }
                    )
                }
            }
        )
    }
}

@Composable
private fun ServiceIdEditorScreen(token: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var selectedCat by remember { mutableStateOf<String?>(null) }
    var overrides by remember { mutableStateOf<Map<String, Long>>(emptyMap()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var refreshKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }

    val cats = listOf(
        "مشاهدات تيكتوك", "لايكات تيكتوك", "متابعين تيكتوك", "مشاهدات بث تيكتوك", "رفع سكور تيكتوك",
        "مشاهدات انستغرام", "لايكات انستغرام", "متابعين انستغرام", "مشاهدات بث انستا",
        "خدمات التليجرام"
    )

    fun servicesFor(cat: String): List<ServiceDef> {
        fun hasAll(key: String, vararg words: String) = words.all { key.contains(it) }
        return servicesCatalog.filter { svc ->
            val k = svc.uiKey
            when (cat) {
                "مشاهدات تيكتوك"   -> hasAll(k, "مشاهدات", "تيكتوك")
                "لايكات تيكتوك"     -> hasAll(k, "لايكات", "تيكتوك")
                "متابعين تيكتوك"    -> hasAll(k, "متابعين", "تيكتوك")
                "مشاهدات بث تيكتوك" -> hasAll(k, "مشاهدات", "بث", "تيكتوك")
                "رفع سكور تيكتوك"   -> k.contains("رفع سكور")
                "مشاهدات انستغرام"  -> hasAll(k, "مشاهدات", "انستغرام")
                "لايكات انستغرام"    -> hasAll(k, "لايكات", "انستغرام")
                "متابعين انستغرام"   -> hasAll(k, "متابعين", "انستغرام")
                "مشاهدات بث انستا"   -> hasAll(k, "مشاهدات", "بث", "انستا")
                "خدمات التليجرام"    -> k.contains("تلي")
                else -> false
            }
        }.map { svc ->
            val cur = overrides[svc.uiKey] ?: svc.serviceId
            svc.copy(serviceId = cur)
        }
    }

    LaunchedEffect(refreshKey) {
        loading = true; err = null
        val data = apiAdminListSvcOverrides(token)
        overrides = data
        loading = false
    }

    snack?.let {
        LaunchedEffect(it) {
            delay(2000); snack = null
        }
        Snackbar(modifier = Modifier.padding(8.dp)) { Text(it) }
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg)
            }
            Spacer(Modifier.width(6.dp))
            Text("تغيير رقم خدمات API", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))

        if (loading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Column
        }
        err?.let { e ->
            Text("تعذر جلب البيانات: $e", color = Bad)
            return@Column
        }

        if (selectedCat == null) {
            cats.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth()) {
                    row.forEach { c ->
                        Card(
                            modifier = Modifier.weight(1f).padding(4.dp).clickable { selectedCat = c },
                            colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                        ) { Text(c, Modifier.padding(16.dp), fontWeight = FontWeight.SemiBold) }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        } else {
            val list = servicesFor(selectedCat!!)
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selectedCat = null }) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg)
                }
                Spacer(Modifier.width(6.dp))
                Text(selectedCat!!, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, color = OnBg)
            }
            Spacer(Modifier.height(10.dp))

            LazyColumn {
                items(list) { svc ->
                    var showEdit by remember { mutableStateOf(false) }
                    val baseId = servicesCatalog.first { it.uiKey == svc.uiKey }.serviceId
                    val curId = overrides[svc.uiKey] ?: baseId
                    val hasOverride = overrides.containsKey(svc.uiKey)
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(svc.uiKey, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            val hasOverride = overrides.containsKey(svc.uiKey)
                            val baseId = servicesCatalog.first { it.uiKey == svc.uiKey }.serviceId
                            val curId = overrides[svc.uiKey] ?: baseId
                                                        Text("الرقم الحالي: $curId" + if (hasOverride) " (معدل)" else " (افتراضي)", color = Dim, fontSize = 10.sp)
                            Spacer(Modifier.height(8.dp))
                            Row {
                                TextButton(onClick = { showEdit = true }) { Text("تعديل") }
                                Spacer(Modifier.width(6.dp))
                                TextButton(enabled = hasOverride, onClick = {
                                    scope.launch {
                                        val ok = apiAdminClearSvcOverride(token, svc.uiKey)
                                        if (ok) {
                                            snack = "تم إرجاع الافتراضي"
                                            refreshKey++
                                        } else snack = "فشل إرجاع الافتراضي"
                                    }
                                }) { Text("إرجاع الافتراضي") }
                            }
                        }
                    }

                    if (showEdit) {
                        var newIdText by remember { mutableStateOf(curId.toString()) }
                        AlertDialog(
                            onDismissRequest = { showEdit = false },
                            confirmButton = {
                                TextButton(onClick = {
                                    val num = newIdText.trim().toLongOrNull()
                                    if (num != null && num > 0) {
                                        scope.launch {
                                            val ok = apiAdminSetSvcOverride(token, svc.uiKey, num)
                                            if (ok) {
                                                snack = "تم الحفظ"
                                                showEdit = false
                                                refreshKey++
                                            } else snack = "فشل الحفظ"
                                        }
                                    }
                                }) { Text("حفظ") }
                            },
                            dismissButton = { TextButton(onClick = { showEdit = false }) { Text("إلغاء") } },
                            title = { Text("تعديل رقم الخدمة", color = OnBg) },
                            text = {
                                Column {
                                    Text("الخدمة: ${svc.uiKey}", color = Dim, fontSize = 10.sp)
                                    Spacer(Modifier.height(6.dp))
                                    OutlinedTextField(
                                        value = newIdText,
                                        onValueChange = { s -> if (s.isEmpty() || s.all { it.isDigit() }) newIdText = s },
                                        singleLine = true,
                                        label = { Text("Service ID") }
                                    )
                                }
                            }
                        )
                    }
                }
            }
        }
    }
}

/* =========================
   شاشة الكروت المعلّقة (المالك)
   ========================= */
@Composable private fun AdminPendingCardsScreen(
    token: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<PendingCard>?>(null) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var reloadKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }
    var execFor by remember { mutableStateOf<PendingCard?>(null) }
    var amountText by remember { mutableStateOf("") }
    LaunchedEffect(reloadKey) {
        loading = true; err = null
        list = apiAdminFetchPendingCards(token)
        if (list == null) err = "تعذر جلب البيانات"
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("طلبات شحن أسيا سيل", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))

        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            list.isNullOrEmpty() -> Text("لا توجد كروت معلّقة.", color = Dim)
            else -> LazyColumn {
                items(list!!) { c ->
                    val dt = if (c.createdAt > 0) {
                        SimpleDateFormat("yyyy/MM/dd HH:mm", Locale.getDefault()).format(Date(c.createdAt))
                    } else ""
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("طلب #${c.id}", fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            Text("UID: ${c.uid}", color = Dim, fontSize = 10.sp)
                            Spacer(Modifier.height(4.dp))
                            val clip = LocalClipboardManager.current
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("الكارت: ", color = OnBg)
                                Text(
                                    c.card,
                                    color = Accent,
                                    modifier = Modifier
                                        .clickable {
                                            clip.setText(AnnotatedString(c.card))
                                            snack = "تم نسخ رقم الكارت"
                                        }
                                        .padding(4.dp)
                                )
                            }
                            if (dt.isNotEmpty()) {
                                Spacer(Modifier.height(4.dp))
                                Text("الوقت: $dt", color = Dim, fontSize = 10.sp)
                            }
                            Row {

                                TextButton(onClick = { execFor = c }) { Text("تنفيذ") }
                                TextButton(onClick = {
                                    scope.launch {
                                        val ok = apiAdminRejectTopupCard(c.id, token)
                                        snack = if (ok) "تم الرفض" else "فشل الرفض"
                                        if (ok) reloadKey++
                                    }
                                }) { Text("رفض") }
                            }
                        }
                    }
                }
            }
        }

        snack?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, color = OnBg)
            LaunchedEffect(it) { delay(2000); snack = null }
        }
    }

    if (execFor != null) {
        AlertDialog(
            onDismissRequest = { execFor = null },
            confirmButton = {
                val scope2 = rememberCoroutineScope()
                TextButton(onClick = {
                    val amt = amountText.toDoubleOrNull()
                    if (amt == null || amt <= 0.0) return@TextButton
                    scope2.launch {
                        val ok = apiAdminExecuteTopupCard(execFor!!.id, amt, token)
                        if (ok) {
                            execFor = null
                            amountText = ""
                            // بعد التنفيذ سيتم تحديث القائمة عبر reloadKey
                            snack = "تم التنفيذ"
                            reloadKey++
                        } else snack = "فشل التنفيذ"
                    }
                }) { Text("إرسال") }
            },
            dismissButton = { TextButton(onClick = { execFor = null }) { Text("إلغاء") } },
            title = { Text("تنفيذ الشحن", color = OnBg) },
            text = {
                Column {
                    Text("أدخل مبلغ الشحن ليُضاف لرصيد المستخدم", color = Dim, fontSize = 10.sp)
                    Spacer(Modifier.height(6.dp))
                    OutlinedTextField(
                        value = amountText,
                        onValueChange = { s -> if (s.isEmpty() || s.toDoubleOrNull() != null) amountText = s },
                        singleLine = true,
                        label = { Text("المبلغ") }
                    )
                }
            }
        )
    }
}
/* =========================
   شاشات مضافة لإكمال النواقص
   ========================= */

/** إضافة/خصم رصيد — تنفذ الطلب بنفسها داخل Coroutine */
@Composable private fun TopupDeductScreen(
    title: String,
    token: String,
    endpoint: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var uid by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = uid, onValueChange = { uid = it.trim() },
            singleLine = true, label = { Text("UID المستخدم") }
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = amount, onValueChange = { s -> if (s.isEmpty() || s.toDoubleOrNull() != null) amount = s },
            singleLine = true, label = { Text("المبلغ") }
        )
        Spacer(Modifier.height(12.dp))
        Button(
            enabled = !busy,
            onClick = {
                val a = amount.toDoubleOrNull()
                if (uid.isBlank() || a == null || a <= 0.0) { msg = "أدخل UID ومبلغًا صحيحًا"; return@Button }
                busy = true
                scope.launch {
                    val ok = apiAdminWalletChange(endpoint, token, uid, a)
                    busy = false
                    msg = if (ok) "تمت العملية بنجاح" else "فشلت العملية"
                }
            }
        ) { Text(if (busy) "جارٍ التنفيذ" else "تنفيذ") }

        Spacer(Modifier.height(10.dp))
        msg?.let { Text(it, color = OnBg) }
    }
}

/** عدد المستخدمين */
@Composable private fun UsersCountScreen(
    token: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var count by remember { mutableStateOf<Int?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        loading = true
        count = apiAdminUsersCount(token)
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("عدد المستخدمين", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(12.dp))
        if (loading) Text("يتم التحميل", color = Dim)
        else Text("العدد: ${count ?: 0}", color = OnBg, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = {
            loading = true
            scope.launch { count = apiAdminUsersCount(token); loading = false }
        }) { Text("تحديث") }
    }
}

/** أرصدة المستخدمين */
@Composable private fun UsersBalancesScreen(
    token: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var rows by remember { mutableStateOf<List<Triple<String,String,Double>>?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        loading = true
        rows = apiAdminUsersBalances(token)
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("أرصدة المستخدمين", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(12.dp))
        when {
            loading -> Text("يتم التحميل", color = Dim)
            rows == null -> Text("تعذر جلب البيانات", color = Bad)
            rows!!.isEmpty() -> Text("لا توجد بيانات.", color = Dim)
            else -> LazyColumn {
                items(rows!!) { (u, state, bal) ->
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("UID: $u", fontWeight = FontWeight.SemiBold, color = OnBg)
                                Text("الحالة: $state", color = Dim, fontSize = 10.sp)
                            }
                            Text("${"%.2f".format(bal)}$", color = OnBg, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = {
            loading = true
            scope.launch { rows = apiAdminUsersBalances(token); loading = false }
        }) { Text("تحديث") }
    }
}

/** فحص رصيد المزود */
@Composable private fun ProviderBalanceScreen(
    token: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var bal by remember { mutableStateOf<Double?>(null) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        loading = true; err = null
        bal = apiAdminProviderBalance(token)
        if (bal == null) err = "تعذر جلب الرصيد"
        loading = false
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("فحص رصيد API", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(12.dp))
        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            else -> Text("الرصيد: ${"%.2f".format(bal ?: 0.0)}", color = OnBg, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = {
            loading = true; err = null
            scope.launch {
                bal = apiAdminProviderBalance(token)
                if (bal == null) err = "تعذر جلب الرصيد"
                loading = false
            }
        }) { Text("تحديث") }
    }
}

/* =========================
   شريط سفلي
   ========================= */
@Composable private fun BottomNavBar(current: Tab, onChange: (Tab) -> Unit, modifier: Modifier = Modifier) {
    NavigationBar(modifier = modifier.fillMaxWidth(), containerColor = Surface1) {
        NavItem(current == Tab.HOME, { onChange(Tab.HOME) }, Icons.Filled.Home, "الرئيسية")
        NavItem(current == Tab.SERVICES, { onChange(Tab.SERVICES) }, Icons.Filled.List, "الخدمات")
        NavItem(current == Tab.WALLET, { onChange(Tab.WALLET) }, Icons.Filled.AccountBalanceWallet, "رصيدي")
        NavItem(current == Tab.ORDERS, { onChange(Tab.ORDERS) }, Icons.Filled.ShoppingCart, "الطلبات")
        NavItem(current == Tab.SUPPORT, { onChange(Tab.SUPPORT) }, Icons.Filled.ChatBubble, "الدعم")
    }
}
@Composable private fun RowScope.NavItem(
    selected: Boolean, onClick: () -> Unit,
    icon: androidx.compose.ui.graphics.vector.ImageVector, label: String
) {
    NavigationBarItem(
        selected = selected, onClick = onClick,
        icon = { Icon(icon, contentDescription = label) },
        label = { Text(label, fontSize = 10.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal) },
        colors = NavigationBarItemDefaults.colors(
            selectedIconColor = Color.White, selectedTextColor = Color.White,
            indicatorColor = Accent.copy(alpha = 0.25f),
            unselectedIconColor = Dim, unselectedTextColor = Dim
        )
    )
}

/* =========================
   تخزين محلي + أدوات شبكة
   ========================= */
private fun prefs(ctx: Context) = ctx.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)

// =========================
// حظر أسيا سيل + عدادات محلية
// =========================
private const val PREF_ASIA_BAN_UNTIL = "asia_ban_until_ms"
private const val PREF_ASIA_BAN_REASON = "asia_ban_reason"
private const val PREF_ASIA_CARD_TIMES = "asia_card_times"    // JSONObject: { "CARD_DIGITS": [ts, ts, ...] }
private const val PREF_ASIA_RECENT = "asia_recent_times"      // JSONArray: [ts, ts, ...]

private fun clearAsiacellBan(ctx: Context) {
    prefs(ctx).edit().remove(PREF_ASIA_BAN_UNTIL).remove(PREF_ASIA_BAN_REASON).apply()
}

private fun loadAsiacellBanUntil(ctx: Context): Long {
    val until = prefs(ctx).getLong(PREF_ASIA_BAN_UNTIL, 0L)
    if (until > 0 && System.currentTimeMillis() > until) {
        clearAsiacellBan(ctx) // انتهى الحظر تلقائيًا
        return 0L
    }
    return until
}

private fun setAsiacellBan(ctx: Context, reason: String) {
    val until = System.currentTimeMillis() + 60L * 60L * 1000L // ساعة
    prefs(ctx).edit()
        .putLong(PREF_ASIA_BAN_UNTIL, until)
        .putString(PREF_ASIA_BAN_REASON, reason)
        .apply()
}

private fun asiacellBanRemainingMinutes(ctx: Context): Long {
    val until = loadAsiacellBanUntil(ctx)
    val left = until - System.currentTimeMillis()
    return if (left <= 0) 0 else (left + 59_999L) / 60_000L
}

private fun loadJsonObjectOrEmpty(s: String?): JSONObject =
    try { if (!s.isNullOrBlank()) JSONObject(s) else JSONObject() } catch (_: Throwable) { JSONObject() }

private fun loadJsonArrayOrEmpty(s: String?): JSONArray =
    try { if (!s.isNullOrBlank()) JSONArray(s) else JSONArray() } catch (_: Throwable) { JSONArray() }

/**
 * يفحص الحظر + السرعة + تكرار نفس الكارت، ويحدث العدادات إن لم يُحظر.
 * @return Pair(allowed, reasonOrNull)
 *  - allowed=false, reason in {"ban_active","speed","repeat"} عند الحظر.
 */
private fun asiacellPreCheckAndRecord(ctx: Context, digitsRaw: String): Pair<Boolean, String?> {
    val now = System.currentTimeMillis()
    if (loadAsiacellBanUntil(ctx) > now) return false to "ban_active"

    val digits = digitsRaw.filter { it.isDigit() }

    // 1) فحص السرعة: 3 محاولات خلال دقيقة -> حظر ساعة
    val recStr = prefs(ctx).getString(PREF_ASIA_RECENT, "[]")
    val recent = loadJsonArrayOrEmpty(recStr)
    val keep = JSONArray()
    var recentCount = 0
    for (i in 0 until recent.length()) {
        val t = recent.optLong(i, 0L)
        if (t > now - 60_000L) { keep.put(t); recentCount++ }
    }
    if (recentCount >= 2) { // هذه ستكون المحاولة الثالثة خلال دقيقة
        setAsiacellBan(ctx, "speed")
        return false to "speed"
    }

    // 2) تكرار نفس الرقم: أكثر من مرتين خلال 24 ساعة -> حظر ساعة
    val mapStr = prefs(ctx).getString(PREF_ASIA_CARD_TIMES, "{}")
    val obj = loadJsonObjectOrEmpty(mapStr)
    val arr = obj.optJSONArray(digits) ?: JSONArray()
    val arrKeep = JSONArray()
    var sameCardCount = 0
    for (i in 0 until arr.length()) {
        val t = arr.optLong(i, 0L)
        if (t > now - 24L * 60L * 60L * 1000L) {
            arrKeep.put(t); sameCardCount++
        }
    }
    if (sameCardCount >= 2) { // المحاولة الحالية ستكون الثالثة لهذا الرقم
        setAsiacellBan(ctx, "repeat")
        return false to "repeat"
    }

    // لم يُحظر: نسجل المحاولة الحالية
    keep.put(now)
    prefs(ctx).edit().putString(PREF_ASIA_RECENT, keep.toString()).apply()
    arrKeep.put(now)
    obj.put(digits, arrKeep)
    prefs(ctx).edit().putString(PREF_ASIA_CARD_TIMES, obj.toString()).apply()

    return true to null
}
private fun loadOrCreateUid(ctx: Context): String {

    val p = prefs(ctx)
    val key = "uid"
    val existing = p.getString(key, null)
    if (!existing.isNullOrBlank()) return existing
    // Generate 7-digit numeric UID, never starting with 0
    val first = (1..9).random().toString()
    val rest = (1..6).map { ('0'..'9').random() }.joinToString("")
    val uid = first + rest
    p.edit().putString(key, uid).apply()
    return uid

}
private fun saveUid(ctx: Context, uid: String) { prefs(ctx).edit().putString("uid", uid).apply() }

/* ============ Local password storage (device only) ============ */
/* تنبيه أمني: السيرفر يخزّن كلمة المرور كـ hash فقط. محليًا نحتفظ بنسخة مشفرة-مبسّطة لأجل "العرض لاحقًا" على نفس الجهاز. */
private fun obf(s: String): String {
    val k = "RATLUZEN_SALT_2025".toByteArray()
    val bytes = s.toByteArray(Charsets.UTF_8)
    val xored = ByteArray(bytes.size) { i -> (bytes[i].toInt() xor k[i % k.size].toInt()).toByte() }
    return android.util.Base64.encodeToString(xored, android.util.Base64.NO_WRAP)
}
private fun deobf(b64: String): String {
    return try {
        val k = "RATLUZEN_SALT_2025".toByteArray()
        val xored = android.util.Base64.decode(b64, android.util.Base64.NO_WRAP)
        val bytes = ByteArray(xored.size) { i -> (xored[i].toInt() xor k[i % k.size].toInt()).toByte() }
        String(bytes, Charsets.UTF_8)
    } catch (_: Exception) { "" }
}
private fun saveLocalPassword(ctx: Context, uid: String, pwd: String) {
    prefs(ctx).edit().putString("user_pwd_$uid", obf(pwd)).apply()
}
private fun loadLocalPassword(ctx: Context, uid: String): String? {
    val raw = prefs(ctx).getString("user_pwd_$uid", null) ?: return null
    val dec = deobf(raw)
    return if (dec.isNotBlank()) dec else null
}

private fun loadOwnerMode(ctx: Context): Boolean = prefs(ctx).getBoolean("owner_mode", false)
private fun saveOwnerMode(ctx: Context, on: Boolean) { prefs(ctx).edit().putBoolean("owner_mode", on).apply() }
private fun loadOwnerToken(ctx: Context): String? = prefs(ctx).getString("owner_token", null)
private fun saveOwnerToken(ctx: Context, token: String?) { prefs(ctx).edit().putString("owner_token", token).apply() }

private fun loadNotices(ctx: Context): List<AppNotice> {
    val raw = prefs(ctx).getString("notices_json", "[]") ?: "[]"
    return try {
        val arr = JSONArray(raw)
        (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            AppNotice(
                title = o.optString("title"),
                body = o.optString("body"),
                ts = o.optLong("ts"),
                orderId = o.optString("orderId", "").takeIf { it.isNotBlank() },
                serviceName = o.optString("serviceName", "").takeIf { it.isNotBlank() },
                amount = o.optString("amount", "").takeIf { it.isNotBlank() },
                code = o.optString("code", "").takeIf { it.isNotBlank() },
                status = o.optString("status", "").takeIf { it.isNotBlank() },
                forOwner = o.optBoolean("forOwner")
            )
        }
    } catch (_: Exception) { emptyList() }
}
private fun saveNotices(ctx: Context, notices: List<AppNotice>) {
    val arr = JSONArray()
    notices.forEach {
        val o = JSONObject()
        o.put("title", it.title)
        o.put("body", it.body)
        o.put("ts", it.ts)
        if (it.orderId != null) o.put("orderId", it.orderId)
        if (it.serviceName != null) o.put("serviceName", it.serviceName)
        if (it.amount != null) o.put("amount", it.amount)
        if (it.code != null) o.put("code", it.code)
        if (it.status != null) o.put("status", it.status)
        o.put("forOwner", it.forOwner)
        arr.put(o)
    }
    prefs(ctx).edit().putString("notices_json", arr.toString()).apply()
}

/* تتبع آخر وقت قراءة الإشعارات لكل وضع (مستخدم/مالك) */
private fun lastSeenKey(forOwner: Boolean) = if (forOwner) "last_seen_owner" else "last_seen_user"
private fun loadLastSeen(ctx: Context, forOwner: Boolean): Long =
    prefs(ctx).getLong(lastSeenKey(forOwner), 0L)
private fun saveLastSeen(ctx: Context, forOwner: Boolean, ts: Long = System.currentTimeMillis()) {
    prefs(ctx).edit().putLong(lastSeenKey(forOwner), ts).apply()
}
/* شبكة - GET (suspend) */
/* ======= Auto-Exec (Admin) helpers ======= */
private suspend fun adminAutoExecStatus(token: String): Boolean {
    val (code, txt) = httpGet(AdminEndpoints.autoExecStatus, headers = mapOf("x-admin-password" to token))
    return if (code in 200..299 && !txt.isNullOrBlank()) {
        try { JSONObject(txt).optBoolean("enabled", false) } catch (_: Exception) { false }
    } else false
}
private suspend fun adminAutoExecToggle(token: String, enabled: Boolean): Boolean {
    val body = JSONObject().put("enabled", enabled)
    val (code, _) = httpPost(AdminEndpoints.autoExecToggle, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
private suspend fun adminAutoExecRun(token: String, limit: Int = 3, onlyWhenEnabled: Boolean = true): Boolean {
    val body = JSONObject().put("limit", limit).put("only_when_enabled", onlyWhenEnabled)
    val (code, _) = httpPost(AdminEndpoints.autoExecRun, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

/* ======= Code Pools helpers (iTunes + Phone Cards) ======= */

data class StoredCode(
    @SerializedName("id") val id: Int = 0,
    @SerializedName("code") val code: String = "",
    @SerializedName("service") val service: String? = null,
    @SerializedName("telco") val telco: String? = null,
    @SerializedName("category") val category: String? = null,
    @SerializedName("used") val used: Boolean = false,
    @SerializedName("created_at") val createdAt: Long? = null
)

// -- Generic JSON parse with safety
private fun parseCodesJson(txt: String?): List<StoredCode> {
    if (txt.isNullOrBlank()) return emptyList()
    return try {
        val arr = JSONArray(txt)
        (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            StoredCode(
                id = o.optInt("id", 0),
                code = o.optString("code", ""),
                service = o.optString("service", null),
                telco = o.optString("telco", null),
                category = (o.opt("category")?.toString() ?: o.optString("pack", null)),
                used = o.optBoolean("used", false),
                createdAt = if (o.has("created_at")) o.optLong("created_at") else null
            )
        }
    } catch (_: Exception) { emptyList() }
}

private suspend fun apiAdminListItunesCodes(token: String): List<StoredCode> {
    val (code, txt) = httpGet(AdminEndpoints.itunesCodesList, headers = mapOf("x-admin-password" to token))
    return if (code in 200..299) parseCodesJson(txt) else emptyList()
}

private suspend fun apiAdminAddItunesCodes(token: String, category: String, codes: List<String>): Boolean {
    val arr = JSONArray()
    codes.filter { it.isNotBlank() }.forEach { arr.put(it.trim()) }
    val body = JSONObject().put("codes", arr).put("category", category)
    val (code, _) = httpPost(AdminEndpoints.itunesCodesAdd, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminDeleteItunesCode(token: String, id: Int): Boolean {
    val (code, _) = httpPost(AdminEndpoints.itunesCodeDelete(id), JSONObject(), headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminListCardCodes(token: String, telco: String): List<StoredCode> {
    val (code, txt) = httpGet(AdminEndpoints.cardCodesList(telco), headers = mapOf("x-admin-password" to token))
    return if (code in 200..299) parseCodesJson(txt) else emptyList()
}

private suspend fun apiAdminAddCardCodes(token: String, telco: String, category: String, codes: List<String>): Boolean {
    val arr = JSONArray()
    codes.filter { it.isNotBlank() }.forEach { arr.put(it.trim()) }
    val body = JSONObject().put("codes", arr).put("category", category)
    val (code, _) = httpPost(AdminEndpoints.cardCodesAdd(telco), body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

private suspend fun apiAdminDeleteCardCode(token: String, telco: String, id: Int): Boolean {
    val (code, _) = httpPost(AdminEndpoints.cardCodeDelete(telco, id), JSONObject(), headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

// -- Scoped Auto-Exec helpers
private suspend fun adminAutoExecGetScoped(token: String, scope: String): Boolean {
    val (code, txt) = httpGet(AdminEndpoints.autoExecStatusScoped(scope), headers = mapOf("x-admin-password" to token))
    return code in 200..299 && (try { JSONObject(txt ?: "{}").optBoolean("enabled", false) } catch (_: Exception) { false })
}

private suspend fun adminAutoExecSetScoped(token: String, scope: String, enabled: Boolean): Boolean {
    val body = JSONObject().put("scope", scope).put("enabled", enabled)
    val (code, _) = httpPost(AdminEndpoints.autoExecSet, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}

/* ======= /Code Pools helpers ======= */
/* ======= /Auto-Exec helpers ======= */
suspend fun httpGet(path: String, headers: Map<String, String> = emptyMap()): Pair<Int, String?> =
    withContext(Dispatchers.IO) {
        try {
            val url = URL("$API_BASE$path")
            val con = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 8000
                readTimeout = 8000
                headers.forEach { (k, v) -> setRequestProperty(k, v) }
            }
            val code = con.responseCode
            val txt = (if (code in 200..299) con.inputStream else con.errorStream)
                ?.bufferedReader()?.use { it.readText() }
            code to txt
        } catch (_: Exception) { -1 to null }
    }

/* POST JSON (blocking) — نغلفها بدالة suspend أدناه */
private fun httpPostBlocking(path: String, json: JSONObject, headers: Map<String, String> = emptyMap()): Pair<Int, String?> {
    return try {
        val url = URL("$API_BASE$path")
        val con = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 12000
            readTimeout = 12000
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            headers.forEach { (k, v) -> setRequestProperty(k, v) }
        }
        OutputStreamWriter(con.outputStream, Charsets.UTF_8).use { it.write(json.toString()) }
        val code = con.responseCode
        val txt = (if (code in 200..299) con.inputStream else con.errorStream)
            ?.bufferedReader()?.use { it.readText() }
        code to txt
    } catch (_: Exception) { -1 to null }
}

/* POST form مطلق (KD1S) — نغلفها بدالة suspend */
private fun httpPostFormAbsolute(fullUrl: String, fields: Map<String, String>, headers: Map<String, String> = emptyMap()): Pair<Int, String?> {
    return try {
        val url = URL(fullUrl)
        val form = fields.entries.joinToString("&") { (k, v) -> "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}" }
        val con = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 12000
            readTimeout = 12000
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
            headers.forEach { (k, v) -> setRequestProperty(k, v) }
        }
        con.outputStream.use { it.write(form.toByteArray(Charsets.UTF_8)) }
        val code = con.responseCode
        val txt = (if (code in 200..299) con.inputStream else con.errorStream)
            ?.bufferedReader()?.use { it.readText() }
        code to txt
    } catch (_: Exception) { -1 to null }
}

/* أغلفة suspend للـ POSTs */
private suspend fun httpPost(path: String, json: JSONObject, headers: Map<String, String> = emptyMap()): Pair<Int, String?> =
    withContext(Dispatchers.IO) { httpPostBlocking(path, json, headers) }

private suspend fun httpPostFormAbs(fullUrl: String, fields: Map<String, String>, headers: Map<String, String> = emptyMap()): Pair<Int, String?> =
    withContext(Dispatchers.IO) { httpPostFormAbsolute(fullUrl, fields, headers) }

/* ===== وظائف مشتركة مع الخادم ===== */
private suspend fun pingHealth(): Boolean? {
    val (code, _) = httpGet("/health")
    return code in 200..299
}
private suspend fun tryUpsertUid(uid: String) {
    httpPost("/api/users/upsert", JSONObject().put("uid", uid))
}
private suspend fun apiGetBalance(uid: String): Double? {
    val (code, txt) = httpGet("/api/wallet/balance?uid=$uid")
    return if (code in 200..299 && txt != null) {
        try { JSONObject(txt.trim()).optDouble("balance") } catch (_: Exception) { null }
    } else null
}
private suspend fun apiCreateProviderOrder(
    uid: String, serviceId: Long, serviceName: String, link: String, quantity: Int, price: Double
): Boolean {
    val body = JSONObject()
        .put("uid", uid)
        .put("service_id", serviceId)
        .put("service_name", serviceName)
        .put("link", link)
        .put("quantity", quantity)
        .put("price", price)
    val (code, txt) = httpPost("/api/orders/create/provider", body)
    return code in 200..299 && (txt?.contains("ok", ignoreCase = true) == true)
}

/* أسيا سيل */
private suspend fun apiSubmitAsiacellCard(uid: String, card: String): Boolean {
    val (code, txt) = httpPost(
        "/api/wallet/asiacell/submit",
        JSONObject().put("uid", uid).put("card", card)
    )
    if (code !in 200..299) return false
    return try {
        if (txt == null) return true
        val obj = JSONObject(txt.trim())
        obj.optBoolean("ok", true) || obj.optString("status").equals("received", true)
    } catch (_: Exception) { true }
}

/* PayTabs – شحن الرصيد عبر الماستر/فيزا */
private suspend fun apiCreatePayTabsPayment(uid: String, amountUsd: Double): String? {
    val body = JSONObject()
        .put("uid", uid)
        .put("usd", amountUsd)
    val (code, txt) = httpPost("/api/wallet/paytabs/create", body)
    if (code !in 200..299 || txt == null) return null
    return try {
        val obj = JSONObject(txt.trim())
        obj.optString("payment_url", null)
    } catch (_: Exception) {
        null
    }
}

private suspend fun apiCreateManualOrder(uid: String, name: String): Boolean {
    val body = JSONObject().put("uid", uid).put("title", name)
    val (code, txt) = httpPost("/api/orders/create/manual", body)
    return code in 200..299 && (txt?.contains("ok", true) == true)
}


suspend fun apiCreateManualPaidOrder(uid: String, product: String, usd: Double, accountId: String? = null): Pair<Boolean, String?> {
    val body = JSONObject()
        .put("uid", uid)
        .put("product", product)
        .put("usd", usd)
    if (!accountId.isNullOrBlank()) body.put("account_id", accountId)
    val (code, txt) = httpPost("/api/orders/create/manual_paid", body)
    val ok = code in 200..299 && (txt?.contains("ok", true) == true || txt?.contains("order_id", true) == true)
    return Pair(ok, txt)
}
suspend fun apiCreateManualPaidOrder(uid: String, product: String, usd: Int, accountId: String? = null): Pair<Boolean, String?> {
    val body = JSONObject()
        .put("uid", uid)
        .put("product", product)
        .put("usd", usd)
    if (!accountId.isNullOrBlank()) body.put("account_id", accountId)
    val (code, txt) = httpPost("/api/orders/create/manual_paid", body)
    val ok = code in 200..299 && (txt?.contains("ok", true) == true || txt?.contains("order_id", true) == true)
    return Pair(ok, txt)
}

private suspend fun apiGetMyOrders(uid: String): List<OrderItem>? {
    val (code, txt) = httpGet("/api/orders/my?uid=$uid")
    if (code !in 200..299 || txt == null) return null
    return try {
        val trimmed = txt.trim()
        val arr: JSONArray = if (trimmed.startsWith("[")) {
            JSONArray(trimmed)
        } else {
            val obj = JSONObject(trimmed)
            when {
                obj.has("orders") -> obj.optJSONArray("orders") ?: JSONArray()
                obj.has("list")   -> obj.optJSONArray("list") ?: JSONArray()
                else -> JSONArray()
            }
        }
        (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            OrderItem(
                id = o.optString("id"),
                title = o.optString("title"),
                quantity = o.optInt("quantity"),
                price = o.optDouble("price"),
                payload = o.optString("payload"),
                status = when (o.optString("status")) {
                    "Done" -> OrderStatus.Done
                    "Rejected" -> OrderStatus.Rejected
                    "Refunded" -> OrderStatus.Refunded
                    "Processing" -> OrderStatus.Processing
                    else -> OrderStatus.Pending
                },
                createdAt = o.optLong("created_at"),
                uid = o.optString("uid","")
            )
        }
    } catch (_: Exception) { null }
}

/* ===== إشعارات المستخدم من الخادم ===== */
private fun noticeKey(n: AppNotice) = n.title + "|" + n.body + "|" + n.ts

private fun mergeNotices(local: List<AppNotice>, incoming: List<AppNotice>): List<AppNotice> {
    val seen = local.associateBy { noticeKey(it) }.toMutableMap()
    incoming.forEach { n -> seen.putIfAbsent(noticeKey(n), n) }
    return seen.values.sortedByDescending { it.ts }
}

private suspend fun apiFetchNotificationsByUid(uid: String, limit: Int = 50): List<AppNotice>? {
    // 1) try by-uid
    val (code1, txt1) = httpGet("/api/user/by-uid/$uid/notifications?status=unread&limit=$limit")
    if (code1 in 200..299 && txt1 != null) {
        try {
            val arr = org.json.JSONArray(txt1!!.trim())
            val out = mutableListOf<AppNotice>()
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                val title = o.optString("title","إشعار")
                val body  = o.optString("body","")
                val tsMs  = o.optLong("created_at", System.currentTimeMillis())
                out += AppNotice(title, body, if (tsMs < 2_000_000_000L) tsMs*1000 else tsMs, forOwner = false)
            }
            return out
        } catch (_: Exception) { /* fallthrough */ }
    }
    // 2) fallback to numeric id route if available (only if uid is numeric)
    val uidNum = uid.toLongOrNull()
    if (uidNum != null) {
        val (code2, txt2) = httpGet("/api/user/$uidNum/notifications?status=unread&limit=$limit")
        if (code2 in 200..299 && txt2 != null) {
            try {
                val arr = org.json.JSONArray(txt2!!.trim())
                val out = mutableListOf<AppNotice>()
                for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    val title = o.optString("title","إشعار")
                    val body  = o.optString("body","")
                    val tsMs  = o.optLong("created_at", System.currentTimeMillis())
                    out += AppNotice(title, body, if (tsMs < 2_000_000_000L) tsMs*1000 else tsMs, forOwner = false)
                }
                return out
            } catch (_: Exception) { /* ignore */ }
        }
    }
    return null
}

/* دخول المالك */
private suspend fun apiAdminLogin(password: String): String? {
    val (code, _) = httpGet(
        AdminEndpoints.pendingServices,
        headers = mapOf("x-admin-password" to password)
    )
    return if (code in 200..299) password else null
} 
private suspend fun apiAdminPOST(path: String, token: String, body: JSONObject? = null): Boolean {
    val (code, _) = if (body == null) {
        httpPost(path, JSONObject(), headers = mapOf("x-admin-password" to token))
    } else {
        httpPost(path, body, headers = mapOf("x-admin-password" to token))
    }
    return code in 200..299
}
private suspend fun apiAdminWalletChange(endpoint: String, token: String, uid: String, amount: Double): Boolean {
    val body = JSONObject().put("uid", uid).put("amount", amount)
    val (code, _) = httpPost(endpoint, body, headers = mapOf("x-admin-password" to token))
    return code in 200..299
}
private suspend fun apiAdminUsersCount(token: String): Int? {
    val (c, t) = httpGet(AdminEndpoints.usersCount, mapOf("x-admin-password" to token))
    return if (c in 200..299 && t != null) try { JSONObject(t.trim()).optInt("count") } catch (_: Exception) { null } else null
}
private suspend fun apiAdminUsersBalances(token: String): List<Triple<String,String,Double>>? {
    val (c, t) = httpGet(AdminEndpoints.usersBalances, mapOf("x-admin-password" to token))
    if (c !in 200..299 || t == null) return null
    return try {
        val trimmed = t.trim()
        val arr: JSONArray = if (trimmed.startsWith("[")) {
            JSONArray(trimmed)
        } else {
            val root = JSONObject(trimmed)
            when {
                root.has("list") -> root.optJSONArray("list") ?: JSONArray()
                root.has("data") -> root.optJSONArray("data") ?: JSONArray()
                else -> JSONArray()
            }
        }
        val out = mutableListOf<Triple<String,String,Double>>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val uid = o.optString("uid")
            val bal = o.optDouble("balance", 0.0)
            val banned = if (o.optBoolean("is_banned", false)) "محظور" else "نشط"
            out += Triple(uid, banned, bal)
        }
        out
    } catch (_: Exception) { null }
}

/** فحص رصيد API (KD1S أولًا ثم مسار الباكند) */
private suspend fun apiAdminProviderBalance(token: String): Double? {
    if (PROVIDER_DIRECT_URL.isNotBlank() && PROVIDER_DIRECT_KEY_VALUE.isNotBlank()) {
        val fields = mapOf("key" to PROVIDER_DIRECT_KEY_VALUE, "action" to "balance")
        val (c, t) = httpPostFormAbs(PROVIDER_DIRECT_URL, fields)
        parseBalancePayload(t)?.let { if (c in 200..299) return it }
    }
    val (c2, t2) = httpGet(AdminEndpoints.providerBalance, mapOf("x-admin-password" to token))
    return if (c2 in 200..299) parseBalancePayload(t2) else null
}

private fun parseBalancePayload(t: String?): Double? {
    if (t == null) return null
    val s = t.trim()
    return try {
        when {
            s.matches(Regex("""\d+(\.\d+)?""")) -> s.toDouble()
            s.startsWith("{") -> {
                val o = JSONObject(s)
                when {
                    o.has("balance") -> o.optString("balance").toDoubleOrNull() ?: o.optDouble("balance", Double.NaN)
                    o.has("data") && o.get("data") is JSONObject -> o.getJSONObject("data").optDouble("balance", Double.NaN)
                    else -> Double.NaN
                }.let { if (it.isNaN()) null else it }
            }
            else -> null
        }
    } catch (_: Exception) { null }
}

/* ============== واجهات إدارة الكروت ============== */
private suspend fun apiAdminFetchPendingCards(token: String): List<PendingCard>? {
    val (c, t) = httpGet(AdminEndpoints.pendingCards, mapOf("x-admin-password" to token))
    if (c !in 200..299 || t == null) return null
    return try {
        val arr = JSONArray(t.trim())
        val out = mutableListOf<PendingCard>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            out += PendingCard(
                id = o.optInt("id"),
                uid = o.optString("uid"),
                card = o.optString("card"),
                createdAt = o.optLong("created_at", 0L)
            )
        }
        out
    } catch (_: Exception) { null }
}
private suspend fun apiAdminRejectTopupCard(id: Int, token: String): Boolean {
    val (c, _) = httpPost(AdminEndpoints.topupCardReject(id), JSONObject(), mapOf("x-admin-password" to token))
    return c in 200..299
}
private suspend fun apiAdminExecuteTopupCard(id: Int, amount: Double, token: String): Boolean {
    val (c, _) = httpPost(
        AdminEndpoints.topupCardExecute(id),
        JSONObject().put("amount", amount),
        mapOf("x-admin-password" to token)
    )
    return c in 200..299
}

/* =========================
   الإعدادات + دخول المالك
   ========================= */
@Composable private fun SettingsDialog(
    uid: String,
    ownerMode: Boolean,
    onUserLogin: (String) -> Unit,
    onUserLoginSuccess: ((String) -> Unit)? = null,
    onOwnerLogin: (token: String) -> Unit,
    onOwnerLogout: () -> Unit,
    onDismiss: () -> Unit
) {
    val clip = LocalClipboardManager.current
    var showAdminLogin by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    var showBindDialog by remember { mutableStateOf(false) }
    var showLoginDialog by remember { mutableStateOf(false) }
    var showRevealDialog by remember { mutableStateOf(false) }
    // حالة ارتباط كلمة المرور بهذا الـ UID
    var isPassBound by remember { mutableStateOf<Boolean?>(null) }
    var loginLinked by remember { mutableStateOf(false) }
    // تحميل حالة البادجات من التخزين فقط (لا مزامنة لحظية)
    val badgeKeyBound = "badge_pass_bound_" + uid
    val badgeKeyLogin = "badge_login_linked_" + uid
    isPassBound = readBadge(ctx, badgeKeyBound)
    loginLinked = readBadge(ctx, badgeKeyLogin)

    // Legacy aliases
    var showBindUserPass by remember { mutableStateOf(false) }
    var showUserLogin by remember { mutableStateOf(false) }
    var snack by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("إغلاق") } },
        title = { Text("الإعدادات", color = OnBg) },
        text = {
            Column {
                Text("المعرّف الخاص بك (UID):", fontWeight = FontWeight.SemiBold, color = OnBg)
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(uid, color = Accent, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.width(8.dp))
                    OutlinedButton(onClick = { clip.setText(AnnotatedString(uid)) }) { Text("نسخ") }
                }
                Spacer(Modifier.height(12.dp))
                Divider(color = Surface1)
                Spacer(Modifier.height(12.dp))

                // ====== أمان الحساب (ربط كلمة مرور + تسجيل دخول + عرض كلمة المرور) ======
                Text("أمان الحساب", color = OnBg, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                
                Column {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        
Box(modifier = Modifier.weight(1f).heightIn(min = 44.dp)) {
    OutlinedButton(
        modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp).alpha(if (isPassBound == true) 0.6f else 1f),
        enabled = (isPassBound != true),
        onClick = { if (isPassBound != true) { showBindDialog = true; showBindUserPass = true } }
    ) { Text("ربط كلمة المرور") }
    if (isPassBound == true) {
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(4.dp)
                .background(Good, RoundedCornerShape(999.dp))
                .padding(horizontal = 4.dp, vertical = 1.dp)
        ) {
            Text("مرتبط", color = Color.White, fontSize = 10.sp)
        }
    }
}

                        
Box(modifier = Modifier.weight(1f).heightIn(min = 44.dp)) {
    OutlinedButton(
        modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp),
        onClick = { showLoginDialog = true; showUserLogin = true }
    ) { Text("تسجيل دخول UID") }
    if (loginLinked) {
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(4.dp)
                .background(Good, RoundedCornerShape(999.dp))
                .padding(horizontal = 4.dp, vertical = 1.dp)
        ) {
            Text("تم دخول", color = Color.White, fontSize = 10.sp)
        }
    }
}
                    }


if (isPassBound == true) {
OutlinedButton(
                        modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp),
                        onClick = { showRevealDialog = true }
                    ) { Text("عرض كلمة المرور") }
}
                }
Spacer(Modifier.height(12.dp))
                Divider(color = Surface1)
                Spacer(Modifier.height(12.dp))
                    

                if (ownerMode) {
                    Text("وضع المالك: مفعل", color = Good, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(6.dp))
                    OutlinedButton(onClick = onOwnerLogout) { Text("تسجيل خروج المالك") }
                } else {
                    Text("تسجيل المالك (كلمة المرور):", fontWeight = FontWeight.SemiBold, color = OnBg)
                    Spacer(Modifier.height(6.dp))
                    OutlinedButton(onClick = { showAdminLogin = true }) { Text("تسجيل المالك") }
                }
            }
        }
    )

    // Dialogs inside Settings
    if (showBindDialog || showBindUserPass) {
        BindPasswordDialog(uid = uid, onDismiss = { showBindDialog = false; showBindUserPass = false }, onBound = { isPassBound = true; saveBadge(ctx, "badge_pass_bound_" + uid, true) }, onToast = { snack = it })
    }
    if (showLoginDialog || showUserLogin) {
        LoginUidDialog(onDismiss = { showLoginDialog = false; showUserLogin = false }, onLogged = { newUid -> 
                            onUserLogin(newUid)
                            loginLinked = true
                            saveBadge(ctx, "badge_login_linked_" + newUid, true)
                            isPassBound = true
                            saveBadge(ctx, "badge_pass_bound_" + newUid, true)
                        }, onToast = { snack = it })
    }
    if (showRevealDialog) {
        RevealPasswordDialog(uid = uid, onDismiss = { showRevealDialog = false }, onToast = { snack = it })
    }

    // snack text
    snack?.let {
        Spacer(Modifier.height(10.dp))
        Text(it, color = OnBg)
        androidx.compose.runtime.LaunchedEffect(it) { kotlinx.coroutines.delay(2000); snack = null }
    }

    if (showAdminLogin) {
        var pass by remember { mutableStateOf("") }
        var err by remember { mutableStateOf<String?>(null) }
        val scope = rememberCoroutineScope()

        AlertDialog(
            onDismissRequest = { showAdminLogin = false },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        err = null
                        val token = apiAdminLogin(pass)
                        if (token != null) { onOwnerLogin(token); showAdminLogin = false }
                        else { err = "بيانات غير صحيحة" }
                    }
                }) { Text("تأكيد") }
            },
            dismissButton = { TextButton(onClick = { showAdminLogin = false }) { Text("إلغاء") } },
            title = { Text("كلمة مرور المالك", color = OnBg) },
            text = {
                Column {
                    OutlinedTextField(
                        value = pass,
                        onValueChange = { pass = it },
                        singleLine = true,
                        label = { Text("أدخل كلمة المرور") },
                        colors = OutlinedTextFieldDefaults.colors(
                            cursorColor = Accent,
                            focusedBorderColor = Accent, unfocusedBorderColor = Dim,
                            focusedLabelColor = OnBg, unfocusedLabelColor = Dim
                        )
                    )
                    if (err != null) {
                        Spacer(Modifier.height(6.dp)); Text(err!!, color = Bad, fontSize = 10.sp)
                    }
                }
            }
        )
    }
}


/* =========================
   حفظ/قراءة حالة الطلبات عبر SharedPreferences
   ========================= */
private fun loadOrderStatusMap(ctx: Context): Map<String, String> {
    val raw = prefs(ctx).getString("order_status_map", "{}") ?: "{}"
    return try {
        val out = mutableMapOf<String, String>()
        val o = JSONObject(raw)
        val it = o.keys()
        while (it.hasNext()) {
            val k = it.next()
            out[k] = o.optString(k, "")
        }
        out
    } catch (_: Exception) { emptyMap() }
}
private fun saveOrderStatusMap(ctx: Context, map: Map<String, String>) {
    val o = JSONObject()
    map.forEach { (k, v) -> o.put(k, v) }
    prefs(ctx).edit().putString("order_status_map", o.toString()).apply()
}

/* =========================
   ربط FCM مع UID على السيرفر
   ========================= */
private suspend fun apiUpdateFcmToken(uid: String, token: String): Boolean {
    val (code, _) = httpPost("/api/users/fcm_token", JSONObject().put("uid", uid).put("fcm", token))
    return code in 200..299
}

/* =========================
   عامل خلفي لفحص اكتمال الطلبات (WorkManager)
   ========================= */
class OrderDoneCheckWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): ListenableWorker.Result {
        val ctx = applicationContext
        return try {
            val uid = loadOrCreateUid(ctx)
            val orders = apiGetMyOrders(uid) ?: emptyList()
            val prev = loadOrderStatusMap(ctx)
            val newMap = prev.toMutableMap()

            orders.forEach { o ->
                val prevStatus = prev[o.id]
                val cur = o.status.name
                if (cur == "Done" && prevStatus != "Done") {
                    AppNotifier.notifyNow(ctx, "تم اكتمال الطلب", "تم تنفيذ ${o.title} بنجاح.")
                    val nn = AppNotice("اكتمال الطلب", "تم تنفيذ ${o.title} بنجاح.", forOwner = false)
                    val existing = loadNotices(ctx)
                    saveNotices(ctx, existing + nn)
                }
                newMap[o.id] = cur
            }
            saveOrderStatusMap(ctx, newMap)
            ListenableWorker.Result.success()
        } catch (_: Throwable) {
            ListenableWorker.Result.retry()
        }
    }

    companion object {
        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val req = PeriodicWorkRequestBuilder<OrderDoneCheckWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context.applicationContext)
                .enqueueUniquePeriodicWork(
                    "order_done_checker",
                    ExistingPeriodicWorkPolicy.UPDATE,
                    req
                )
            // فحص فوري لمرة واحدة عند الإقلاع
            val once = OneTimeWorkRequestBuilder<OrderDoneCheckWorker>().setConstraints(constraints).build()
            WorkManager.getInstance(context.applicationContext).enqueue(once)
        }
    }
}

@Composable
private fun FixedTopBar(
    online: Boolean?,
    unread: Int,
    balance: Double?,
    onOpenNotices: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenWallet: () -> Unit
) {
    Surface(
        color = Surface1,
        contentColor = OnBg,
        shadowElevation = 6.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
                .statusBarsPadding()
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            // كبسولة الرصيد - أيقونة بيضاء ونص واضح
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(Color(0xFF2E3F47))
                    .clickable { onOpenWallet() }
                    .padding(horizontal = 14.dp, vertical = 8.dp)
            ) {
                Text(
                    text = "$ " + (balance?.let { String.format(java.util.Locale.US, "%.2f", it) } ?: "--"),
                    color = Color.White,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.width(10.dp))
                Icon(Icons.Filled.AccountBalanceWallet, contentDescription = null, tint = Color.White, modifier = Modifier.size(18.dp))
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                // إشعارات مع بادج
                NotificationBellCentered(unread = unread, onClick = onOpenNotices)
                Spacer(Modifier.width(8.dp))

                // حالة الخادم
                val (txt, clr) = when (online) {
                    true -> "متصل" to Good
                    false -> "غير متصل" to Bad
                    else -> "..." to Dim
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(clr))
                    Spacer(Modifier.width(6.dp))
                    Text(txt, color = OnBg, fontSize = 10.sp)
                }
                Spacer(Modifier.width(8.dp))

                // الإعدادات
                IconButton(onClick = onOpenSettings) {
                    Icon(Icons.Filled.Settings, contentDescription = null, tint = OnBg)
                }
            }
        }
    }
}

/* =========================
   واجهة مركز الإشعارات
   ========================= */
@Composable
private fun NoticeCenterDialog(
    notices: List<AppNotice>,
    onClear: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("إغلاق") } },
        dismissButton = { TextButton(onClick = onClear) { Text("مسح الإشعارات") } },
        title = { Text("الإشعارات") },
        text = {
            if (notices.isEmpty()) {
                Text("لا توجد إشعارات حاليًا", color = Dim)
            } else {
                LazyColumn {
                    items(notices.sortedByDescending { it.ts }) { itx ->
                        val dt = java.text.SimpleDateFormat("yyyy/MM/dd HH:mm", java.util.Locale.getDefault())
                            .format(java.util.Date(itx.ts))
                        Text("• " + itx.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                        NoticeBody(itx.body)
                        Text(dt, color = Dim, fontSize = 10.sp)
                        Divider(Modifier.padding(vertical = 8.dp), color = Surface1)
                    }
                }
            }
        }
    )
}

@Composable
private fun NotificationBellCentered(
    unread: Int,
    onClick: () -> Unit
) {
    Box {
        IconButton(onClick = onClick) {
            Icon(
                Icons.Filled.Notifications,
                contentDescription = null,
                tint = OnBg
            )
        }
        if (unread > 0) {
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .align(Alignment.TopEnd)
                    .offset(x = (-2).dp, y = 2.dp)
                    .background(Color(0xFFE53935), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = unread.toString(),
                    color = Color.White,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center,
                    maxLines = 1
                )
            }
        }
    }
}


// =========================
// Firebase Messaging Service — يحفظ إشعارات FCM داخل أيقونة الجرس مع التفاصيل
// =========================
class AppFcmService : FirebaseMessagingService() {
    override fun onMessageReceived(msg: RemoteMessage) {
        val ctx = applicationContext
        val d = msg.data
        val title = d["title"] ?: msg.notification?.title ?: "إشعار"
        val bodyTxt  = d["body"] ?: msg.notification?.body ?: ""
        try {
            val existing = loadNotices(ctx)
            val nn = AppNotice(
                title = title,
                body = bodyTxt,
                ts = System.currentTimeMillis(),
                forOwner = false,
                orderId = d["order_id"],
                serviceName = d["service_name"],
                amount = d["amount"],
                code = d["code"],
                status = d["status"]
            )
            saveNotices(ctx, existing + nn)
        } catch (_: Throwable) { }
        AppNotifier.notifyNow(ctx, title, bodyTxt)
    }
}


@Composable
private fun AdminAnnouncementsHub(
    token: String,
    onBack: () -> Unit
) {
    var screen by remember { mutableStateOf<String?>(null) } // "create" | "list"

    if (screen == null) {
        Column(Modifier.fillMaxSize().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text("إعلانات التطبيق", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = OnBg, modifier = Modifier.weight(1f))
                TextButton(onClick = onBack) { Text("رجوع") }
            }
            Spacer(Modifier.height(12.dp))
            ElevatedButton(
                onClick = { screen = "create" },
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
            ) { Text("إنشاء إعلان") }
            ElevatedButton(
                onClick = { screen = "list" },
                modifier = Modifier.fillMaxWidth()
            ) { Text("عرض الإعلانات") }
        }
    } else {
        when (screen) {
            "create" -> AdminAnnouncementScreen(token = token, onBack = { screen = null })
            "list" -> AdminAnnouncementsList(token = token, onBack = { screen = null })
        }
    }
}

@Composable
private fun AdminAnnouncementsList(
    token: String,
    onBack: () -> Unit
) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<Announcement>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var refreshKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(refreshKey) {
        loading = true; err = null
        try {
            list = apiFetchAdminAnnouncements(token, 200).sortedByDescending { it.createdAt }
        } catch (e: Exception) {
            err = "تعذر جلب الإعلانات"
        } finally { loading = false }
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text("عرض الإعلانات", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))

        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            list.isEmpty() -> Text("لا توجد إعلانات.", color = Dim)
            else -> {
                LazyColumn {
                    items(list.size) { idx ->
                        val ann = list[idx]
                        var showEdit by remember { mutableStateOf(false) }
                        var showDelete by remember { mutableStateOf(false) }
                        Card(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                            colors = CardDefaults.cardColors(containerColor = Surface1, contentColor = OnBg)
                        ) {
                            Column(Modifier.padding(16.dp)) {
                                Text(ann.title ?: "إعلان مهم 📢", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = OnBg)
                                Spacer(Modifier.height(6.dp))
                                Text(ann.body, color = OnBg)
                                Spacer(Modifier.height(6.dp))
                                val ts = if (ann.createdAt > 0) ann.createdAt else System.currentTimeMillis()
                                val formatted = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.getDefault())
                                    .format(java.util.Date(ts))
                                Text(formatted, fontSize = 10.sp, color = Dim)
                                Spacer(Modifier.height(8.dp))
                                Row {
                                    TextButton(onClick = { showEdit = true }) { Text("تعديل الإعلان") }
                                    Spacer(Modifier.width(6.dp))
                                    TextButton(onClick = { showDelete = true }) { Text("حذف الإعلان") }
                                }
                            }
                        }

                        if (showEdit) {
                            var title by remember { mutableStateOf(ann.title ?: "") }
                            var body by remember { mutableStateOf(ann.body) }
                            AlertDialog(
                                onDismissRequest = { showEdit = false },
                                confirmButton = {
                                    TextButton(onClick = {
                                        val id = ann.id
                                        if (id != null && id > 0) {
                                            scope.launch {
                                                val ok = apiAdminUpdateAnnouncement(token, id, title.ifBlank { null }, body)
                                                showEdit = false
                                                snack = if (ok) "تم الحفظ" else "فشل التعديل"
                                                if (ok) refreshKey++
                                            }
                                        } else {
                                            showEdit = false
                                            snack = "لا يدعم الخادم تعديل هذا الإعلان (معرّف مفقود)"
                                        }
                                    }) { Text("حفظ") }
                                },
                                dismissButton = { TextButton(onClick = { showEdit = false }) { Text("إلغاء") } },
                                title = { Text("تعديل الإعلان", color = OnBg) },
                                text = {
                                    Column {
                                        OutlinedTextField(value = title, onValueChange = { title = it }, singleLine = true, label = { Text("العنوان (اختياري)") })
                                        Spacer(Modifier.height(8.dp))
                                        OutlinedTextField(value = body, onValueChange = { body = it }, minLines = 5, label = { Text("نص الإعلان") })
                                    }
                                }
                            )
                        }

                        if (showDelete) {
                            AlertDialog(
                                onDismissRequest = { showDelete = false },
                                confirmButton = {
                                    TextButton(onClick = {
                                        val id = ann.id
                                        if (id != null && id > 0) {
                                            scope.launch {
                                                val ok = apiAdminDeleteAnnouncement(token, id)
                                                showDelete = false
                                                snack = if (ok) "تم الحذف" else "فشل الحذف"
                                                if (ok) refreshKey++
                                            }
                                        } else {
                                            showDelete = false
                                            snack = "لا يدعم الخادم حذف هذا الإعلان (معرّف مفقود)"
                                        }
                                    }) { Text("تأكيد الحذف") }
                                },
                                dismissButton = { TextButton(onClick = { showDelete = false }) { Text("إلغاء") } },
                                title = { Text("تأكيد الحذف", color = OnBg) },
                                text = { Text("هل أنت متأكد من حذف هذا الإعلان؟", color = OnBg) }
                            )
                        }
                    }
                }
            }
        }

        snack?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, color = OnBg)
            androidx.compose.runtime.LaunchedEffect(it) { kotlinx.coroutines.delay(2000); snack = null }
        }
    }
}



/* ====== حوار ربط كلمة المرور ====== */
@Composable
private fun BindPasswordDialog(uid: String, onDismiss: () -> Unit, onBound: (String) -> Unit, onToast: (String)->Unit) {
    val ctx = LocalContext.current
    var pwd by remember { mutableStateOf("") }
    var pwd2 by remember { mutableStateOf("") }
    var show1 by remember { mutableStateOf(false) }
    var show2 by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { if (!sending) onDismiss() },
        title = { Text("ربط كلمة المرور بالحساب") },
        text = {
            Column {
                OutlinedTextField(value = pwd, onValueChange = { pwd = it }, label = { Text("كلمة المرور") },
                    visualTransformation = if (show1) androidx.compose.ui.text.input.VisualTransformation.None else androidx.compose.ui.text.input.PasswordVisualTransformation(),
                    trailingIcon = {
                        TextButton(onClick = { show1 = !show1 }) { Text(if (show1) "إخفاء" else "عرض") }
                    })
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = pwd2, onValueChange = { pwd2 = it }, label = { Text("تأكيد كلمة المرور") },
                    visualTransformation = if (show2) androidx.compose.ui.text.input.VisualTransformation.None else androidx.compose.ui.text.input.PasswordVisualTransformation(),
                    trailingIcon = {
                        TextButton(onClick = { show2 = !show2 }) { Text(if (show2) "إخفاء" else "عرض") }
                    })
            }
        },
        confirmButton = {
            TextButton(enabled = !sending, onClick = {
                if (pwd.length < 4) { onToast("كلمة المرور قصيرة"); return@TextButton }
                if (pwd != pwd2)   { onToast("كلمتا المرور غير متطابقتين"); return@TextButton }
                sending = true
                kotlinx.coroutines.GlobalScope.launch(kotlinx.coroutines.Dispatchers.Main) {
                    try {
                        val obj = org.json.JSONObject().put("uid", uid).put("password", pwd)
                        val (code, _) = httpPost("/api/users/bind_password", obj)
                        if (code in 200..299) {
                            saveLocalPassword(ctx, uid, pwd)
                            onToast("تم الربط بنجاح")
                            onBound(pwd)
                            onDismiss()
                        } else onToast("فشل الربط ($code)")
                    } catch (t: Throwable) { onToast("خطأ: ${t.message}") }
                    finally { sending = false }
                }
            }) { Text(if (sending) "يرسل" else "تثبيت") }
        },
        dismissButton = { TextButton(enabled = !sending, onClick = onDismiss) { Text("إلغاء") } }
    )
}

/* ====== حوار تسجيل الدخول ====== */
@Composable
private fun LoginUidDialog(onDismiss: () -> Unit, onLogged: (String) -> Unit, onToast: (String)->Unit) {
    val ctx = LocalContext.current
    var uidIn by remember { mutableStateOf("") }
    var pwd by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    var sending by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { if (!sending) onDismiss() },
        title = { Text("تسجيل دخول UID") },
        text = {
            Column {
                OutlinedTextField(value = uidIn, onValueChange = { if (it.length <= 24) uidIn = it.filter { ch -> ch.isLetterOrDigit() } }, label = { Text("UID") })
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = pwd, onValueChange = { pwd = it }, label = { Text("كلمة المرور") },
                    visualTransformation = if (show) androidx.compose.ui.text.input.VisualTransformation.None else androidx.compose.ui.text.input.PasswordVisualTransformation(),
                    trailingIcon = { TextButton(onClick = { show = !show }) { Text(if (show) "إخفاء" else "عرض") } })
            }
        },
        confirmButton = {
            TextButton(enabled = !sending, onClick = {
                if (uidIn.isBlank() || pwd.isBlank()) { onToast("أكمل الحقول") ; return@TextButton }
                sending = true
                kotlinx.coroutines.GlobalScope.launch(kotlinx.coroutines.Dispatchers.Main) {
                    try {
                        val obj = org.json.JSONObject().put("uid", uidIn).put("password", pwd)
                        val (code, _) = httpPost("/api/users/login", obj)
                        if (code in 200..299) {
                            saveLocalPassword(ctx, uidIn, pwd)
                            onToast("تم تسجيل الدخول")
                            onLogged(uidIn)
                            onDismiss()
                        } else onToast("فشل تسجيل الدخول ($code)")
                    } catch (t: Throwable) { onToast("خطأ: ${t.message}") }
                    finally { sending = false }
                }
            }) { Text(if (sending) "يدخل" else "تسجيل الدخول") }
        },
        dismissButton = { TextButton(enabled = !sending, onClick = onDismiss) { Text("إلغاء") } }
    )
}

/* ====== طلب تأكيد قفل الجهاز + إظهار كلمة المرور ====== */
@Composable
private fun revealPassword(ctx: Context, uid: String) {
    var show by remember { mutableStateOf(false) }
    var value by remember { mutableStateOf<String?>(null) }
    val activity = LocalContext.current as? android.app.Activity
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()
    ) { res ->
        if (res.resultCode == android.app.Activity.RESULT_OK) {
            value = loadLocalPassword(ctx, uid)
            show = true
        }
    }
    LaunchedEffect(Unit) {
        val km = ctx.getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
        val intent = km.createConfirmDeviceCredentialIntent("تأكيد الهوية", "أدخل قفل الجهاز لعرض كلمة المرور")
        if (intent != null && activity != null) {
            launcher.launch(intent)
        } else {
            value = loadLocalPassword(ctx, uid); show = true
        }
    }
    if (show) {
        AlertDialog(
            onDismissRequest = { show = false },
            title = { Text("كلمة المرور المحفوظة") },
            text = {
                val v = value ?: "لا توجد كلمة مرور محفوظة"
                Column {
                    SelectionContainer { Text(v, color = OnBg) }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        val clip = LocalClipboardManager.current
                        OutlinedButton(onClick = { clip.setText(AnnotatedString(v)) }) { Text("نسخ") }
                        OutlinedButton(onClick = { show = false }) { Text("تم") }
                    }
                }
            },
            confirmButton = {},
            dismissButton = {}
        )
    }
}

/* ====== حوار عرض كلمة المرور (تحقّق خادم + تأكيد قفل الجهاز) ====== */

@Composable
private fun RevealPasswordDialog(uid: String, onDismiss: () -> Unit, onToast: (String) -> Unit) {
    val ctx = LocalContext.current
    val activity = LocalContext.current as? android.app.Activity
    var sending by remember { mutableStateOf(false) }
    var revealed by remember { mutableStateOf<String?>(null) }
    var showResult by remember { mutableStateOf(false) }

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { res ->
        if (res.resultCode == android.app.Activity.RESULT_OK) {
            kotlinx.coroutines.GlobalScope.launch(kotlinx.coroutines.Dispatchers.Main) {
                sending = true
                try {
                    val obj = org.json.JSONObject().put("uid", uid)
                    val (code, body) = httpPost("/api/users/reveal_password", obj)
                    if (code in 200..299) {
                        val j = org.json.JSONObject(body ?: "{}")
                        val pw = j.optString("password", "")
                        if (pw.isNotBlank()) {
                            saveLocalPassword(ctx, uid, pw)
                            revealed = pw
                            showResult = true
                        } else onToast("لا توجد كلمة مرور محفوظة")
                    } else onToast("فشل العرض ($code)")
                } catch (t: Throwable) { onToast("خطأ: ${t.message}") }
                finally { sending = false }
            }
        }
    }

    AlertDialog(
        onDismissRequest = { if (!sending) onDismiss() },
        title = { Text("عرض كلمة المرور") },
        text = {
            Column {
                Text("لأمانك سيتم التحقق من قفل الجهاز مباشرةً، وبعد النجاح سنعرض كلمة المرور المخزّنة.", color = OnBg)
                Spacer(Modifier.height(8.dp))
            }
        },
        confirmButton = {
            TextButton(enabled = !sending, onClick = {
                val km = ctx.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
                val intent = km.createConfirmDeviceCredentialIntent("تأكيد الهوية", "أدخل قفل الجهاز للمتابعة")
                if (intent != null && activity != null) launcher.launch(intent) else onToast("يتطلب قفل جهاز مُفعّل")
            }) { Text(if (sending) "جاري..." else "متابعة") }
        },
        dismissButton = { TextButton(enabled = !sending, onClick = onDismiss) { Text("إلغاء") } }
    )

    if (showResult) {
        AlertDialog(
            onDismissRequest = { showResult = false },
            title = { Text("كلمة المرور") },
            text = {
                val v = revealed ?: ""
                Column {
                    SelectionContainer { Text(v, color = OnBg) }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        val clip = LocalClipboardManager.current
                        OutlinedButton(onClick = { clip.setText(AnnotatedString(v)) }) { Text("نسخ") }
                        OutlinedButton(onClick = { showResult = false; onDismiss() }) { Text("تم") }
                    }
                }
            },
            confirmButton = {},
            dismissButton = {}
        )
    }
}



    // --- Badge state persistence ---
    private const val BADGE_PREF = "badge_state_v1"
    private fun badgePrefs(ctx: Context): android.content.SharedPreferences =
        ctx.getSharedPreferences(BADGE_PREF, android.content.Context.MODE_PRIVATE)
    private fun saveBadge(ctx: Context, key: String, value: Boolean) {
        badgePrefs(ctx).edit().putBoolean(key, value).apply()
    }
    private fun readBadge(ctx: Context, key: String): Boolean =
        badgePrefs(ctx).getBoolean(key, false)
