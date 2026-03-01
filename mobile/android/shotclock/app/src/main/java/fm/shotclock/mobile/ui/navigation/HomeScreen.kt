package fm.shotclock.mobile.ui.navigation

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.QueueMusic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import fm.juke.core.session.SessionSnapshot
import fm.shotclock.mobile.core.design.ShotClockPalette
import fm.shotclock.mobile.core.design.components.ShotClockBackground
import fm.shotclock.mobile.ui.session.lobby.SessionListRoute
import fm.shotclock.mobile.ui.profile.ProfileRoute

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    session: SessionSnapshot,
    onLogout: () -> Unit,
) {
    var selectedTab by remember { mutableStateOf(HomeTab.SESSIONS) }

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text(
                        text = "ShotClock",
                        color = ShotClockPalette.Accent,
                    )
                },
                actions = {
                    TextButton(
                        onClick = onLogout,
                        colors = ButtonDefaults.textButtonColors(contentColor = ShotClockPalette.Accent),
                    ) {
                        Text(text = "Logout")
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = Color.Transparent,
                    titleContentColor = ShotClockPalette.Accent,
                    actionIconContentColor = ShotClockPalette.Accent,
                ),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = Color.Transparent) {
                HomeTab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = tab == selectedTab,
                        onClick = { selectedTab = tab },
                        icon = { Icon(imageVector = tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                        colors = NavigationBarItemDefaults.colors(
                            indicatorColor = ShotClockPalette.Accent.copy(alpha = 0.2f),
                            selectedIconColor = ShotClockPalette.Accent,
                            selectedTextColor = ShotClockPalette.Accent,
                            unselectedIconColor = ShotClockPalette.Muted,
                            unselectedTextColor = ShotClockPalette.Muted,
                        ),
                    )
                }
            }
        },
    ) { paddingValues ->
        ShotClockBackground(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            when (selectedTab) {
                HomeTab.SESSIONS -> SessionListRoute(session = session)
                HomeTab.PROFILE -> ProfileRoute()
            }
        }
    }
}

private enum class HomeTab(val label: String, val icon: ImageVector) {
    SESSIONS("Sessions", Icons.Outlined.QueueMusic),
    PROFILE("Profile", Icons.Outlined.AccountCircle),
}
