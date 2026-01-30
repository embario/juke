package fm.juke.mobile.ui.navigation

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Public
import androidx.compose.material.icons.automirrored.outlined.QueueMusic
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Icon
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import fm.juke.mobile.core.design.JukePalette
import fm.juke.mobile.core.design.components.JukeBackground
import fm.juke.mobile.data.local.SessionSnapshot
import fm.juke.mobile.ui.profile.ProfileRoute
import fm.juke.mobile.ui.search.CatalogRoute
import androidx.compose.foundation.clickable
import androidx.compose.ui.unit.dp

private enum class HomeTab(val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector) {
    PROFILE("Profile", Icons.Outlined.AccountCircle),
    CATALOG("Catalog", Icons.AutoMirrored.Outlined.QueueMusic),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    session: SessionSnapshot,
    onOpenWorld: () -> Unit,
    onLogout: () -> Unit,
) {
    var selectedTab by remember { mutableStateOf(HomeTab.PROFILE) }
    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(text = "@${session.username}") },
                navigationIcon = {
                    Icon(
                        imageVector = Icons.Outlined.Public,
                        contentDescription = "Juke World",
                        tint = JukePalette.Accent,
                        modifier = Modifier
                            .padding(start = 12.dp)
                            .clickable(onClick = onOpenWorld),
                    )
                },
                actions = {
                    TextButton(
                        onClick = onLogout,
                        colors = ButtonDefaults.textButtonColors(contentColor = JukePalette.Accent),
                    ) {
                        Text(text = "Logout")
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = Color.Transparent,
                    titleContentColor = JukePalette.Text,
                    actionIconContentColor = JukePalette.Accent,
                ),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = Color.Transparent) {
                HomeTab.values().forEach { tab ->
                    NavigationBarItem(
                        selected = tab == selectedTab,
                        onClick = { selectedTab = tab },
                        icon = { Icon(imageVector = tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            indicatorColor = JukePalette.Accent.copy(alpha = 0.2f),
                            selectedIconColor = JukePalette.Accent,
                            selectedTextColor = JukePalette.Accent,
                            unselectedIconColor = JukePalette.Muted,
                            unselectedTextColor = JukePalette.Muted,
                        ),
                    )
                }
            }
        },
    ) { paddingValues ->
        JukeBackground(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            when (selectedTab) {
                HomeTab.PROFILE -> ProfileRoute()
                HomeTab.CATALOG -> CatalogRoute()
            }
        }
    }
}
