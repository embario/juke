package fm.juke.core.search

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class DebouncedSearch(
    private val coroutineScope: CoroutineScope,
    private val delayMs: Long = 400L,
) {
    private var pendingSearch: Job? = null

    fun submit(query: String, action: suspend (String) -> Unit) {
        pendingSearch?.cancel()
        pendingSearch = coroutineScope.launch {
            delay(delayMs)
            action(query)
        }
    }

    fun cancel() {
        pendingSearch?.cancel()
        pendingSearch = null
    }
}
