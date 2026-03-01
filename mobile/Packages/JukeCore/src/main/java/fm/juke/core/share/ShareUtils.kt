package fm.juke.core.share

import android.content.Context
import android.content.Intent
import android.net.Uri

fun shareSmsOrText(
    context: Context,
    message: String,
    chooserTitle: String,
) {
    val smsIntent = Intent(Intent.ACTION_SENDTO).apply {
        data = Uri.parse("smsto:")
        putExtra("sms_body", message)
    }
    if (smsIntent.resolveActivity(context.packageManager) != null) {
        context.startActivity(smsIntent)
        return
    }

    val shareIntent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, message)
    }
    context.startActivity(Intent.createChooser(shareIntent, chooserTitle))
}
