# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.juke.shotclock.**$$serializer { *; }
-keepclassmembers class com.juke.shotclock.** {
    *** Companion;
}
-keepclasseswithmembers class com.juke.shotclock.** {
    kotlinx.serialization.KSerializer serializer(...);
}
