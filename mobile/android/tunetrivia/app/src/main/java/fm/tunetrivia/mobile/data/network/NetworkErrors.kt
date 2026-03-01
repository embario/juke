package fm.tunetrivia.mobile.data.network

import fm.juke.core.network.humanReadableMessage as coreHumanReadableMessage

// Delegated to JukeCore — re-export for existing import compatibility.
fun Throwable.humanReadableMessage(): String = coreHumanReadableMessage()
