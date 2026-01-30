package fm.juke.mobile.ui.world

import android.annotation.SuppressLint
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.net.toUri
import androidx.activity.compose.BackHandler
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.di.ServiceLocator
import androidx.compose.ui.unit.dp

data class WorldFocus(
    val lat: Double,
    val lng: Double,
    val username: String? = null,
)

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun JukeWorldScreen(
    token: String,
    focus: WorldFocus?,
    onExit: () -> Unit,
    onLogout: () -> Unit,
) {
    var isLoading by remember { mutableStateOf(true) }

    BackHandler(onBack = onExit)

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(text = "Juke World") },
                navigationIcon = {
                    TextButton(onClick = onExit) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Outlined.ArrowBack,
                            contentDescription = "Home",
                            tint = JukePalette.Accent,
                        )
                        Text(text = "Home", color = JukePalette.Accent)
                    }
                },
                actions = {
                    IconButton(onClick = onLogout) {
                        Icon(
                            imageVector = Icons.Outlined.Logout,
                            contentDescription = "Logout",
                            tint = JukePalette.Accent,
                        )
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = Color.Transparent,
                    titleContentColor = JukePalette.Text,
                ),
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            JukeWorldWebView(
                token = token,
                focus = focus,
                onLoadingChange = { isLoading = it },
                onExit = onExit,
            )
            if (isLoading) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.Black),
                    contentAlignment = Alignment.Center,
                ) {
                    androidx.compose.foundation.layout.Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(12.dp),
                    ) {
                        CircularProgressIndicator(color = JukePalette.Accent)
                        Text(text = "Loading Juke World...", color = Color.White)
                    }
                }
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun JukeWorldWebView(
    token: String,
    focus: WorldFocus?,
    onLoadingChange: (Boolean) -> Unit,
    onExit: () -> Unit,
) {
    val context = LocalContext.current
    val url = remember(token, focus) { buildWorldUrl(focus) }
    val bridge = remember { JukeWorldBridge(onExit) }

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = {
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.databaseEnabled = true
                setBackgroundColor(android.graphics.Color.BLACK)
                webChromeClient = WebChromeClient()
                addJavascriptInterface(bridge, "JukeWorldBridge")
                webViewClient = object : WebViewClient() {
                    override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                        onLoadingChange(true)
                        if (shouldInjectToken(url)) {
                            injectToken(view, token)
                        }
                    }

                    override fun onPageFinished(view: WebView, url: String?) {
                        if (shouldInjectToken(url)) {
                            injectToken(view, token)
                        }
                        onLoadingChange(false)
                    }
                }
                setLayerType(View.LAYER_TYPE_HARDWARE, null)
                loadUrl(url)
            }
        },
        update = { webView ->
            if (shouldInjectToken(webView.url)) {
                injectToken(webView, token)
            }
        },
    )
}

private fun shouldInjectToken(url: String?): Boolean {
    val value = url ?: return false
    return value.startsWith("http://") || value.startsWith("https://")
}

private fun buildWorldUrl(focus: WorldFocus?): String {
    val base = ServiceLocator.normalizedFrontendUrl().toUri()
    val builder = base.buildUpon().appendPath("world")
    builder.appendQueryParameter("native", "1")
    if (focus != null) {
        builder.appendQueryParameter("welcome", "1")
        builder.appendQueryParameter("focusLat", focus.lat.toString())
        builder.appendQueryParameter("focusLng", focus.lng.toString())
        focus.username?.let { username ->
            if (username.isNotBlank()) {
                builder.appendQueryParameter("focusUsername", username)
            }
        }
    }
    return builder.build().toString()
}

private fun injectToken(webView: WebView, token: String) {
    if (token.isBlank()) return
    val escaped = token.replace("\\", "\\\\").replace("'", "\\'")
    val payload = "{\"token\":\"$escaped\"}"
    val script = """
        localStorage.setItem('juke-auth-state', '$payload');
        if (!window.webkit) { window.webkit = {}; }
        if (!window.webkit.messageHandlers) { window.webkit.messageHandlers = {}; }
        window.webkit.messageHandlers.jukeWorld = {
            postMessage: function(payload) {
                if (window.JukeWorldBridge && window.JukeWorldBridge.postMessage) {
                    window.JukeWorldBridge.postMessage(JSON.stringify(payload));
                }
            }
        };
    """.trimIndent()
    webView.evaluateJavascript(script, null)
}

private class JukeWorldBridge(
    private val onExit: () -> Unit,
) {
    @JavascriptInterface
    fun postMessage(payload: String?) {
        if (payload?.contains("\"type\":\"exit\"") == true) {
            onExit()
        }
    }
}
