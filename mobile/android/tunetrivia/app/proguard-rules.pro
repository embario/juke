# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.juke.tunetrivia.**$$serializer { *; }
-keepclassmembers class com.juke.tunetrivia.** {
    *** Companion;
}
-keepclasseswithmembers class com.juke.tunetrivia.** {
    kotlinx.serialization.KSerializer serializer(...);
}
