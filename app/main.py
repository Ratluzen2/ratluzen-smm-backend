

@file:Suppress("UnusedImport", "SpellCheckingInspection")
@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.zafer.smm
import androidx.compose.material3.MaterialTheme
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

private const val OWNER_UID_BACKEND = "OWNER-0001" // يجب أن يطابق OWNER_UID في السيرفر

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

@Composable
private fun NoticeBody(text: String) {
    val clip = LocalClipboardManager.current
    val codeRegex = "(?:الكود|code|card|voucher|redeem)\\s*[:：-]?\\s*([A-Za-z0-9][A-Za-z0-9-]{5,})".toRegex(RegexOption.IGNORE_CASE)
    val match = codeRegex.find(text)
    if (match != null) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            SelectionContainer {
                Text(text, color = Dim, fontSize = 12.sp, modifier = Modifier.weight(1f))
            }
            TextButton(onClick = {
                val c = match.groupValues.getOrNull(1) ?: text
                clip.setText(AnnotatedString(c))
            }) { Text("نسخ") }
        }
    } else {
        SelectionContainer {
            Text(text, color = Dim, fontSize = 12.sp)
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
data class PublicPricingEntry(val pricePerK: Double, val minQty: Int, val maxQty: Int, val mode: String = "per_k")

private suspend fun apiPublicPricingBulk(keys: List<String>): Map<String, PublicPricingEntry> {
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

@Composable
private fun PricingEditorScreen(token: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var selectedCat by remember { mutableStateOf<String?>(null) }
    var overrides by remember { mutableStateOf<Map<String, PricingOverride>>(emptyMap()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var refreshKey by remember { mutableStateOf(0) }
    var snack by remember { mutableStateOf<String?>(null) }

    val cats = listOf(
        
        "مشاهدات تيكتوك", "لايكات تيكتوك", "متابعين تيكتوك", "مشاهدات بث تيكتوك", "رفع سكور تيكتوك",
        "مشاهدات انستغرام", "لايكات انستغرام", "متابعين انستغرام", "مشاهدات بث انستا", "خدمات التليجرام",
        "ببجي", "لودو"
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
        snack?.let { s -> Snackbar(Modifier.fillMaxWidth()) { Text(s) }; LaunchedEffect(s) { kotlinx.coroutines.delay(2000); snack = null } }
        err?.let { e -> Text("تعذر جلب البيانات: $e", color = Bad); return@Column }

        if (selectedCat == null) {
            cats.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth()) {
                    row.forEach { c ->
                        ElevatedCard(
                            modifier = Modifier.weight(1f).padding(4.dp).clickable { selectedCat = c },
                            colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
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
if (selectedCat == "ببجي" || selectedCat == "لودو") {
    // عرض باقات ببجي/لودو وتعديل السعر والكمية بشكل مخصص لكل باقة
    data class PkgSpec(val key: String, val title: String, val defQty: Int, val defPrice: Double)
    val scope = rememberCoroutineScope()

    val pkgs: List<PkgSpec> = if (selectedCat == "ببجي") listOf(
        PkgSpec("pkg.pubg.60",   "60 شدة",    60,    2.0),
        PkgSpec("pkg.pubg.325",  "325 شدة",   325,   9.0),
        PkgSpec("pkg.pubg.660",  "660 شدة",   660,   15.0),
        PkgSpec("pkg.pubg.1800", "1800 شدة",  1800,  40.0),
        PkgSpec("pkg.pubg.3850", "3850 شدة",  3850,  55.0),
        PkgSpec("pkg.pubg.8100", "8100 شدة",  8100,  100.0),
        PkgSpec("pkg.pubg.16200","16200 شدة", 16200, 185.0)
    ) else listOf(
        // Diamonds
        PkgSpec("pkg.ludo.diamonds.810",     "810 الماسة",       810,     5.0),
        PkgSpec("pkg.ludo.diamonds.2280",    "2280 الماسة",      2280,    10.0),
        PkgSpec("pkg.ludo.diamonds.5080",    "5080 الماسة",      5080,    20.0),
        PkgSpec("pkg.ludo.diamonds.12750",   "12750 الماسة",     12750,   35.0),
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

    LazyColumn {
        items(pkgs) { p ->
            val ov = overrides[p.key]
            val curPrice = ov?.pricePerK ?: p.defPrice
            val curQty   = if (ov != null && ov.minQty > 0) ov.minQty else p.defQty

            var open by remember { mutableStateOf(false) }
            ElevatedCard(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(p.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                    Spacer(Modifier.height(4.dp))
                    Text("الكمية الحالية: $curQty  •  السعر الحالي: ${"%.2f".format(curPrice)}", color = Dim, fontSize = 12.sp)
                    Spacer(Modifier.height(8.dp))
                    Row {
                        TextButton(onClick = { open = true }) { Text("تعديل") }
                        Spacer(Modifier.width(6.dp))
                        if (ov != null) {
                            TextButton(onClick = {
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
                var priceTxt by remember { mutableStateOf(TextFieldValue(curPrice.toString())) }
                var qtyTxt   by remember { mutableStateOf(TextFieldValue(curQty.toString())) }
                AlertDialog(
                    onDismissRequest = { open = false },
                    confirmButton = {
                        TextButton(onClick = {
                            scope.launch {
                                val newPrice = priceTxt.text.toDoubleOrNull() ?: 0.0
                                val newQty   = qtyTxt.text.toIntOrNull() ?: 0
                                val ok = apiAdminSetPricing(
                                    token = token,
                                    uiKey = p.key,
                                    pricePerK = newPrice,
                                    minQty = newQty,
                                    maxQty = newQty,
                                    mode = "package"
                                )
                                if (ok) { snack = "تم الحفظ"; open = false; refreshKey++ } else snack = "فشل الحفظ"
                            }
                        }) { Text("حفظ") }
                    },
                    dismissButton = { TextButton(onClick = { open = false }) { Text("إلغاء") } },
                    title = { Text("تعديل: ${p.title}") },
                    text  = {
                        Column {
                            OutlinedTextField(value = priceTxt, onValueChange = { priceTxt = it }, label = { Text("السعر") }, singleLine = true)
                            Spacer(Modifier.height(6.dp))
                            OutlinedTextField(value = qtyTxt, onValueChange = { qtyTxt = it }, label = { Text("الكمية") }, singleLine = true)
                        }
                    }
                )
            }
        }
    }
    return@Column
}

            }
            Spacer(Modifier.height(10.dp))

            LazyColumn {
                items(list) { svc ->
                    var showEdit by remember { mutableStateOf(false) }
                    val key = svc.uiKey
                    val ov  = overrides[key]
                    val has = ov != null
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(key, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            val tip = if (has) " (معدل)" else " (افتراضي)"
                            Text("السعر/ألف: ${ov?.pricePerK ?: svc.pricePerK}  •  الحد الأدنى: ${ov?.minQty ?: svc.min}  •  الحد الأقصى: ${ov?.maxQty ?: svc.max}$tip", color = Dim, fontSize = 12.sp)
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

    ElevatedCard(
            modifier = Modifier
                .fillMaxWidth()
                .padding(4.dp)
                .clickable { open = true },
        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
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
private val Dim      = Color(0xFFAAB3BB)

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
),
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

setContent { AppTheme { UpdatePromptHost(); AppRoot() } }
    }
}

/* =========================
   Root
   ========================= */
@Composable
fun AppRoot() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()

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


    if (showSettings) {
        SettingsDialog(
            uid = uid,
            ownerMode = ownerMode,
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
    ElevatedCard(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        colors = CardDefaults.elevatedCardColors(
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
data class Announcement(val title: String?, val body: String, val createdAt: Long)


private suspend fun apiAdminCreateAnnouncement(token: String, title: String?, body: String): Boolean {
    val obj = org.json.JSONObject().put("body", body)
    if (!title.isNullOrBlank()) obj.put("title", title)
    val (code, _) = httpPost(AdminEndpoints.announcementCreate, obj, headers = mapOf("x-admin-password" to token))
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
                            Text(formatted, fontSize = 12.sp, color = Dim)
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
        if (error != null) { Spacer(Modifier.height(6.dp)); Text(error!!, color = Bad, fontSize = 12.sp) }
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
                ElevatedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 8.dp)
                        .clickable { selectedCategory = cat },
                    colors = CardDefaults.elevatedCardColors(
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
    val keys = remember(inCat, selectedCategory) { inCat.map { it.uiKey } }
    val effectiveMap by produceState<Map<String, PublicPricingEntry>>(initialValue = emptyMap(), keys) {
        value = try { apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
    }
    val listToShow = remember(inCat, effectiveMap) {
        inCat.map { s ->
            val ov = effectiveMap[s.uiKey]
            if (ov != null) s.copy(min = ov.minQty, max = ov.maxQty, pricePerK = ov.pricePerK) else s
        }
    }
    if (inCat.isNotEmpty()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { selectedCategory = null }) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg)
                }
                Spacer(Modifier.width(6.dp))
                Text(selectedCategory!!, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
            }
            Spacer(Modifier.height(10.dp))

            inCat.forEach { svc ->
                ElevatedCard(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 8.dp)
                        .clickable { selectedService = svc },
                    colors = CardDefaults.elevatedCardColors(
                        containerColor = Surface1,
                        contentColor = OnBg
                    )
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text(svc.uiKey, fontWeight = FontWeight.SemiBold, color = OnBg)
                        Text("الكمية: ${svc.min} - ${svc.max}", color = Dim, fontSize = 12.sp)
                        Text("السعر لكل 1000: ${svc.pricePerK}\$", color = Dim, fontSize = 12.sp)
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
                Text("الكمية بين ${service.min} و ${service.max}", color = Dim, fontSize = 12.sp)
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
                        "يرجى إطفاء زر 'تميز للمراجعة' داخل حسابك الانستغرام قبل ارسال رابط الخدمه لضمان إكمال طلبك!",
                        color = Dim, fontSize = 12.sp
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
                        color = Dim, fontSize = 12.sp
                    )
                }
    
                Spacer(Modifier.height(8.dp))
                Text("السعر التقريبي: $price\$", fontWeight = FontWeight.SemiBold, color = OnBg)
                Spacer(Modifier.height(4.dp))
                Text("رصيدك الحالي: ${userBalance?.let { "%.2f".format(it) } ?: ""}\$", color = Dim, fontSize = 12.sp)
            }
        }
    )
}

/* =========================
   Amount Picker (iTunes & Phone Cards)
   ========================= */
data class AmountOption(val label: String, val usd: Int)

private val commonAmounts = listOf(5,10,15,20,25,30,40,50,100)

private fun priceForItunes(usd: Int): Double {
    // كل 5$ = 9$
    val steps = (usd / 5.0)
    return steps * 9.0
}
private fun priceForAtheerOrAsiacell(usd: Int): Double {
    // كل 5$ = 7$
    val steps = (usd / 5.0)
    return steps * 7.0
}
private fun priceForKorek(usd: Int): Double {
    // كل 5$ = 7$
    val steps = (usd / 5.0)
    return steps * 7.0
}

@Composable
private fun AmountGrid(
    title: String,
    subtitle: String,
    amounts: List<Int>,
    priceOf: (Int) -> Double,
    onSelect: (usd: Int, price: Double) -> Unit,
    onBack: () -> Unit
) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Column {
                Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
                if (subtitle.isNotBlank()) Text(subtitle, color = Dim, fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(12.dp))

        val rows = amounts.chunked(2)
        rows.forEach { pair ->
            Row(Modifier.fillMaxWidth()) {
                pair.forEach { usd ->
                    val price = String.format(java.util.Locale.getDefault(), "%.2f", priceOf(usd))
                    ElevatedCard(
                        modifier = Modifier.weight(1f)
                            .padding(4.dp)
                            .clickable { onSelect(usd, priceOf(usd)) },
                        colors = CardDefaults.elevatedCardColors(
                            containerColor = Surface1,
                            contentColor = OnBg
                        )
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("$usd$", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            Text("السعر: $price$", color = Dim, fontSize = 12.sp)
                        }
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
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
                Text("سيتم إرسال الطلب للمراجعة من قِبل المالك وسيصلك إشعار عند التنفيذ.", color = Dim, fontSize = 12.sp)
            }
        }
    )

}

/* الأقسام اليدوية (ايتونز/هاتف/ببجي/لودو) */

/* =========================
   Package Picker (PUBG / Ludo)
   ========================= */
data class PackageOption(val label: String, val priceUsd: Int)

val pubgPackages = listOf(
    PackageOption("60 شدة", 2),
    PackageOption("325 شدة", 9),
    PackageOption("660 شدة", 15),
    PackageOption("1800 شدة", 40),
    PackageOption("3850 شدة", 55),
    PackageOption("8100 شدة", 100),
    PackageOption("16200 شدة", 185)
)
val ludoDiamondsPackages = listOf(
    PackageOption("810 الماسة", 5),
    PackageOption("2280 الماسة", 10),
    PackageOption("5080 الماسة", 20),
    PackageOption("12750 الماسة", 35),
    PackageOption("27200 الماسة", 85),
    PackageOption("54900 الماسة", 165),
    PackageOption("164800 الماسة", 475),
    PackageOption("275400 الماسة", 800)
)
val ludoGoldPackages = listOf(
    PackageOption("66680 ذهب", 5),
    PackageOption("219500 ذهب", 10),
    PackageOption("1443000 ذهب", 20),
    PackageOption("3627000 ذهب", 35),
    PackageOption("9830000 ذهب", 85),
    PackageOption("24835000 ذهب", 165),
    PackageOption("74550000 ذهب", 475),
    PackageOption("124550000 ذهب", 800)
)

@Composable
/* ===== Helpers for PUBG/Ludo package overrides ===== */
private fun extractDigits(s: String): String = s.filter { it.isDigit() }

@Composable
private fun packagesWithOverrides(
    base: List<PackageOption>,
    keyPrefix: String,
    unit: String
): List<PackageOption> {
    val result by produceState(initialValue = base, base) {
        val keys = base.mapNotNull { opt ->
            val qty = opt.label.filter { it.isDigit() }
            if (qty.isEmpty()) null else "$keyPrefix$qty"
        }
        val map = try { apiPublicPricingBulk(keys) } catch (_: Throwable) { emptyMap() }
        value = base.map { opt ->
            val qtyStr = opt.label.filter { it.isDigit() }
            val k = if (qtyStr.isEmpty()) "" else "$keyPrefix$qtyStr"
            val ov = map[k]
            val newQty = ov?.minQty?.takeIf { it > 0 } ?: qtyStr.toIntOrNull() ?: 0
            val newPrice = ov?.pricePerK ?: opt.priceUsd.toDouble()
            val newLabel = if (newQty > 0) "$newQty $unit" else opt.label
            PackageOption(newLabel, kotlin.math.round(newPrice).toInt())
        }
    }
    return result
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
                if (subtitle.isNotBlank()) Text(subtitle, color = Dim, fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(12.dp))

        val rows = packages.chunked(2)
        rows.forEach { pair ->
            Row(Modifier.fillMaxWidth()) {
                pair.forEach { opt ->
                    ElevatedCard(
                        modifier = Modifier.weight(1f)
                            .padding(4.dp)
                            .clickable { onSelect(opt) },
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1)
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Text(opt.label, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            Text("السعر: ${'$'}${opt.priceUsd}", color = Dim, fontSize = 12.sp)
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
                Text("السعر المستحق: ${'$'}$priceUsd", color = Dim)
                Spacer(Modifier.height(8.dp))
                Text("سيتم إرسال الطلب للمراجعة من قِبل المالك وسيصلك إشعار عند التنفيذ.", color = Dim, fontSize = 12.sp)
            }
        }
    )
}

@Composable
fun ConfirmPackageIdDialog(
    sectionTitle: String,
    label: String,
    priceUsd: Int,
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
                Text("السعر المستحق: ${'$'}$priceUsd", color = Dim)
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = accountId,
                    onValueChange = { accountId = it },
                    singleLine = true,
                    label = { Text("معرّف اللاعب / Game ID") }
                )
                Spacer(Modifier.height(6.dp))
                Text("أدخل رقم الحساب بدقة. الطلب لن يُرسل بدون هذا الحقل.", color = Dim, fontSize = 12.sp)
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
    var pendingPkgPrice by remember { mutableStateOf<Int?>(null) }

    val items = when (title) {
        "قسم شراء رصيد ايتونز" -> listOf("شراء رصيد ايتونز")
        "قسم شراء رصيد هاتف"  -> listOf("شراء رصيد اثير", "شراء رصيد اسياسيل", "شراء رصيد كورك")
        "قسم شحن شدات ببجي"    -> listOf("شحن شدات ببجي")
        "قسم خدمات الودو"       -> listOf("شراء الماسات لودو", "شراء ذهب لودو")
        else -> emptyList()
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).padding(bottom = 100.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = OnBg) }
            Spacer(Modifier.width(6.dp))
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = OnBg)
        }
        Spacer(Modifier.height(10.dp))

        items.forEach { name ->
            ElevatedCard(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
                    .clickable {
                        selectedManualFlow = name
                    },
                colors = CardDefaults.elevatedCardColors(
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
    if (selectedManualFlow != null) {
        when (selectedManualFlow) {
            "شراء رصيد ايتونز" -> {
                AmountGrid(
                    title = "شراء رصيد ايتونز",
                    subtitle = "كل 5$ = 9$",
                    amounts = commonAmounts,
                    priceOf = { usd -> priceForItunes(usd) },
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
                    subtitle = "كل 5$ = 7$",
                    amounts = commonAmounts,
                    priceOf = { usd -> priceForAtheerOrAsiacell(usd) },
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
                    subtitle = "كل 5$ = 7$",
                    amounts = commonAmounts,
                    priceOf = { usd -> priceForAtheerOrAsiacell(usd) },
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
                    subtitle = "كل 5$ = 7$",
                    amounts = commonAmounts,
                    priceOf = { usd -> priceForKorek(usd) },
                    onSelect = { usd, price ->
                        pendingUsd = usd
                        pendingPrice = price
                    },
                    onBack = { selectedManualFlow = null; pendingUsd = null; pendingPrice = null }
                )
            }
            "شحن شدات ببجي" -> {
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
                        val (ok, txt) = apiCreateManualPaidOrder(uid, product, priceInt, accountId)
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

        ElevatedCard(
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
            colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
        ) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.SimCard, null, tint = Accent)
                Spacer(Modifier.width(8.dp))
                Text("شحن عبر أسيا سيل (كارت)", fontWeight = FontWeight.SemiBold, color = OnBg)
            }
        }

        listOf(
            "شحن عبر هلا بي",
            "شحن عبر نقاط سنتات",
            "شحن عبر سوبركي",
            "شحن عبر زين كاش",
            "شحن عبر عملات رقمية (USDT)"
        ).forEach {
            ElevatedCard(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp).clickable {
                    onToast("لإتمام الشحن تواصل مع الدعم (واتساب/تيليجرام).")
                    onAddNotice(AppNotice("شحن رصيد", "يرجى التواصل مع الدعم لإكمال شحن: $it", forOwner = false))
                },
                colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.AttachMoney, null, tint = Accent)
                    Spacer(Modifier.width(8.dp))
                    Text(it, fontWeight = FontWeight.SemiBold, color = OnBg)
                }
            }
        }
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
                    Text("أدخل رقم الكارت (فوق 10 أرقام):", color = Dim, fontSize = 12.sp)
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
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(o.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Text("الكمية: ${o.quantity} | السعر: ${"%.2f".format(o.price)}$", color = Dim, fontSize = 12.sp)
                            Text("المعرف: ${o.id}", color = Dim, fontSize = 12.sp)
                            Text("الحالة: ${o.status}", color = when (o.status) {
                                OrderStatus.Done -> Good
                                OrderStatus.Rejected -> Bad
                                OrderStatus.Refunded -> Accent
                                else -> OnBg
                            }, fontSize = 12.sp)
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
            IconButton(onClick = { current = "notices" }) {
                Icon(Icons.Filled.Notifications, contentDescription = null, tint = OnBg)
            }
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
                        ) { Text(title, fontSize = 12.sp) }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        } else {
            when (current) {
                "announce" -> AdminAnnouncementScreen(token = token!!, onBack = { current = null })
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
                "pending_itunes" -> AdminPendingGenericList(title = "طلبات iTunes المعلقة",
                    token = token!!,
                    fetchUrl = AdminEndpoints.pendingItunes,
                    itemFilter = { true },
                    approveWithCode = true,                                      // ✅ يطلب كود آيتونز
                    codeFieldLabel = "كود الايتونز",
                    onBack = { current = null }
                )
                "pending_pubg" -> AdminPendingGenericList(
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
                "pending_phone" -> AdminPendingGenericList(

                    title = "طلبات شراء الكارتات",
                    token = token!!,
                    // يمكن أن يعود من مسار مخصص للأرصدة؛ إن لم يوجد نستعمل services مع فلترة العنوان:
                    fetchUrl = AdminEndpoints.pendingBalances,
                    itemFilter = { item -> isIraqTelcoCardPurchase(item.title) },
                    approveWithCode = true,                                      // ✅ يطلب رقم الكارت
                    codeFieldLabel = "كود الكارت",
                    onBack = { current = null }
                )
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

    var approveFor by remember { mutableStateOf<OrderItem?>(null) }
    var codeText by remember { mutableStateOf("") }

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

        when {
            loading -> Text("يتم التحميل", color = Dim)
            err != null -> Text(err!!, color = Bad)
            list.isNullOrEmpty() -> Text("لا يوجد شيء معلق.", color = Dim)
            else -> LazyColumn {
                items(list!!) { o ->
                    val dt = if (o.createdAt > 0) {
                        SimpleDateFormat("yyyy/MM/dd HH:mm", Locale.getDefault()).format(Date(o.createdAt))
                    } else ""
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(o.title, fontWeight = FontWeight.SemiBold, color = OnBg)
                            if (o.uid.isNotBlank()) Text("UID: ${o.uid}", color = Dim, fontSize = 12.sp)
                            if (o.payload.isNotBlank()) {
                                Spacer(Modifier.height(4.dp))
                                Text("تفاصيل: ${o.payload}", color = Dim, fontSize = 12.sp)
                            }
                            if (dt.isNotEmpty()) {
                                Spacer(Modifier.height(4.dp))
                                Text("الوقت: $dt", color = Dim, fontSize = 12.sp)
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
                        ElevatedCard(
                            modifier = Modifier.weight(1f).padding(4.dp).clickable { selectedCat = c },
                            colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
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
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(svc.uiKey, fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            val hasOverride = overrides.containsKey(svc.uiKey)
                            val baseId = servicesCatalog.first { it.uiKey == svc.uiKey }.serviceId
                            val curId = overrides[svc.uiKey] ?: baseId
                                                        Text("الرقم الحالي: $curId" + if (hasOverride) " (معدل)" else " (افتراضي)", color = Dim, fontSize = 12.sp)
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
                                    Text("الخدمة: ${svc.uiKey}", color = Dim, fontSize = 12.sp)
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
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text("طلب #${c.id}", fontWeight = FontWeight.SemiBold, color = OnBg)
                            Spacer(Modifier.height(4.dp))
                            Text("UID: ${c.uid}", color = Dim, fontSize = 12.sp)
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
                                Text("الوقت: $dt", color = Dim, fontSize = 12.sp)
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
                    Text("أدخل مبلغ الشحن ليُضاف لرصيد المستخدم", color = Dim, fontSize = 12.sp)
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
                    ElevatedCard(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        colors = CardDefaults.elevatedCardColors(containerColor = Surface1, contentColor = OnBg)
                    ) {
                        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("UID: $u", fontWeight = FontWeight.SemiBold, color = OnBg)
                                Text("الحالة: $state", color = Dim, fontSize = 12.sp)
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
        label = { Text(label, fontSize = 12.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal) },
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
private suspend fun httpGet(path: String, headers: Map<String, String> = emptyMap()): Pair<Int, String?> =
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

private suspend fun apiCreateManualOrder(uid: String, name: String): Boolean {
    val body = JSONObject().put("uid", uid).put("title", name)
    val (code, txt) = httpPost("/api/orders/create/manual", body)
    return code in 200..299 && (txt?.contains("ok", true) == true)
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
    onOwnerLogin: (token: String) -> Unit,
    onOwnerLogout: () -> Unit,
    onDismiss: () -> Unit
) {
    val clip = LocalClipboardManager.current
    var showAdminLogin by remember { mutableStateOf(false) }

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
                        Spacer(Modifier.height(6.dp)); Text(err!!, color = Bad, fontSize = 12.sp)
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
                    Text(txt, color = OnBg, fontSize = 12.sp)
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
