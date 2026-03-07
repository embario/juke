package com.juke.shotclock.model

import com.juke.shotclock.data.network.dto.SessionPlayerDto

data class SessionPlayer(
    val id: String,
    val userId: Int,
    val username: String,
    val displayName: String,
    val isAdmin: Boolean,
)

fun SessionPlayerDto.toDomain(): SessionPlayer = SessionPlayer(
    id = id,
    userId = user.id,
    username = user.username,
    displayName = user.displayName.orEmpty().ifBlank { user.username },
    isAdmin = isAdmin,
)
